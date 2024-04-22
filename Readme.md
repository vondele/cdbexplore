# Explore and extend the Chess Cloud Database 

Explores and searches [chessdb.cn](https://chessdb.cn/queryc_en/), the largest online database (db) of chess positions and openings.

## Purpose

Build a search tree from a particular position, using a mini-max like algorithm,
finding the best line, extending the db as needed.

Using some concurrency, fairly deep exploration is quickly possible.

## `cdbsearch`

This is a command line program to explore a single position.

```
usage: cdbsearch.py [-h] [--epd EPD | --san SAN] [--depthLimit DEPTHLIMIT] [--timeLimit TIMELIMIT] [--concurrency CONCURRENCY] [--evalDecay EVALDECAY] [--cursedWins] [--TBsearch] [--proveMates] [--user USER]

Explore and extend the Chess Cloud Database (https://chessdb.cn/queryc_en/). Builds a search tree for a given position.

options:
  -h, --help            show this help message and exit
  --epd EPD             EPD/FEN to explore: acceptable are FENs w/ and w/o move counters, as well as the extended "moves m1 m2 m3" syntax from cdb's API. (default: rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - moves g2g4)
  --san SAN             Moves in SAN notation that lead to the position to be explored. E.g. "1. g4". (default: None)
  --depthLimit DEPTHLIMIT
                        Finish the exploration at the specified depth. (default: None)
  --timeLimit TIMELIMIT
                        Do not start a search at higher depth if this limit (in seconds) is exceeded. (default: None)
  --concurrency CONCURRENCY
                        Concurrency of requests. This is the maximum number of requests made to chessdb at the same time. (default: 16)
  --evalDecay EVALDECAY
                        Depth decrease per cp eval-to-best. A small number will use a very narrow search, 0 will essentially just follow PV lines. A wide search will likely enqueue many positions. (default: 2)
  --cursedWins          Treat cursed wins as wins. (default: False)
  --TBsearch            Extend the searching and exploration of lines into cdb's EGTB. (default: False)
  --proveMates          Attempt to prove that mate PV lines have no better defence. Proven mates are indicated with "CHECKMATE" at the end of the PV, whereas unproven ones use "checkmate". (default: False)
  --user USER           Add this username to the http user-agent header. (default: None)
``` 

Sample output:

```
Search at depth  8
  cdb PV len:  70
  score     :  143
  PV        :  d7d5 e2e3 b8c6 d2d4 e7e5 b1c3 c8e6 d4e5 c6e5 h2h3 h7h5 g1f3 e5f3 d1f3 h5g4 h3g4 e6g4 f3g2 h8h1 g2h1 g8f6 c1d2 d8d6 c3b5 d6b6 f2f3 a7a6 b5c3 g4f5
  PV len    :  29
  level     :  39
  max level :  47
  queryall  :  1596
  bf        :  2.51
  chessdbq  :  578 (36.22% of queryall)
  enqueued  :  8
  requeued  :  0
  unscored  :  0 (0.00% of enqueued)
  reprobed  :  75 (12.98% of chessdbq)
  inflightQ :  26.69
  inflightR :  8.21
  cdb time  :  223
  date      :  2023-06-21T08:17:28.101875
  total time:  0:02:09.36
  URL       :  https://chessdb.cn/queryc_en/?rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR_w_KQkq_-_moves_g2g4_d7d5_e2e3_b8c6_d2d4_e7e5_b1c3_c8e6_d4e5_c6e5_h2h3_h7h5_g1f3_e5f3_d1f3_h5g4_h3g4_e6g4_f3g2_h8h1_g2h1_g8f6_c1d2_d8d6_c3b5_d6b6_f2f3_a7a6_b5c3_g4f5
```

Meaning of the fields:

```
cdb PV len : Current length of the PV for this position in cdb in plies.
score      : The standard minimax score found, not using the decay that cdb implements.
PV         : Best line found.
PV len     : Length of this PV line in plies.
level      : Deepest level in search tree reached in the last completed search.
max level  : Deepest level in search tree reached in all the searches so far.
queryall   : Number of positions visited in the search tree, with results provided by cdb or the local cache.
bf         : Branching factor q^(1/d) computed from queryall q and depth d.
chessdbq   : Number of positions requested to cdb.
enqueued   : Number of positions that did not exist within cdb but have been added as part of the search.
requeued   : Number of positions that were re-queued to prompt cdb to provide at least 5 scored moves.
unscored   : Number of existing unscored moves within cdb that were assigned a score as part of the search.
reprobed   : Number of positions in local PV lines re-requested to cdb.
inflightQ  : Number of concurrent queries, guaranteed to return scored moves, made to cdb on average.
inflightR  : Number of concurrent http requests made to chessdb.cn on average.
cdb time   : Average time (in milliseconds) needed to get a cdb list of moves for a position (including those that required enqueuing).
date       : ... you guessed it
total time : Time spent since the start of the search.
URL        : Link displaying the found PV on chessdb.cn.
```

Sample output with `--proveMates`:

```
> python cdbsearch.py --epd "3r4/3N2kr/1p6/pBpn1p2/Q2PR1p1/P7/1P4P1/2q3K1 w - -" --depthLimit 1 --evalDecay 0 --proveMates
Root position:  3r4/3N2kr/1p6/pBpn1p2/Q2PR1p1/P7/1P4P1/2q3K1 w - -
evalDecay    :  0
Concurrency  :  16
Prove Mates  :  True
Starting date:  2023-06-18T18:58:14.335194
Search at depth  1
  cdb PV len:  10
  score     :  -29990
  PV        :  a4d1 c1d1 g1f2 f5e4 b5a6 h7h1 a6f1 d1d2 f2g3 d2f4 CHECKMATE (#-5)
  PV len    :  10
  level     :  10
  max level :  10
  queryall  :  1504
  bf        :  1504.00
  chessdbq  :  1117 (74.27% of queryall)
  enqueued  :  0
  requeued  :  0
  unscored  :  0 (0.00% of enqueued)
  reprobed  :  10 (0.90% of chessdbq)
  inflightQ :  9.22
  inflightR :  2.61
  cdb time  :  117
  date      :  2023-06-18T19:00:25.868435
  total time:  0:02:11.53
  URL       :  https://chessdb.cn/queryc_en/?3r4/3N2kr/1p6/pBpn1p2/Q2PR1p1/P7/1P4P1/2q3K1_w_-_-_moves_a4d1_c1d1_g1f2_f5e4_b5a6_h7h1_a6f1_d1d2_f2g3_d2f4
```

## `cdbbulksearch`

This is a command line program to sequentially explore several positions.

```
usage: cdbbulksearch.py [-h] [--plyBegin PLYBEGIN] [--plyEnd PLYEND] [--shuffle] [--depthLimit DEPTHLIMIT] [--timeLimit TIMELIMIT] [--concurrency CONCURRENCY] [--evalDecay EVALDECAY] [--cursedWins] [--TBsearch] [--proveMates] [--user USER] [--bulkConcurrency BULKCONCURRENCY] [--forever] [--maxDepthLimit MAXDEPTHLIMIT] [--reload] filename

Invoke cdbsearch for positions loaded from a file.

positional arguments:
  filename              PGN file if suffix is .pgn(.gz), o/w a file with FENs/EPDs. The latter may use the extended "moves m1 m2 m3" syntax from cdb's API.

options:
  -h, --help            show this help message and exit
  --plyBegin PLYBEGIN   Ply in each line of filename from which positions will be searched by cdbsearch. A value of 0 corresponds to the starting FEN without any moves played. Negative values count from the back, as per the Python standard. (default: -1)
  --plyEnd PLYEND       Ply in each line of filename until which positions will be searched by cdbsearch. A value of None means including the final move of the line. (default: None)
  --shuffle             Shuffle the positions to be searched randomly. (default: False)
  --depthLimit DEPTHLIMIT
                        Argument passed to cdbsearch. (default: 5)
  --timeLimit TIMELIMIT
                        Argument passed to cdbsearch. (default: None)
  --concurrency CONCURRENCY
                        Argument passed to cdbsearch. (default: 16)
  --evalDecay EVALDECAY
                        Argument passed to cdbsearch. (default: 2)
  --cursedWins          Argument passed to cdbsearch. (default: False)
  --TBsearch            Argument passed to cdbsearch. (default: False)
  --proveMates          Argument passed to cdbsearch. (default: False)
  --user USER           Argument passed to cdbsearch. (default: None)
  --bulkConcurrency BULKCONCURRENCY
                        Number of concurrent processes running cdbsearch. (default: 4)
  --forever             Pass positions from filename to cdbsearch in an infinite loop, increasing depthLimit by one after each completed cycle. (default: False)
  --maxDepthLimit MAXDEPTHLIMIT
                        Upper bound for dynamically increasing depthLimit. (default: None)
  --reload              Reload positions from filename when tasks for new cycle are needed. (default: False)

```

Example:
```shell
echo -e '[Event "*"]\n\n1. g4 *\n\n1. g4 d5 *\n' > book.pgn
git clone https://github.com/vondele/cdbexplore && pip install -r cdbexplore/requirements.txt
python3 cdbexplore/cdbbulksearch.py book.pgn --forever >& cdbsearch_book.log &
```

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
