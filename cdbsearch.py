import requests
import time
import chess
import sys
import threading
import concurrent.futures
from datetime import datetime, timedelta
from multiprocessing import freeze_support

# current conventions on chessdb.cn for mates, TBwins, cursed wins and special evals
CDB_MATE = 30000
CDB_TBWIN = 25000
CDB_CURSED = 20000
CDB_SPECIAL = 10000


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
    def __init__(
        self, concurrency, evalDecay, cursedWins=False, rootBoard=chess.Board()
    ):
        # user defined parameters
        self.concurrency = concurrency
        self.evalDecay = evalDecay
        self.cursedWins = cursedWins

        # the root position under which the tree will be built
        self.rootBoard = rootBoard

        # some counters that will be accessed by multiple threads
        self.count_queryall = AtomicInteger()
        self.count_uncached = AtomicInteger()
        self.count_enqueued = AtomicInteger()
        self.count_unscored = AtomicInteger()
        self.count_inflightRequests = AtomicInteger()
        self.count_sumInflightRequests = AtomicInteger()

        # for timing output
        self.count_starttime = time.perf_counter()

        # use a session to keep alive the connection to the server
        self.session = requests.Session()

        # our dictionary to cache intermediate results
        self.TT = AtomicTT()

        # a dictionary storing the distance to leaf for positions on cdb PVs
        self.cdbPvToLeaf = {}

        # list of ThreadPoolExecutors, one for each level
        self.executorTree = []

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

    def __cdbapicall(self, action, timeout):
        return self.__apicall("http://www.chessdb.cn/cdb.php" + action, timeout)

    def add_cdb_pv_positions(self, epd):
        """query cdb for the PV of the position and create a dictionary containing these positions and their distance to the PV leaf for extensions during search"""
        content = self.__cdbapicall(f"?action=querypv&board={epd}&json=1", timeout=15)
        if (
            content
            and "status" in content
            and content["status"] == "ok"
            and "pv" in content
        ):
            pv = content["pv"]
            self.cdbPvToLeaf[epd] = len(pv)
            self.executorWork.submit(self.queryall, epd)
            board = chess.Board(epd)
            for parsed, m in enumerate(pv):
                move = chess.Move.from_uci(m)
                board.push(move)
                self.cdbPvToLeaf[board.epd()] = len(pv) - 1 - parsed
                self.executorWork.submit(self.queryall, board.epd())

    def pv_has_proven_mate(self, epd, pv):
        """check if the PV line is a proven mate on cdb, and if not help prove it"""
        print("Enter with pv = ", pv)
        if not pv or pv[-1] != "checkmate":
            return False
        _ = input(f"before board, len(pv) = {len(pv)}, % 2 = {len(pv) % 2}")
        if pv == ["checkmate"]:
            return True
        board = chess.Board(epd)
        if len(pv) % 2 == 0:  # we just need to check the defender's moves
            board.push(chess.Move.from_uci(pv[0]))
            return self.pv_has_proven_mate(board.epd(), pv[1:])

        scored_db_moves = self.executorWork.submit(self.queryall, epd).result()
        print(scored_db_moves)
        _ = input(f"#legal moves = {len(list(board.legal_moves))}, # scored = {len(scored_db_moves) - 1}")
        if len(list(board.legal_moves)) != len(scored_db_moves) - 1: # there are unscored moves for epd
            # do here the helping proof bit
            return False

        # we need to check if the _given_ PV is a correct mating line:
        for m in pv[:2]:
            board.push(chess.Move.from_uci(m))
        if not self.pv_has_proven_mate(board.epd(), pv[2:]):
            return False
        for _ in [0, 1]:
            board.pop()

        for m in scored_db_moves:
            if m == "depth" or m == pv[0]:  # the move that is first PV move was already checked
                continue
            board.push(chess.Move.from_uci(m))
            # @vondele: not sure about this line (the searches can be parallelized in future)
            _, mpv = self.executorWork.submit(self.search, board.epd(),len(pv) - 2).result()
            if not self.pv_has_proven_mate(board.epd(), mpv):
                return False
            board.pop()

    def queryall(self, epd, skipTT=False):
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

            content = self.__cdbapicall(f"?action=queryall&board={epd}&json=1", timeout)

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

                content = self.__cdbapicall(
                    f"?action=queue&board={epd}&json=1", timeout
                )
                if content is None:
                    lasterror = "Something went wrong with queue"
                    continue

                # special case: position not available in cdb, e.g. in TB but with castling rights
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
                self.__cdbapicall("?action=clearlimit", timeout)
                lasterror = "Asked to clearlimit"
                continue

            elif content["status"] == "ok":
                found = True
                try:
                    for m in content["moves"]:
                        s = m["score"]
                        if abs(s) >= CDB_SPECIAL:
                            if not self.cursedWins and abs(s) <= CDB_CURSED:
                                # cursed wins are TB mates that run afoul of 50mr
                                s = 0
                            else:
                                # to stay in sync with cdb evals, we need to counter-act the bestscore off-set applied later on
                                s += 1 if s >= 0 else -1
                        result[m["uci"]] = s
                except:
                    # we do not trust possibly partial move information received
                    found = False
                    result = {"depth": 0}
                    lasterror = "Unexpected or malformed json reply"
                    continue

            elif content["status"] in ["checkmate", "stalemate"]:
                found = True

            elif content["status"] == "invalid board":
                result = {}
                found = True

            else:
                lasterror = "Surprise reply"
                continue

        # set and return a possibly even deeper result
        return self.TT.set(epd, result)

    def reprobe_PV(self, board, pv):
        """query all positions along the PV back to the root"""
        local_board = board.copy()
        for ucimove in pv:
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
        """returns depth - 1 for bestmove and negative values for bad moves, terminating their search; unscored moves are treated worse than worstmove, returning at most 0"""
        delta = score - bestscore if score is not None else worstscore - bestscore
        decay = delta // self.evalDecay if self.evalDecay != 0 else 10**6 * delta
        return depth + decay - 1 if score is not None else min(0, depth + decay - 2)

    def search(self, board, depth):
        """returns (bestscore, pv) for current position stored in board"""

        if board.is_checkmate():
            return -CDB_MATE, ["checkmate"]

        if (
            board.is_stalemate()
            or board.is_insufficient_material()
            or board.can_claim_draw()
        ):
            return 0, ["draw"]

        # get current ranking, use an executor to limit total requests in flight
        scored_db_moves = self.executorWork.submit(self.queryall, board.epd()).result()
        if scored_db_moves == {}:
            return 0, ["invalid"]

        scoreCount = len(scored_db_moves) - 1  # number of scored moves for board

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

        bestscore = -(CDB_MATE + 1)
        bestmove = None
        worstscore = CDB_MATE + 1

        for m, s in scored_db_moves.items():
            if m == "depth":
                continue
            if s > bestscore:
                bestscore = s
                bestmove = m
            if s < worstscore:
                worstscore = s

        # ply stores the level of the search tree we are in, i.e. how many plies we are away from rootBoard
        ply = len(board.move_stack) - len(self.rootBoard.move_stack)

        # guarantee sufficient length of the executorTree list
        while len(self.executorTree) < ply + 1:
            self.executorTree.append(
                concurrent.futures.ThreadPoolExecutor(max_workers=self.concurrency)
            )

        moves_to_search = 0
        for move in board.legal_moves:
            ucimove = move.uci()
            score = scored_db_moves.get(ucimove, None)
            newdepth = self.move_depth(bestscore, worstscore, score, depth)
            if newdepth >= 0:
                moves_to_search += 1

        newly_scored_moves = {"depth": depth}
        minicache = {}  # store candidate PVs for all newly scored moves
        futures = {}
        tried_unscored = False

        for move in board.legal_moves:
            ucimove = move.uci()
            score = scored_db_moves.get(ucimove, None)
            newdepth = self.move_depth(bestscore, worstscore, score, depth)

            # extension if the unique bestmove is the only move to be searched deeper or the position is in the cdb PV
            if score == bestscore:
                cdbPvToLeaf = self.cdbPvToLeaf.get(board.epd(), None)
                if (moves_to_search == 1 and depth > 4) or (
                    cdbPvToLeaf is not None and newdepth < cdbPvToLeaf
                ):
                    newdepth += 1

            # schedule qualifying moves for deeper searches, at most 1 unscored move
            # for sufficiently large depth and suffiently small scoreCount we possibly schedule an unscored move
            if (newdepth >= 0 and not (score is None and tried_unscored)) or (
                score is None and not tried_unscored and depth > 15 + scoreCount
            ):
                board.push(move)
                futures[ucimove] = self.executorTree[ply].submit(
                    self.search, board.copy(), newdepth
                )
                board.pop()
                if score is None:
                    tried_unscored = True
                    self.count_unscored.inc()
            elif score is not None:
                newly_scored_moves[ucimove] = scored_db_moves[ucimove]
                minicache[ucimove] = [ucimove]

        # get the results from the futures
        for ucimove, search in futures.items():
            s, pv = search.result()
            newly_scored_moves[ucimove] = -s
            minicache[ucimove] = [ucimove] + pv

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

        # find bestmove and associated PV
        bestscore = -(CDB_MATE + 1)
        for m, s in newly_scored_moves.items():
            if m == "depth":
                continue
            if s > bestscore or (
                s == bestscore and len(minicache[m]) > len(minicache[bestmove])
            ):
                bestscore = s
                bestmove = m

        if depth > 15:
            self.reprobe_PV(board, minicache[bestmove])

        # for lines leading to mates, TBwins and cursed wins we do not use mini-max, but rather store the distance in ply
        # this means local evals for such nodes will always be in sync with cdb
        if abs(bestscore) > CDB_SPECIAL:
            bestscore -= 1 if bestscore >= 0 else -1

        return bestscore, minicache[bestmove]


def cdbsearch(epd, depthLimit, concurrency, evalDecay, cursedWins=False):
    """on 32-bit systems, such as Raspberry Pi, it is prudent to adjust the thread stack size before calling this method, as seen in __main__ below"""

    concurrency = max(1, concurrency)
    evalDecay = max(0, evalDecay)

    # basic output
    print("Searched epd : ", epd)
    print("evalDecay    : ", evalDecay)
    print("Concurrency  : ", concurrency)
    print("Starting date: ", datetime.now().isoformat())

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

    # create a ChessDB
    chessdb = ChessDB(
        concurrency=concurrency,
        evalDecay=evalDecay,
        cursedWins=cursedWins,
        rootBoard=board.copy(),
    )

    depth = 1
    while depthLimit is None or depth <= depthLimit:
        print("Search at depth ", depth)
        chessdb.add_cdb_pv_positions(board.epd())
        print("  cdb PV len: ", chessdb.cdbPvToLeaf.get(board.epd(), 0), flush=True)
        bestscore, pv = chessdb.search(board, depth)
        if pv[-1] in ["checkmate", "draw", "invalid"]:
            pvlen = len(pv) - 1
            if pv[-1] == "checkmate":
                if chessdb.pv_has_proven_mate(board.epd(), pv):
                    pv[-1] = "CHECKMATE"
        else:
            pvlen = len(pv)
        runtime = time.perf_counter() - chessdb.count_starttime
        queryall = chessdb.count_queryall.get()
        print("  score     : ", bestscore)
        print("  PV        : ", " ".join(pv))
        print("  PV len    : ", pvlen)
        if queryall:
            print("  queryall  : ", queryall)
            print(f"  bf        :  { queryall**(1/depth) :.2f}")
            print(
                f"  inflight  : { chessdb.count_sumInflightRequests.get() / queryall : .2f}"
            )
            print("  chessdbq  : ", chessdb.count_uncached.get())
            print("  enqueued  : ", chessdb.count_enqueued.get())
            print("  unscored  : ", chessdb.count_unscored.get())
            print("  date      : ", datetime.now().isoformat())
            timestr = str(timedelta(seconds=int(100 * runtime) / 100))
            print("  total time: ", timestr[: -4 if "." in timestr else None])
            print(
                "  req. time : ",
                int(1000 * runtime / chessdb.count_uncached.get()),
            )

        pvline = " ".join(epdMoves + pv[:pvlen])
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
    argParser.add_argument(
        "--cursedWins",
        action="store_true",
        help="Treat cursed wins as wins.",
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
        cursedWins=args.cursedWins,
    )
