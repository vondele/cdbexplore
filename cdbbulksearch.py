import argparse, sys
import chess, chess.pgn
import cdbsearch
import concurrent.futures


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
    default=22,
)
argParser.add_argument(
    "--concurrency",
    help="Argument passed to cdbsearch.",
    type=int,
    default=16,
)
argParser.add_argument(
    "--bulkConcurrency",
    help="Number of concurrent processes running cdbsearch",
    type=int,
    default=1,
)
argParser.add_argument(
    "--evalDecay",
    help="Argument passed to cdbsearch.",
    type=int,
    default=2,
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
                    epd = " ".join(epd.split()[:4])  # cdb ignores move counters anyway
                    epdMoves = " moves"
                    for m in moves.split():
                        if (
                            len(m) != 4
                            or not {m[0], m[2]}.issubset(set("abcdefgh"))
                            or not {m[1], m[3]}.issubset(set("12345678"))
                        ):
                            break
                        epdMoves += f" {m}"
                    if epdMoves != " moves":
                        epd += epdMoves
                    metalist.append(epd)
        print(f"Read {len(metalist)} EPDs from file {args.filename}.")

    with concurrent.futures.ProcessPoolExecutor(max_workers=args.bulkConcurrency) as executor:
        for item in metalist:
            if isPGN:
                epd = item.board().epd()
                if len(list(item.mainline_moves())):
                    epd += " moves"
                for move in item.mainline_moves():
                    epd += f" {move}"
            else:
                epd = item
            executor.submit(
                cdbsearch.cdbsearch,
                epd=epd,
                depthLimit=args.depthLimit,
                concurrency=args.concurrency,
                evalDecay=args.evalDecay,
            )
    print(f"Done processing {args.filename}.")
    if not args.forever:
        break
