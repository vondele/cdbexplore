from io import StringIO
import asyncio
import argparse, sys
import chess, chess.pgn
import cdbsearch
import concurrent.futures
import signal
from multiprocessing import freeze_support, active_children
from collections import deque


def wrapcdbsearch(epd, depthLimit, concurrency, evalDecay, cursedWins=False):
    old_stdout = sys.stdout
    sys.stdout = mystdout = StringIO()
    try:
        asyncio.run(
            cdbsearch.cdbsearch(
                epd=epd,
                depthLimit=depthLimit,
                concurrency=concurrency,
                evalDecay=evalDecay,
                cursedWins=cursedWins,
            )
        )
    except Exception as ex:
        print(f' error: while searching {epd} caught exception "{ex}"')
    sys.stdout = old_stdout
    return mystdout.getvalue()


if __name__ == "__main__":
    freeze_support()
    argParser = argparse.ArgumentParser(
        description="Sequentially call cdbsearch for EPDs or book exits stored in a file.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    argParser.add_argument(
        "filename", help="PGN file if suffix is .pgn, o/w a text file with EPDs."
    )
    argParser.add_argument(
        "--depthLimit",
        help="Argument passed to cdbsearch.",
        type=int,
        default=5,
    )
    argParser.add_argument(
        "--concurrency",
        help="Argument passed to cdbsearch.",
        type=int,
        default=16,
    )
    argParser.add_argument(
        "--evalDecay",
        help="Argument passed to cdbsearch.",
        type=int,
        default=2,
    )
    argParser.add_argument(
        "--cursedWins",
        action="store_true",
        help="Argument passed to cdbsearch.",
    )
    argParser.add_argument(
        "--bulkConcurrency",
        help="Number of concurrent processes running cdbsearch.",
        type=int,
        default=4,
    )
    argParser.add_argument(
        "--forever",
        action="store_true",
        help="Pass positions from filename to cdbsearch in an infinite loop, increasing depthLimit by one after each completed cycle.",
    )
    args = argParser.parse_args()

    def on_sigint(signal, frame):
        print("Received signal to terminate. Killing sub-processes.", flush=True)
        for child in active_children():
            child.kill()
        print("Done.", flush=True)
        sys.exit(1)

    # Install signal handlers.
    signal.signal(signal.SIGINT, on_sigint)
    signal.signal(signal.SIGTERM, on_sigint)
    try:
        signal.signal(signal.SIGQUIT, on_sigint)
    except:
        # Windows does not have SIGQUIT.
        pass
    try:
        signal.signal(signal.SIGBREAK, on_sigint)
    except:
        # Linux does not have SIGBREAK.
        pass

    isPGN = args.filename.endswith(".pgn")
    metalist = []
    if isPGN:
        pgn = open(args.filename)
        while game := chess.pgn.read_game(pgn):
            metalist.append(game)
        print(f"Read {len(metalist)} (opening) lines from file {args.filename}.")
    else:
        with open(args.filename) as f:
            for line in f:
                line = line.strip()
                if line:
                    if line.startswith("#"):  # ignore comments
                        continue
                    epd, _, moves = line.partition("moves")
                    epd = " ".join(epd.split()[:4])  # cdb ignores move counters anyway
                    epdMoves = " moves"
                    for m in moves.split():
                        if (
                            len(m) < 4
                            or len(m) > 5
                            or not {m[0], m[2]}.issubset(set("abcdefgh"))
                            or not {m[1], m[3]}.issubset(set("12345678"))
                            or (len(m) == 5 and not m[4] in "qrbn")
                        ):
                            break
                        epdMoves += f" {m}"
                    if epdMoves != " moves":
                        epd += epdMoves
                    metalist.append(epd)

    epds = []
    for item in metalist:
        if isPGN:
            epd = item.board().epd()
            if len(list(item.mainline_moves())):
                epd += " moves"
            for move in item.mainline_moves():
                epd += f" {move}"
        else:
            epd = item
        epds.append(epd)

    print(f"Using {len(epds)} EPDs from file {args.filename}.")

    epdIdx = 0
    depthLimit = args.depthLimit

    executor = concurrent.futures.ProcessPoolExecutor(max_workers=args.bulkConcurrency)
    print(f"Positions to be explored with concurrency {args.bulkConcurrency}.")

    tasks = deque()
    task = None

    class TaskCounter:
        def __init__(self):
            self.counter = 0

        def inc(self):
            self.counter += 1

        def dec(self, fn):
            self.counter -= 1

        def get(self):
            return self.counter

    taskCounter = TaskCounter()

    while True:
        if epdIdx == len(epds):
            # We arrived at the end of the list: see if we cycle or break.
            if args.forever:
                depthLimit += 1
                epdIdx = 0
            elif task is None and len(tasks) == 0:
                break
        else:
            # Add some more tasks to the list if few are pending
            if taskCounter.get() < 2 * args.bulkConcurrency:
                epd = epds[epdIdx]
                future = executor.submit(
                    wrapcdbsearch,
                    epd=epd,
                    depthLimit=depthLimit,
                    concurrency=args.concurrency,
                    evalDecay=args.evalDecay,
                    cursedWins=args.cursedWins,
                )
                taskCounter.inc()
                future.add_done_callback(taskCounter.dec)
                tasks.append(
                    (
                        epd,
                        epdIdx,
                        depthLimit,
                        future,
                    )
                )
                epdIdx += 1

        if task is None:
            if len(tasks) > 0:
                task = tasks.popleft()
                print(
                    "=" * 72
                    + f'\nAwaiting results for exploration of EPD "{task[0]}" ({task[1] + 1} / {len(epds)}) to depth {task[2]} ... ',
                    flush=True,
                )
        else:
            # See if we have a result, if not continue.
            try:
                print(task[3].result(timeout=0.01), flush=True)
                task = None
            except concurrent.futures.TimeoutError:
                pass
            except Exception as ex:
                print(f' error: caught exception "{ex}"')
                task = None

    executor.shutdown()
    print(f"Done processing {args.filename}.")
