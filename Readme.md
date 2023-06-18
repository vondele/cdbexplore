# Explore and extend the Chess Cloud Database 

Explores and searches [chessdb.cn](https://chessdb.cn/queryc_en/), the largest online database (db) of chess positions and openings.

## Purpose

Build a search tree from a particular position, using a mini-max like algorithm,
finding the best line, extending the db as needed.

Using some concurrency, fairly deep exploration is quickly possible.

## `cdbsearch`

This is a command line program to explore a single position.

```
usage: cdbsearch.py [-h] [--epd EPD | --san SAN] [--depthLimit DEPTHLIMIT] [--concurrency CONCURRENCY] [--evalDecay EVALDECAY] [--cursedWins] [--proveMates] [--user USER]

Explore and extend the Chess Cloud Database (https://chessdb.cn/queryc_en/). Builds a search tree for a given position.

options:
  -h, --help            show this help message and exit
  --epd EPD             EPD/FEN to explore: acceptable are FENs w/ and w/o move counters, as well as the extended "moves m1 m2 m3" syntax from cdb's API. (default: rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - moves g2g4)
  --san SAN             Moves in SAN notation that lead to the position to be explored. E.g. "1. g4". (default: None)
  --depthLimit DEPTHLIMIT
                        Finish the exploration at the specified depth. (default: None)
  --concurrency CONCURRENCY
                        Concurrency of requests. This is the maximum number of http requests made to chessdb at the same time. (default: 16)
  --evalDecay EVALDECAY
                        Depth decrease per cp eval-to-best. A small number will use a very narrow search, 0 will essentially just follow PV lines. A wide search will likely enqueue many positions. (default: 2)
  --cursedWins          Treat cursed wins as wins. (default: False)
  --proveMates          Attempt to prove that mate PV lines have no better defence. Proven mates are indicated with "CHECKMATE" at the end of the PV, whereas unproven ones use "checkmate". (default: False)
  --user USER           Add this username to the http user-agent header. (default: None)
``` 

Sample output:

```
Search at depth  12
  cdb PV len:  39
  score     :  141
  PV        :  d7d5 e2e3 b8c6 f1e2 e7e5 d2d4 h7h5 g4g5 d8g5 g1f3 g5g6 d4e5 c8g4 h1g1 g6e6 b1d2 g8h6 f3d4 e6e5 d2f3 e5f6 d4c6 f6c6 d1d4 f7f6
  PV len    :  25
  level     :  68
  max level :  84
  queryall  :  6830
  bf        :  1.14
  chessdbq  :  2020 (29.58% of queryall)
  enqueued  :  47
  unscored  :  0 (0.00% of enqueued)
  reprobed  :  163 (8.07% of chessdbq)
  inflightQ :  80.27
  inflightR :  10.56
  cdb time  :  120
  date      :  2023-06-18T18:56:24.547853
  total time:  0:04:03.78
  URL       :  https://chessdb.cn/queryc_en/?rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR_w_KQkq_-_moves_g2g4_d7d5_e2e3_b8c6_f1e2_e7e5_d2d4_h7h5_g4g5_d8g5_g1f3_g5g6_d4e5_c8g4_h1g1_g6e6_b1d2_g8h6_f3d4_e6e5_d2f3_e5f6_d4c6_f6c6_d1d4_f7f6
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
bf         : Branching factor q^(1/(l+1)) computed from queryall q and level l.
chessdbq   : Number of positions requested to cdb.
enqueued   : Number of positions that did not exist within cdb but have been added as part of the search.
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
  bf        :  1.94
  chessdbq  :  1117 (74.27% of queryall)
  enqueued  :  0
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
usage: cdbbulksearch.py [-h] [--plyBegin PLYBEGIN] [--plyEnd PLYEND] [--shuffle] [--depthLimit DEPTHLIMIT] [--concurrency CONCURRENCY] [--evalDecay EVALDECAY] [--cursedWins] [--proveMates] [--user USER] [--bulkConcurrency BULKCONCURRENCY] [--forever] [--reload] filename

Invoke cdbsearch for positions loaded from a file.

positional arguments:
  filename              PGN file if suffix is .pgn, o/w a text file with FENs/EPDs. The latter may use the extended "moves m1 m2 m3" syntax from cdb's API.

options:
  -h, --help            show this help message and exit
  --plyBegin PLYBEGIN   Ply in each line of filename from which positions will be searched by cdbsearch. A value of 0 corresponds to the starting FEN without any moves played. Negative values count from the back, as per the Python standard. (default: -1)
  --plyEnd PLYEND       Ply in each line of filename until which positions will be searched by cdbsearch. A value of None means including the final move of the line. (default: None)
  --shuffle             Shuffle the positions to be searched randomly. (default: False)
  --depthLimit DEPTHLIMIT
                        Argument passed to cdbsearch. (default: 5)
  --concurrency CONCURRENCY
                        Argument passed to cdbsearch. (default: 16)
  --evalDecay EVALDECAY
                        Argument passed to cdbsearch. (default: 2)
  --cursedWins          Argument passed to cdbsearch. (default: False)
  --proveMates          Argument passed to cdbsearch. (default: False)
  --user USER           Argument passed to cdbsearch. (default: None)
  --bulkConcurrency BULKCONCURRENCY
                        Number of concurrent processes running cdbsearch. (default: 4)
  --forever             Pass positions from filename to cdbsearch in an infinite loop, increasing depthLimit by one after each completed cycle. (default: False)
  --reload              Reload positions from filename when tasks for new cycle are needed. (default: False)
```

Example:
```shell
echo '[Event "*"]\n\n1. g4 *\n\n1. g4 d5 *\n' > book.pgn
git clone https://github.com/vondele/cdbexplore && pip install -r cdbexplore/requirements.txt
python3 cdbexplore/cdbbulksearch.py book.pgn --forever >& cdbsearch_book.log &
```

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
