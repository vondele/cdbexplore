import requests
import time
import copy
import chess
import sys
import threading
import concurrent.futures
from datetime import datetime
from multiprocessing import freeze_support


class AtomicTT:
    def __init__(self):
        self._lock = threading.Lock()
        self.cache = {}

    def get(self, epd):
        with self._lock:
            return self.cache.get(epd)

    def set(self, epd, result):
        with self._lock:
            if epd not in self.cache or self.cache[epd]["depth"] <= result["depth"]:
                self.cache[epd] = result
            return self.cache[epd]


class AtomicInteger:
    def __init__(self, value=0):
        self._value = int(value)
        self._lock = threading.Lock()

    def inc(self, d=1):
        with self._lock:
            self._value += int(d)
            return self._value

    def dec(self, d=1):
        return self.inc(-d)

    def get(self):
        with self._lock:
            return self._value

    def set(self, v):
        with self._lock:
            self._value = int(v)
            return self._value


class ChessDB:
    def __init__(self, concurrency, evalDecay):
        # user defined parameters
        self.concurrency = concurrency
        self.evalDecay = evalDecay

        # some counters that will be accessed by multiple threads
        self.count_queryall = AtomicInteger(0)
        self.count_uncached = AtomicInteger(0)
        self.count_enqueued = AtomicInteger(0)
        self.count_inflightRequests = AtomicInteger(0)
        self.count_sumInflightRequests = AtomicInteger(0)

        # for timing output
        self.count_starttime = time.perf_counter()

        # use a session to keep alive the connection to the server
        self.session = requests.Session()

        # our dictionary to cache intermediate results
        self.TT = AtomicTT()

        # At each level in the tree we need a few threads.
        # Evaluations can happen at any level, so we can saturate the work executor nevertheless
        self.executorTree = [
            concurrent.futures.ThreadPoolExecutor(
                max_workers=max(2, self.concurrency // 4)
            )
        ]
        self.executorWork = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.concurrency
        )

    def __apicall(self, url, timeout):
        self.count_inflightRequests.inc()
        try:
            response = self.session.get(url, timeout=timeout)
            response.raise_for_status()
            content = response.json()
        except Exception:
            content = None
        self.count_inflightRequests.dec()
        return content

    def queryall(self, epd, skipTT):
        """query chessdb until scored moves come back"""

        # book keeping of calls and average in flight requests.
        self.count_queryall.inc()
        self.count_sumInflightRequests.inc(self.count_inflightRequests.get())

        # see if we can return this result from the TT
        if not skipTT:
            result = self.TT.get(epd)
            if result is not None:
                return result

        # if uncached retrieve from chessdb
        self.count_uncached.inc()

        api = "http://www.chessdb.cn/cdb.php"
        timeout = 5
        found = False
        first = True
        enqueued = False
        result = {"depth": 0}
        lasterror = ""

        while not found:
            # sleep a bit before further requests
            if not first:
                # adjust timeout increasing after every attempt, up to a max.
                if timeout < 60:
                    timeout = timeout * 1.5
                else:
                    print(
                        datetime.now().isoformat(),
                        " - failed to get reply for : ",
                        epd,
                        " last error: ",
                        lasterror,
                        flush=True,
                    )
                time.sleep(timeout)
            else:
                first = False

            url = api + f"?action=queryall&board={epd}&json=1"
            content = self.__apicall(url, timeout)

            if content is None:
                lasterror = "Something went wrong with queryall"
                continue

            if "status" not in content:
                lasterror = "Malformed reply, not containing status"
                continue

            if content["status"] == "unknown":
                # unknown position, queue and see again
                if not enqueued:
                    enqueued = True
                    self.count_enqueued.inc()

                url = api + f"?action=queue&board={epd}&json=1"
                content = self.__apicall(url, timeout)
                if content is None:
                    lasterror = "Something went wrong with queue"
                    continue

                # special case, position not available in cdb,
                # e.g. in TB but with castling rights.
                # score all moves as draw, and let search figure it out
                if content == {}:
                    found = True
                    board = chess.Board(epd)
                    for move in board.legal_moves:
                        ucimove = move.uci()
                        result[ucimove] = 0
                    lasterror = "Position not queued"
                    continue

                lasterror = "Enqueued position"
                continue

            elif content["status"] == "rate limit exceeded":
                # special case, request to clear the limit
                url = api + "?action=clearlimit"
                self.__apicall(url, timeout)
                lasterror = "asked to clearlimit"
                continue

            elif content["status"] == "ok":
                found = True
                if "moves" in content:
                    for m in content["moves"]:
                        result[m["uci"]] = m["score"]
                else:
                    lasterror = "Unexpectedly missing moves"
                    continue

            elif content["status"] == "checkmate" or content["status"] == "stalemate":
                found = True

            elif content["status"] == "invalid board":
                result = {}
                found = True

            else:
                lasterror = "Surprise reply"
                continue

        # set and return a possibly even deeper result
        return self.TT.set(epd, result)

    # query all positions along the PV back to the root
    def reprobe_PV(self, board, PV):
        local_board = copy.deepcopy(board)
        for ucimove in PV:
            try:
                move = chess.Move.from_uci(ucimove)
                local_board.push(move)
            except Exception:
                pass

        while True:
            self.executorWork.submit(self.queryall, local_board.epd(), skipTT=True)
            try:
                local_board.pop()
            except Exception:
                break

    def move_depth(self, bestscore, worstscore, score, depth):
        delta = score - bestscore if score is not None else worstscore - bestscore
        decay = delta // self.evalDecay if self.evalDecay != 0 else -100
        return depth + decay - 1 if score is not None else min(0, depth + decay - 1 - 1)

    def search(self, board, depth):
        if board.is_checkmate():
            return (-40000 + board.ply(), ["checkmate"])

        if (
            board.is_stalemate()
            or board.is_insufficient_material()
            or board.can_claim_draw()
        ):
            return (0, ["draw"])

        # get current ranking, use an executor to limit total requests in flight
        scored_db_moves = self.executorWork.submit(
            self.queryall, board.epd(), skipTT=False
        ).result()
        if scored_db_moves == {}:
            return (0, ["invalid"])

        # also force a query for high depth moves that do not have a full list of scored moves,
        # we use this to add newly scored moves to our TT
        skipTT_db_moves = None
        if depth > 10:
            for move in board.legal_moves:
                ucimove = move.uci()
                if ucimove not in scored_db_moves:
                    skipTT_db_moves = self.executorWork.submit(
                        self.queryall, board.epd(), skipTT=True
                    )
                    break

        bestscore = -40001
        bestmove = None
        worstscore = +40001

        for m in scored_db_moves:
            if m == "depth":
                continue
            s = scored_db_moves[m]
            if s > bestscore:
                bestscore = s
                bestmove = m
            if s < worstscore:
                worstscore = s

        # guarantee sufficient depth of the executorTree list
        ply = board.ply()
        while len(self.executorTree) < ply + 1:
            self.executorTree.append(
                concurrent.futures.ThreadPoolExecutor(max_workers=self.concurrency)
            )

        newly_scored_moves = {"depth": depth}

        tried_unscored = False
        moves_to_search = 0
        for move in board.legal_moves:
            ucimove = move.uci()
            score = scored_db_moves.get(ucimove, None)
            newdepth = self.move_depth(bestscore, worstscore, score, depth)
            if newdepth >= 0 and not tried_unscored:
                moves_to_search += 1

        minicache = {}
        futures = {}
        tried_unscored = False

        for move in board.legal_moves:
            ucimove = move.uci()
            score = scored_db_moves.get(ucimove, None)
            newdepth = self.move_depth(bestscore, worstscore, score, depth)

            # extension
            if moves_to_search == 1 and bestscore == score and depth > 4:
                newdepth += 1

            if newdepth >= 0 and not tried_unscored:
                board.push(move)
                futures[ucimove] = self.executorTree[ply].submit(
                    self.search, copy.deepcopy(board), newdepth
                )
                board.pop()
                tried_unscored = True if score is None else tried_unscored
            elif score is not None:
                newly_scored_moves[ucimove] = scored_db_moves[ucimove]
                minicache[ucimove] = [ucimove]

        # get the results from the futures
        for ucimove in futures:
            s, pv = futures[ucimove].result()
            minicache[ucimove] = [ucimove] + pv
            newly_scored_moves[ucimove] = -s

        # add potentially newly scored moves, or moves we have not explored by search
        if skipTT_db_moves:
            skipTT_db_moves = skipTT_db_moves.result()
            for move in board.legal_moves:
                ucimove = move.uci()
                if ucimove in skipTT_db_moves:
                    if ucimove not in newly_scored_moves:
                        newly_scored_moves[ucimove] = skipTT_db_moves[ucimove]
                        minicache[ucimove] = [ucimove]
                    elif newly_scored_moves[ucimove] != skipTT_db_moves[ucimove]:
                        board.push(move)
                        if self.TT.get(board.epd()) is None:
                            newly_scored_moves[ucimove] = skipTT_db_moves[ucimove]
                            minicache[ucimove] = [ucimove]
                        board.pop()

        # store our computed result
        self.TT.set(board.epd(), newly_scored_moves)

        bestscore = -40001
        bestmove = None

        for m in newly_scored_moves:
            if m == "depth":
                continue
            s = newly_scored_moves[m]
            if s > bestscore or (
                s == bestscore and len(minicache[m]) > len(minicache[bestmove])
            ):
                bestscore = s
                bestmove = m

        if depth > 15:
            self.reprobe_PV(board, minicache[bestmove])

        return (bestscore, minicache[bestmove])


def cdbsearch(epd, depthLimit, concurrency, evalDecay):
    # on 32-bit systems, such as Raspberry Pi, it is prudent to adjust the
    # thread stack size before calling this method, as seen in __main__ below

    # basic output
    print("Searched epd : ", epd)
    print("evalDecay: ", evalDecay)
    print("Concurrency  : ", concurrency)
    print("Starting date: ", datetime.now().isoformat())

    # create a ChessDB
    chessdb = ChessDB(concurrency=concurrency, evalDecay=evalDecay)

    # set initial board, including the moves provided within epd
    if "moves" in epd:
        epd, _, epdMoves = epd.partition("moves")
        epdMoves = epdMoves.split()
    else:
        epdMoves = []
    epd = epd.strip()  # avoid leading and trailing spaces in URL below
    board = chess.Board(epd)
    for m in epdMoves:
        move = chess.Move.from_uci(m)
        board.push(move)
    depth = 1
    while depthLimit is None or depth <= depthLimit:
        bestscore, pv = chessdb.search(board, depth)
        runtime = time.perf_counter() - chessdb.count_starttime
        queryall = chessdb.count_queryall.get()
        print("Search at depth ", depth)
        print("  score     : ", bestscore)
        print("  PV        : ", " ".join(pv))
        if queryall:
            print("  queryall  : ", queryall)
            print(f"  bf        :  { queryall**(1/depth) :.2f}")
            print(
                f"  inflight  : { chessdb.count_sumInflightRequests.get() / queryall : .2f}"
            )
            print("  chessdbq  : ", chessdb.count_uncached.get())
            print("  enqueued  : ", chessdb.count_enqueued.get())
            print("  date      : ", datetime.now().isoformat())
            print("  total time: ", int(1000 * runtime))
            print(
                "  req. time : ",
                int(1000 * runtime / chessdb.count_uncached.get()),
            )

        pvline = " ".join(
            [m for m in epdMoves + pv if m not in ["checkmate", "draw", "invalid"]]
        )
        if pvline:
            pvline = " moves " + pvline
        url = f"https://chessdb.cn/queryc_en/?{epd}{pvline}"
        print("  URL       : ", url.replace(" ", "_"))

        print("", flush=True)
        depth += 1
        if pv in [["checkmate"], ["draw"], ["invalid"]]:  # nothing to be done
            break


if __name__ == "__main__":
    import argparse
    freeze_support()

    argParser = argparse.ArgumentParser(
        description="Explore and extend the Chess Cloud Database (https://chessdb.cn/queryc_en/). Builds a search tree for a given position.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    group = argParser.add_mutually_exclusive_group()
    group.add_argument(
        "--epd",
        help="""EPD/FEN to explore: acceptable are FENs w/ and w/o move counters, as well as the extended "moves m1 m2 m3" syntax from cdb's API.""",
        default=chess.STARTING_FEN[:-3] + "moves g2g4",
    )
    group.add_argument(
        "--san",
        help='Moves in SAN notation that lead to the position to be explored. E.g. "1. g4".',
    )
    argParser.add_argument(
        "--depthLimit",
        help="Finish the exploration at the specified depth.",
        type=int,
        default=None,
    )
    argParser.add_argument(
        "--concurrency",
        help="Concurrency of requests. This is the maximum number of requests made to chessdb at the same time.",
        type=int,
        default=16,
    )
    argParser.add_argument(
        "--evalDecay",
        help="Depth decrease per cp eval-to-best. A small number will use a very narrow search, 0 will essentially just follow PV lines. A wide search will likely enqueue many positions.",
        type=int,
        default=2,
    )
    args = argParser.parse_args()

    if sys.maxsize <= 2**32:
        # on 32-bit systems we limit thread stack size, as many are created
        stackSize = 4096 * 64
        threading.stack_size(stackSize)

    if args.san is not None:
        import chess.pgn, io

        if args.san:
            pgn = io.StringIO(args.san)
            game = chess.pgn.read_game(pgn)
            epd = game.board().epd() + " moves"
            for move in game.mainline_moves():
                epd += f" {move}"
        else:
            epd = chess.STARTING_FEN  # passing empty string to --san gives startpos
    else:
        epd = args.epd

    cdbsearch(
        epd=epd,
        depthLimit=args.depthLimit,
        concurrency=args.concurrency,
        evalDecay=args.evalDecay,
    )
