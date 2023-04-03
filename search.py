import queue
import requests
import time
import chess
import argparse
import functools
import math
from urllib import parse


def timer(func):
    @functools.wraps(func)
    def wrapper_timer(*args, **kwargs):
        tic = time.perf_counter()
        value = func(*args, **kwargs)
        toc = time.perf_counter()
        elapsed_time = toc - tic
        print(f"Elapsed time: {elapsed_time:0.4f} seconds")
        return value

    return wrapper_timer


class ChessDB:
    def reset_counts(self):
        self.count_queryall = 0
        self.count_uncached = 0
        self.count_enqueued = 0
        self.count_timeneeded = 0

    def __init__(self):
        self.session = requests.Session()
        self.cache = {}
        self.reset_counts()

    def queryall(self, epd):
        """query chessdb until scored moves come back"""

        self.count_queryall += 1

        if epd in self.cache:
            return self.cache[epd]

        tic = time.perf_counter()
        self.count_uncached += 1

        api = "http://www.chessdb.cn/cdb.php"
        timeout = 10
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
                    print("Failed to get reply for: ", epd, " last error: ", lasterror)
                time.sleep(timeout)
            else:
                first = False

            url = api + "?action=queryall&board=" + parse.quote(epd) + "&json=1"
            try:
                response = self.session.get(url, timeout=timeout)
                response.raise_for_status()
                content = response.json()
            except Exception:
                lasterror="Something went wrong with queryall"
                continue

            if "status" not in content:
                lasterror="Malformed reply, not containing status"
                continue

            if content["status"] == "unknown":
                # unknown position, queue and see again
                if not enqueued:
                   enqueued = True
                   self.count_enqueued += 1

                url = api + "?action=queue&board=" + parse.quote(epd) + "&json=1"
                try:
                    response = self.session.get(url, timeout=timeout)
                    response.raise_for_status()
                    content = response.json()
                except Exception:
                    lasterror="Something went wrong with queue"
                    continue

                lasterror="Enqueued position"
                continue

            elif content["status"] == "rate limit exceeded":
                # special case, request to clear the limit
                url = api + "?action=clearlimit"
                try:
                    response = self.session.get(url, timeout=timeout)
                    response.raise_for_status()
                except Exception:
                    pass
                lasterror="asked to clearlimit"
                continue

            elif content["status"] == "ok":
                found = True
                if "moves" in content:
                    for m in content["moves"]:
                        result[m["uci"]] = m["score"]
                else:
                    lasterror="Unexpectedly missing moves"
                    continue

            elif content["status"] == "checkmate" or content["status"] == "stalemate":
                found = True

            else:
                lasterror="Surprise reply"
                continue

        self.cache[epd] = result
        toc = time.perf_counter()
        self.count_timeneeded += toc - tic

        return result

    def search(self, board, depth):

        if board.is_checkmate():
           return (-40000, [None])

        if board.is_stalemate() or board.is_insufficient_material() or board.can_claim_draw():
           return (0, [None])

        # get current ranking
        scored_db_moves = self.queryall(board.epd())

        bestscore = -40001
        bestmove = None

        for m in scored_db_moves:
            if m == "depth":
               continue
            s = scored_db_moves[m]
            if s > bestscore:
               bestscore = s
               bestmove = m

        if depth <= scored_db_moves["depth"]:
           return (bestscore, [bestmove])

        newly_scored_moves = {"depth" : depth}

        minicache = {}
        newmoves = 0
        for move in board.legal_moves:
            ucimove = move.uci()
            indb = ucimove in scored_db_moves
            if indb:
               # decrement depth for moves
               newdepth = depth + (scored_db_moves[ucimove] - bestscore) // 3 - 1 
            else:
               newmoves += 1
               newdepth = depth - 5 - len(scored_db_moves) - newmoves

            if newdepth >= 0:
               board.push(move)
               s, pv = self.search(board, newdepth)
               minicache[ucimove] = [ucimove] + pv
               newly_scored_moves[ucimove] = -s
               board.pop()
            elif indb:
               newly_scored_moves[ucimove] = scored_db_moves[ucimove]
               minicache[ucimove] = [ucimove]

        self.cache[board.epd()] = newly_scored_moves

        bestscore = -40001
        bestmove = None

        for m in newly_scored_moves:
            if m == "depth":
               continue
            s = newly_scored_moves[m]
            if s > bestscore or (s == bestscore and len(minicache[m]) > len(minicache[bestmove])):
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
    args = argParser.parse_args()
    epd = args.epd

    # create a ChessDB
    chessdb = ChessDB()

    # set initial board
    board = chess.Board(epd)
    depth = 1
    while True:
       bestscore, pv = chessdb.search(board, depth)
       pvline = ""
       for m in pv:
           pvline += m + " "
       print( "Search at depth ", depth)
       print( "  score     : ", bestscore)
       print( "  PV        : ", pvline)
       print( "  queryall  : ", chessdb.count_queryall)
       print( "  chessdbq  : ", chessdb.count_uncached)
       print( "  enqueued  : ", chessdb.count_enqueued)
       print( "  total time: ", int(1000 * chessdb.count_timeneeded))
       print( "  req. time : ", int(1000 * chessdb.count_timeneeded / chessdb.count_uncached))
       print(f'  bf        :  { math.exp(math.log(chessdb.count_queryall)/depth) :.2f}')
       depth += 1
