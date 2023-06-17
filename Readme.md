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
Search at depth  10
  cdb PV len:  67
  score     :  138
  PV        :  d7d5 h2h3 h7h5 g4h5 e7e5 d2d3 b8c6 g1f3 h8h5 b1c3 g8f6 a2a3 f8e7 e2e4 d5e4
  PV len    :  15
  max ply   :  68
  queryall  :  2189
  bf        :  2.16
  chessdbq  :  578 (26.40% of queryall)
  enqueued  :  13
  requeued  :  4
  unscored  :  0 (0.00% of enqueued)
  reprobed  :  89 (15.40% of chessdbq)
  inflightQ :  19.87
  inflightR :  8.60
  cdb time  :  100
  date      :  2023-06-17T14:43:38.862147
  total time:  0:00:57.84
  URL       :  https://chessdb.cn/queryc_en/?rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR_w_KQkq_-_moves_g2g4_d7d5_h2h3_h7h5_g4h5_e7e5_d2d3_b8c6_g1f3_h8h5_b1c3_g8f6_a2a3_f8e7_e2e4_d5e4
```

Meaning of the fields:

```
cdb PV len : Current length of the PV for this position in cdb in plies.
score      : The standard minimax score found, not using the decay that cdb implements.
PV         : Best line found.
PV len     : Length of this PV line in plies.
max ply    : Length of the deepest line searched so far.
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
Starting date:  2023-06-17T14:44:32.611779
Search at depth  1
  cdb PV len:  10
  score     :  -29990
  PV        :  g1f2 f5e4 a4b3 h7h1 b3c3 d5c3 b5f1 c1f4 f2e1 f4e3 CHECKMATE (#-5)
  PV len    :  10
  max ply   :  10
  queryall  :  1315
  bf        :  1315.00
  chessdbq  :  1041 (79.16% of queryall)
  enqueued  :  0
  requeued  :  0
  unscored  :  0 (0.00% of enqueued)
  reprobed  :  10 (0.96% of chessdbq)
  inflightQ :  5.07
  inflightR :  2.74
  cdb time  :  136
  date      :  2023-06-17T14:46:54.857399
  total time:  0:02:22.24
  URL       :  https://chessdb.cn/queryc_en/?3r4/3N2kr/1p6/pBpn1p2/Q2PR1p1/P7/1P4P1/2q3K1_w_-_-_moves_g1f2_f5e4_a4b3_h7h1_b3c3_d5c3_b5f1_c1f4_f2e1_f4e3
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
