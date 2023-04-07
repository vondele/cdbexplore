import queue
import requests
import time
import copy
import chess
import argparse
import functools
import math
import sys
import threading
import concurrent.futures
import multiprocessing
from urllib import parse
from datetime import datetime


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
        self.cache = {}

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

    def queryall(self, epd):
        """query chessdb until scored moves come back"""

        self.count_queryall.inc()
        self.count_sumInflightRequests.inc(self.count_inflightRequests.get())

        if epd in self.cache:
            return self.cache[epd]

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

            url = api + "?action=queryall&board=" + parse.quote(epd) + "&json=1"
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

                url = api + "?action=queue&board=" + parse.quote(epd) + "&json=1"
                content = self.__apicall(url, timeout)
                if content is None:
                    lasterror = "Something went wrong with queue"
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

            else:
                lasterror = "Surprise reply"
                continue

        self.cache[epd] = result

        return result

    def search(self, board, depth):

        if board.is_checkmate():
            return (-40000, [None])

        if (
            board.is_stalemate()
            or board.is_insufficient_material()
            or board.can_claim_draw()
        ):
            return (0, [None])

        # get current ranking, use an executor to limit total requests in flight
        scored_db_moves = self.executorWork.submit(self.queryall, board.epd()).result()

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

        if depth <= scored_db_moves["depth"]:
            return (bestscore, [bestmove])

        # guarantee sufficient depth of the executorTree list
        ply = board.ply()
        while len(self.executorTree) < ply + 1:
            self.executorTree.append(
                concurrent.futures.ThreadPoolExecutor(max_workers=self.concurrency)
            )

        newly_scored_moves = {"depth": depth}

        minicache = {}
        futures = {}
        newmoves = 0
        for move in board.legal_moves:
            ucimove = move.uci()
            indb = ucimove in scored_db_moves
            if indb:
                # decrement depth for moves
                if (scored_db_moves[ucimove] - bestscore) == 0:
                    decay = 0
                else:
                    decay = (
                        (scored_db_moves[ucimove] - bestscore) // self.evalDecay
                        if self.evalDecay != 0
                        else -100
                    )
                newdepth = depth + decay - 1
            else:
                newmoves += 1
                # new moves at most depth 0 search, and assume they are worse than the worst move so far.
                if (worstscore - bestscore) == 0:
                    decay = 0
                else:
                    decay = (
                        (worstscore - bestscore) // self.evalDecay
                        if self.evalDecay != 0
                        else -100
                    )
                newdepth = min(0, depth + decay - 1 - newmoves)

            if newdepth >= 0:
                board.push(move)
                futures[ucimove] = self.executorTree[ply].submit(
                    self.search, copy.deepcopy(board), newdepth
                )
                board.pop()
            elif indb:
                newly_scored_moves[ucimove] = scored_db_moves[ucimove]
                minicache[ucimove] = [ucimove]

        # get the results from the futures
        for ucimove in futures:
            s, pv = futures[ucimove].result()
            minicache[ucimove] = [ucimove] + pv
            newly_scored_moves[ucimove] = -s

        self.cache[board.epd()] = newly_scored_moves

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

        return (bestscore, minicache[bestmove])


if __name__ == "__main__":

    argParser = argparse.ArgumentParser()
    argParser.add_argument(
        "--epd",
        help="epd to explore",
        default="rnbqkbnr/ppp1pppp/8/3p4/6P1/8/PPPPPP1P/RNBQKBNR w KQkq d6",
    )
    argParser.add_argument(
        "--concurrency",
        help="concurrency of requests",
        type=int,
        default=16,
    )
    argParser.add_argument(
        "--evalDecay",
        help="depth decrease per cp eval-to-best",
        type=int,
        default=2,
    )
    args = argParser.parse_args()
    epd = args.epd

    # limit stack size of created threads, many are created
    stackSize = 4096 * 64
    threading.stack_size(stackSize)

    # basic output
    print("Searched epd : ", epd)
    print("evalDecay: ", args.evalDecay)
    print("Concurrency  : ", args.concurrency)
    print("Starting date: ", datetime.now().isoformat())

    # create a ChessDB
    chessdb = ChessDB(concurrency=args.concurrency, evalDecay=args.evalDecay)

    # set initial board
    board = chess.Board(epd)
    depth = 1
    while True:
        bestscore, pv = chessdb.search(board, depth)
        pvline = ""
        for m in pv:
            pvline += m + " "
        runtime = time.perf_counter() - chessdb.count_starttime
        print("Search at depth ", depth)
        print("  score     : ", bestscore)
        print("  PV        : ", pvline)
        print("  queryall  : ", chessdb.count_queryall.get())
        print(
            f"  bf        :  { math.exp(math.log(chessdb.count_queryall.get())/depth) :.2f}"
        )
        print(
            f"  inflight  : { chessdb.count_sumInflightRequests.get() / chessdb.count_queryall.get() : .2f}"
        )
        print("  chessdbq  : ", chessdb.count_uncached.get())
        print("  enqueued  : ", chessdb.count_enqueued.get())
        print("  date      : ", datetime.now().isoformat())
        print("  total time: ", int(1000 * runtime))
        print(
            "  req. time : ",
            int(1000 * runtime / chessdb.count_uncached.get()),
        )
        print("", flush=True)
        depth += 1
