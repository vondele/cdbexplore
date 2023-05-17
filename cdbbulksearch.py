from io import StringIO
import argparse, sys
import chess, chess.pgn
import cdbsearch
import concurrent.futures
import signal
from multiprocessing import freeze_support, active_children


def wrapcdbsearch(epd, depthLimit, concurrency, evalDecay, cursedWins=False):
    old_stdout = sys.stdout
    sys.stdout = mystdout = StringIO()
    try:
        cdbsearch.cdbsearch(
            epd=epd,
            depthLimit=depthLimit,
            concurrency=concurrency,
            evalDecay=evalDecay,
            cursedWins=cursedWins,
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
        help="Pass positions from filename to cdbsearch in an infinite loop.",
    )
    args = argParser.parse_args()

    if sys.maxsize <= 2**32:
        # on 32-bit systems we limit thread stack size, as many are created
        stackSize = 4096 * 64
        threading.stack_size(stackSize)

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
    while True:  # if args.forever is true, run indefinitely; o/w stop after one run
        # re-reading the data in each loop allows updates to it in the background
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
                        epd = " ".join(
                            epd.split()[:4]
                        )  # cdb ignores move counters anyway
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
            print(f"Read {len(metalist)} EPDs from file {args.filename}.")

        with concurrent.futures.ProcessPoolExecutor(
            max_workers=args.bulkConcurrency
        ) as executor:
            fs = []
            print("Scheduling work ... ", flush=True)
            for item in metalist:
                if isPGN:
                    epd = item.board().epd()
                    if len(list(item.mainline_moves())):
                        epd += " moves"
                    for move in item.mainline_moves():
                        epd += f" {move}"
                else:
                    epd = item
                fs.append(
                    (
                        epd,
                        executor.submit(
                            wrapcdbsearch,
                            epd=epd,
                            depthLimit=args.depthLimit,
                            concurrency=args.concurrency,
                            evalDecay=args.evalDecay,
                            cursedWins=args.cursedWins,
                        ),
                    )
                )
            print(
                f"Scheduled {len(fs)} positions to be explored with concurrency {args.bulkConcurrency}."
            )
            for epd, f in fs:
                print(
                    "=" * 72
                    + f'\nAwaiting results for exploration of EPD "{epd}" to depth {args.depthLimit} ... ',
                    flush=True,
                )
                try:
                    print(f.result(), flush=True)
                except Exception as ex:
                    print(f' error: caught exception "{ex}"')

        print(f"Done processing {args.filename}.")
        if not args.forever:
            break
