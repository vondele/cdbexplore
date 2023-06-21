import argparse, asyncio, requests, time, threading, concurrent.futures
import chess, chess.pgn
from io import StringIO
from datetime import datetime, timedelta
from multiprocessing import freeze_support

# current conventions on chessdb.cn
CDB_MATE = 30000  # score for mates
CDB_TBWIN = 25000  # score for TBwins
CDB_CURSED = 20000  # score for cursed wins
CDB_SPECIAL = 10000  # assumed strict upper bound for material scores
CDB_EGTB = 7  # maximum number of pieces for wdl and dtz EGTB's
CDB_SIEVED = 5  # minimum number of scored moves for an analysed position

# some (depth) constants that trigger certain events in search
depthForceQuery = 10  # force queryall if unscored moves exist and depth exceeds this
depthAllowExts = 4  # allow extension of the unique bestmove if depth exceeds this
depthMaxExtension = 10  # maximum number of extensions allowed in a non-PV line
depthUnscored = 25  # score an unscored move if depth - scoredCount exceeds this
depthReprobePV = 16  # do not call reprobe_PV when depth is smaller than this
percentReprobePV = 1  # % of queryall API calls we are willing to use for reprobe_PV


class AtomicTT:
    def __init__(self):
        self._lock = threading.Lock()
        self._cache = {}

    def get(self, epd):
        with self._lock:
            return self._cache.get(epd)

    def set(self, epd, result):
        with self._lock:
            value = self._cache.get(epd)
            if value is None or value["depth"] <= result["depth"]:
                self._cache[epd] = result
                return result
            return value


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
        self,
        concurrency,
        evalDecay,
        cursedWins=False,
        TBsearch=False,
        rootBoard=chess.Board(),
        user=None,
    ):
        # user defined parameters
        self.concurrency = concurrency
        self.evalDecay = evalDecay
        self.cursedWins = cursedWins
        self.TBsearch = TBsearch
        self.user = "" if user is None else str(user)

        # the board containing as final leaf(!) the root position under which the tree will be built
        self.rootBoard = rootBoard

        # some counters that will be accessed by multiple threads
        self.count_queryall = AtomicInteger()
        self.count_uncached = AtomicInteger()
        self.count_enqueued = AtomicInteger()
        self.count_requeued = AtomicInteger()
        self.count_unscored = AtomicInteger()
        self.count_inflightRequests = AtomicInteger()
        self.count_sumInflightRequests = AtomicInteger()
        self.count_inflightUncached = AtomicInteger()
        self.count_sumInflightUncached = AtomicInteger()
        self.count_reprobeQueryall = AtomicInteger()

        # for timing output
        self.count_starttime = time.perf_counter()

        # use a session to keep alive the connection to the server
        self.session = requests.Session()

        # our dictionary to cache intermediate results
        self.TT = AtomicTT()

        # a dictionary storing the distance to leaf for positions on cdb PVs
        self.cdbPvToLeaf = {}

        # a semaphore to limit the number of concurrent accesses to the API
        self.semaphoreWork = asyncio.Semaphore(self.concurrency)

        # a thread pool to do some of the blocking IO (TODO: look into aiohttp)
        self.executorWork = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.concurrency
        )

        # a list of semaphores to limit the number of concurrent tasks on each level of the search tree
        self.semaphoreTree = []

    def __apicall(self, url, timeout):
        """our blocking apicall, not to be called directly"""
        self.count_inflightRequests.inc()
        try:
            response = self.session.get(
                url,
                timeout=timeout,
                headers={"user-agent": "cdbsearch" + bool(self.user) * "/" + self.user},
            )
            response.raise_for_status()
            content = response.json()
        except Exception:
            content = None
        self.count_inflightRequests.dec()
        return content

    async def __cdbapicall(self, action, timeout=15):
        """co-routine to access the API"""
        async with self.semaphoreWork:
            return await asyncio.get_running_loop().run_in_executor(
                self.executorWork,
                self.__apicall,
                "http://www.chessdb.cn/cdb.php" + action,
                timeout,
            )

    async def add_cdb_pv_positions(self, epd):
        """query cdb for the PV of the position and create a dictionary containing these positions and their distance to the PV leaf for extensions during search"""
        content = await self.__cdbapicall(f"?action=querypv&board={epd}&json=1")
        if content and content.get("status") == "ok" and "pv" in content:
            pv = content["pv"]
            self.cdbPvToLeaf[epd] = len(pv)
            asyncio.ensure_future(self.queryall(epd))
            board = chess.Board(epd)
            for parsed, ucimove in enumerate(pv):
                board.push(chess.Move.from_uci(ucimove))
                self.cdbPvToLeaf[board.epd()] = len(pv) - 1 - parsed
                asyncio.ensure_future(self.queryall(board.epd()))

    async def obtain_PV(self, board, depth):
        """obtain the PV line for position on board, to the specified depth"""
        t = self.check_trivial_PV(board)
        if t is not None:
            return t[1]
        scored_db_moves = await self.queryall(board.epd())
        if scored_db_moves == {}:
            return ["invalid"]
        if depth == 0:
            return []
        bestmove, _ = max(
            [t for t in scored_db_moves.items() if t[0] != "depth"],
            key=lambda t: t[1],
        )
        board.push(chess.Move.from_uci(bestmove))
        # we walk along a single PV line with board, so no need to create a copy for the recursive call
        return [bestmove] + await self.obtain_PV(board, depth - 1)

    async def pv_has_proven_mate(self, board, pv):
        """check if the PV line is a proven mate on cdb, and if not help prove it"""
        if not pv or pv[-1] != "checkmate":
            return False
        if pv == ["checkmate"]:
            return True
        # now pv is a list of moves, with pv[-2] the mating move, and pv[-1] == "checkmate"
        if len(pv) % 2 == 0:  # we just need to check the defender's moves
            board.push(chess.Move.from_uci(pv[0]))
            return await self.pv_has_proven_mate(board.copy(), pv[1:])

        scored_db_moves = await self.queryall(board.epd())
        if len(scored_db_moves) - 1 < len(list(board.legal_moves)):
            # there are unscored moves: help to construct a proof by querying all of them
            for move in board.legal_moves:
                if move.uci() not in scored_db_moves:
                    board.push(move)
                    asyncio.ensure_future(self.queryall(board.epd()))
                    self.count_unscored.inc()
                    board.pop()
            return False

        # we need to check if the _given_ PV is a correct mating line (once again just checking the defender's moves)
        for ucimove in pv[:2]:
            board.push(chess.Move.from_uci(ucimove))
        if not await self.pv_has_proven_mate(board.copy(), pv[2:]):
            return False
        for _ in [0, 1]:
            board.pop()

        tasks = []
        # now we check if all the currently non-best moves also inevitably lead to the defender being mated (in at most the claimed number of moves)
        for ucimove in [m for m in scored_db_moves if m != "depth" if m != pv[0]]:
            # we schedule the proofs for all the alternative defending moves in parallel
            board.push(chess.Move.from_uci(ucimove))
            # the list pv contains "checkmate", so mate must be delivered in len(pv) - 2 plies
            mpv = await self.obtain_PV(board.copy(), len(pv) - 2)
            tasks.append(
                asyncio.create_task(self.pv_has_proven_mate(board.copy(), mpv))
            )
            board.pop()

        # if any of the possible defences does _not_ lead to a mate, the proof breaks down
        for pv_has_proven_mate in tasks:
            if not await pv_has_proven_mate:
                return False

        return True

    async def queryall(self, epd, skipTT=False):
        """query chessdb until scored moves come back"""

        # book keeping of calls and average in flight requests.
        self.count_queryall.inc()

        # see if we can return this result from the TT, else retrieve from chessdb
        if not skipTT:
            result = self.TT.get(epd)
            if result is not None:
                return result

        self.count_uncached.inc()
        self.count_sumInflightRequests.inc(self.count_inflightRequests.get())
        self.count_inflightUncached.inc()
        self.count_sumInflightUncached.inc(self.count_inflightUncached.get())

        timeout = 5
        found = enqueued = False
        first = True
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
                await asyncio.sleep(timeout)
            else:
                first = False

            content = await self.__cdbapicall(
                f"?action=queryall&board={epd}&json=1", timeout
            )

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

                content = await self.__cdbapicall(
                    f"?action=queue&board={epd}&json=1", timeout
                )
                if content is None:
                    lasterror = "Something went wrong with queue"
                    continue

                if content == {}:
                    # the position is not available in cdb (EGTB w/ castling rights) - score all moves as 1cp, and let search figure it out
                    found = True
                    board = chess.Board(epd)
                    for move in board.legal_moves:
                        result[move.uci()] = 1  # we reserve 0 for EGTB draws
                    lasterror = "Position not queued"
                    continue

                lasterror = "Enqueued position"
                continue

            elif content["status"] == "rate limit exceeded":
                # special case, request to clear the limit
                await self.__cdbapicall("?action=clearlimit", timeout)
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
                except Exception:
                    # we do not trust possibly partial move information
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

        self.count_inflightUncached.dec()
        # set and return a possibly even deeper result
        return self.TT.set(epd, result)

    async def reprobe_PV(self, board, pv):
        """query all positions along the PV, starting from its leaf and all the way back to the start position of rootBoard"""
        for ucimove in pv[: -1 if pv[-1] in ["checkmate", "draw", "EGTB"] else None]:
            board.push(chess.Move.from_uci(ucimove))
        while board.move_stack:
            await self.queryall(board.epd(), skipTT=True)
            self.count_reprobeQueryall.inc()
            board.pop()

    def move_depth(self, bestscore, worstscore, score, depth):
        """returns depth - 1 for bestmove and negative values for bad moves, terminating their search; unscored moves are treated worse than worstmove, returning at most 0"""
        delta = score - bestscore if score is not None else worstscore - bestscore
        decay = delta // self.evalDecay if self.evalDecay != 0 else 10**6 * delta
        return depth + decay - 1 if score is not None else min(0, depth + decay - 2)

    def check_trivial_PV(self, board):
        if board.is_checkmate():
            return -CDB_MATE, ["checkmate"]
        if (
            board.is_stalemate()
            or board.is_insufficient_material()
            or board.can_claim_draw()
        ):
            return 0, ["draw"]
        return None

    async def search(self, board, depth):
        """returns (bestscore, pv, maxLevel) for current position stored in board"""

        # the level of the search tree we are in, i.e. how many plies we are away from rootBoard
        level = len(board.move_stack) - len(self.rootBoard.move_stack)

        t = self.check_trivial_PV(board)
        if t is not None:
            return t[0], t[1], level

        epd = board.epd()
        # get current ranking
        scored_db_moves = await self.queryall(epd)
        if scored_db_moves == {}:
            return 0, ["invalid"], level

        # stop search if we are in EGTB and know the result
        if (
            not self.TBsearch
            and sum(p in "pnbrqk" for p in epd.lower().split()[0]) <= CDB_EGTB
        ):
            bestmove, bestscore = max(
                [t for t in scored_db_moves.items() if t[0] != "depth"],
                key=lambda t: t[1],
            )
            # if bestscore is 1 or -1, we have a TB position with castling rights: continue the search
            if abs(bestscore) != 1:
                if abs(bestscore) > CDB_SPECIAL:
                    bestscore -= 1 if bestscore > 0 else -1
                return bestscore, [bestmove, "EGTB"], level

        scoredCount = len(scored_db_moves) - 1  # number of scored moves for board
        movesCount = len(list(board.legal_moves))  # numer of legal moves
        missingCDBmoves = scoredCount < min(CDB_SIEVED, movesCount)

        # for positions with an incomplete move list, we schedule a queue API call, since querall for positions beyond cdb's old piece count limit may not be enough to add new moves
        if missingCDBmoves:
            asyncio.ensure_future(
                self.__cdbapicall(f"?action=queue&board={epd}&json=1", timeout=60)
            )
            self.count_requeued.inc()

        # force a query for high depth nodes that do not have a full list of scored moves: we use this to add newly scored moves to our TT
        skipTT_db_moves = None
        if (depth > depthForceQuery and scoredCount < movesCount) or missingCDBmoves:
            skipTT_db_moves = asyncio.create_task(self.queryall(epd, skipTT=True))

        bestscore = -(CDB_MATE + 1)
        bestmove = None
        worstscore = CDB_MATE + 1

        for m, s in [t for t in scored_db_moves.items() if t[0] != "depth"]:
            if s > bestscore:
                bestmove, bestscore = m, s
            if s < worstscore:
                worstscore = s

        moves_to_search = 0
        for move in board.legal_moves:
            score = scored_db_moves.get(move.uci())
            newdepth = self.move_depth(bestscore, worstscore, score, depth)
            if newdepth >= 0:
                moves_to_search += 1

        newly_scored_moves = {"depth": depth}
        minicache = {}  # store candidate PVs for all newly scored moves
        tasks = {}
        allowUnscored = scoredCount >= CDB_SIEVED  # allow search of unscored moves
        allowMaxExtension = True

        # guarantee sufficient length of the semaphoreTree list, and limit the number of threads that can be created at each level of the search tree
        while len(self.semaphoreTree) < level + 1:
            self.semaphoreTree.append(asyncio.Semaphore(4 * self.concurrency))

        async with self.semaphoreTree[level]:
            for move in board.legal_moves:
                ucimove = move.uci()
                score = scored_db_moves.get(ucimove)
                newdepth = self.move_depth(bestscore, worstscore, score, depth)

                # extension if the unique bestmove is the only move to be searched deeper or the position is in the cdb PV
                if score == bestscore:
                    cdbPvToLeaf = self.cdbPvToLeaf.get(epd)
                    if (moves_to_search == 1 and depth > depthAllowExts) or (
                        cdbPvToLeaf is not None and newdepth < cdbPvToLeaf
                    ):
                        newdepth += 1

                # no extensions beyond depthMaxExtension, unless we are in PV line
                if newdepth >= 0 and level >= self.rootDepth + depthMaxExtension:
                    if not allowMaxExtension or score is None or score < bestscore:
                        newdepth = -1
                    else:
                        allowMaxExtension = False

                # schedule qualifying moves for deeper searches, at most 1 unscored move
                # for sufficiently large depth and suffiently small scoredCount we possibly schedule an unscored move
                if (newdepth >= 0 and (score is not None or allowUnscored)) or (
                    score is None
                    and allowUnscored
                    and depth - scoredCount > depthUnscored
                ):
                    board.push(move)
                    tasks[ucimove] = asyncio.create_task(
                        self.search(board.copy(), newdepth)
                    )
                    board.pop()
                    if score is None:
                        allowUnscored = False
                        self.count_unscored.inc()
                elif score is not None:
                    newly_scored_moves[ucimove] = scored_db_moves[ucimove]
                    minicache[ucimove] = [ucimove]

            maxLevel = level
            # get the results from the futures
            for ucimove, search in tasks.items():
                s, pv, l = await search
                newly_scored_moves[ucimove] = -s
                minicache[ucimove] = [ucimove] + pv
                maxLevel = max(maxLevel, l)

        # add potentially newly scored moves, or moves we have not explored by search
        if skipTT_db_moves:
            skipTT_db_moves = await skipTT_db_moves
            for move in board.legal_moves:
                ucimove = move.uci()
                skipTT_score = skipTT_db_moves.get(ucimove)
                if skipTT_score is not None:
                    newly_score = newly_scored_moves.get(ucimove)
                    if newly_score is None:
                        newly_scored_moves[ucimove] = skipTT_score
                        minicache[ucimove] = [ucimove]
                    elif newly_score != skipTT_score:
                        board.push(move)
                        if self.TT.get(board.epd()) is None:
                            newly_scored_moves[ucimove] = skipTT_score
                            minicache[ucimove] = [ucimove]
                        board.pop()

        # store our computed result
        self.TT.set(epd, newly_scored_moves)

        # find bestmove and associated PV
        bestscore = -(CDB_MATE + 1)
        for m, s in [t for t in newly_scored_moves.items() if t[0] != "depth"]:
            if s > bestscore or (
                s == bestscore and len(minicache[m]) > len(minicache[bestmove])
            ):
                bestmove, bestscore = m, s

        # in order to keep cdb up-to-date with possible progress we have made locally, we reprobe the found PV all the way back to the start position of rootBoard: but only if we would stay within the agreed percentage of queryall API calls
        if (
            depth >= depthReprobePV
            and self.count_reprobeQueryall.get()
            + len(board.move_stack)
            + len(minicache[bestmove])
            < self.count_uncached.get() * percentReprobePV / 100
        ):
            asyncio.ensure_future(self.reprobe_PV(board.copy(), minicache[bestmove]))

        # for lines leading to mates, TBwins and cursed wins we do not use mini-max, but rather store the distance in ply
        # this means local evals for such nodes will always be in sync with cdb
        if abs(bestscore) > CDB_SPECIAL:
            bestscore -= 1 if bestscore > 0 else -1

        return bestscore, minicache[bestmove], maxLevel


async def cdbsearch(
    epd,
    depthLimit,
    concurrency,
    evalDecay,
    cursedWins=False,
    TBsearch=False,
    proveMates=False,
    user=None,
):
    concurrency = max(1, concurrency)
    evalDecay = max(0, evalDecay)

    # basic output
    print("Root position: ", epd)
    print("evalDecay    : ", evalDecay)
    print("Concurrency  : ", concurrency)
    if user:
        print("User name    : ", user)
    if cursedWins:
        print("Cursed Wins  :  True")
    if TBsearch:
        print("TB search    :  True")
    if proveMates:
        print("Prove Mates  :  True")
    print("Starting date: ", datetime.now().isoformat())

    # set initial board, including the moves provided within epd
    if "moves" in epd:
        epd, _, epdMoves = epd.partition("moves")
        epdMoves = epdMoves.split()
    else:
        epdMoves = []
    epd = epd.strip()  # avoid leading and trailing spaces in URL below
    board = chess.Board(epd)
    for ucimove in epdMoves:
        board.push(chess.Move.from_uci(ucimove))

    # create a ChessDB
    chessdb = ChessDB(
        concurrency=concurrency,
        evalDecay=evalDecay,
        cursedWins=cursedWins,
        TBsearch=TBsearch,
        rootBoard=board.copy(),
        user=user,
    )

    depth = 1
    while depthLimit is None or depth <= depthLimit:
        print("Search at depth ", depth)
        await chessdb.add_cdb_pv_positions(board.epd())
        print("  cdb PV len: ", chessdb.cdbPvToLeaf.get(board.epd(), 0), flush=True)
        chessdb.rootDepth = depth
        bestscore, pv, level = await chessdb.search(board, depth)
        # always reprobe the root PV
        asyncio.ensure_future(chessdb.reprobe_PV(board.copy(), pv))
        print("  score     : ", bestscore)
        pvlen = len(pv) - (pv[-1] in ["checkmate", "draw", "EGTB", "invalid"])
        if proveMates and pv[-1] == "checkmate" and pvlen:
            print("  PV        : ", " ".join(pv[:-1]), end=" ", flush=True)
            if await chessdb.pv_has_proven_mate(board.copy(), pv):
                mStr = f"(#{(pvlen+1)//2})" if bestscore > 0 else f"(#-{pvlen//2})"
                print("CHECKMATE", mStr)
            else:
                print("checkmate")
        else:
            print("  PV        : ", " ".join(pv))
        print("  PV len    : ", pvlen)
        print("  level     : ", level)
        print("  max level : ", len(chessdb.semaphoreTree))
        queryall = chessdb.count_queryall.get()
        if queryall:
            uncached = chessdb.count_uncached.get()
            reprobed = chessdb.count_reprobeQueryall.get()
            enqueued = chessdb.count_enqueued.get()
            unscored = chessdb.count_unscored.get()
            runtime = time.perf_counter() - chessdb.count_starttime
            print("  queryall  : ", queryall)
            print(f"  bf        :  {queryall**(1/depth):.2f}")
            print(
                f"  chessdbq  :  {uncached} ({uncached / queryall * 100:.2f}% of queryall)"
            )
            print("  enqueued  : ", enqueued)
            print("  requeued  : ", chessdb.count_requeued.get())
            print(
                f"  unscored  :  {unscored} ({unscored / max(enqueued, 1) * 100:.2f}% of enqueued)"
            )
            uncached = max(uncached, 1)
            print(
                f"  reprobed  :  {reprobed} ({reprobed / uncached * 100:.2f}% of chessdbq)"
            )
            print(
                f"  inflightQ :  {chessdb.count_sumInflightUncached.get() / uncached:.2f}"
            )
            print(
                f"  inflightR :  {chessdb.count_sumInflightRequests.get() / uncached:.2f}"
            )
            print("  cdb time  : ", int(1000 * runtime / uncached))
            print("  date      : ", datetime.now().isoformat())
            timestr = str(timedelta(seconds=int(100 * runtime) / 100))
            print("  total time: ", timestr[: -4 if "." in timestr else None])

        pvline = " ".join(epdMoves + pv[:pvlen])
        if pvline:
            pvline = " moves " + pvline
        url = f"https://chessdb.cn/queryc_en/?{epd}{pvline}"
        print(f"  URL       :  {url.replace(' ', '_')}\n")
        depth += 1
        if pvlen == 0 or pvlen == 1 and pv[-1] == "EGTB":
            break  # nothing to be done


if __name__ == "__main__":
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
    argParser.add_argument(
        "--TBsearch",
        action="store_true",
        help="Extend the searching and exploration of lines into cdb's EGTB.",
    )
    argParser.add_argument(
        "--proveMates",
        action="store_true",
        help='Attempt to prove that mate PV lines have no better defence. Proven mates are indicated with "CHECKMATE" at the end of the PV, whereas unproven ones use "checkmate".',
    )
    argParser.add_argument(
        "--user",
        help="Add this username to the http user-agent header.",
    )
    args = argParser.parse_args()

    if args.san is not None:
        if args.san:
            game = chess.pgn.read_game(StringIO(args.san))
            epd = game.board().epd() + " moves"
            for move in game.mainline_moves():
                epd += f" {move}"
        else:
            epd = chess.STARTING_FEN  # passing empty string to --san gives startpos
    else:
        epd = args.epd

    asyncio.run(
        cdbsearch(
            epd=epd,
            depthLimit=args.depthLimit,
            concurrency=args.concurrency,
            evalDecay=args.evalDecay,
            cursedWins=args.cursedWins,
            TBsearch=args.TBsearch,
            proveMates=args.proveMates,
            user=args.user,
        )
    )
