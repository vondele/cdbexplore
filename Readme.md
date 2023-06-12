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
Search at depth  8
  cdb PV len:  73
  score     :  136
  PV        :  d7d5 e2e3 b8c6 f1e2 e7e5 d2d4 h7h5 g4h5 g8f6 g1f3 f8b4 b1d2 e5d4 f3d4 c6d4
  PV len    :  15
  max ply   :  68
  queryall  :  1481
  bf        :  2.49
  inflightR :  6.89
  inflightQ :  21.30
  chessdbq  :  447
  enqueued  :  9
  unscored  :  1
  reprobed  :  57 (12.75%)
  date      :  2023-06-12T10:35:53.786240
  total time:  0:00:29.65
  cdb time  :  66
  URL       :  https://chessdb.cn/queryc_en/?rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR_w_KQkq_-_moves_g2g4_d7d5_e2e3_b8c6_f1e2_e7e5_d2d4_h7h5_g4h5_g8f6_g1f3_f8b4_b1d2_e5d4_f3d4_c6d4
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
inflightR  : Number of concurrent http requests made to cdb on average.
inflightQ  : Number of concurrent queries, guaranteed to return scored moves, made to cdb on average.
chessdbq   : Number of positions requested to cdb.
enqueued   : Number of positions that did not exist within cdb but have been added as part of the search.
unscored   : Number of existing unscored moves within cdb that were assigned a score as part of the search.
reprobed   : Number of positions in local PV lines re-requested to cdb (and reprobed/chessdbq).
date       : ... you guessed it
total time : Time spent since the start of the search.
cdb time   : Average time (in milliseconds) needed to get a cdb list of moves for a position (including those that required enqueuing).
URL        : Link displaying the found PV on chessdb.cn.
```

Sample output with `--proveMates`:

```
> python cdbsearch.py --epd "3r4/3N2kr/1p6/pBpn1p2/Q2PR1p1/P7/1P4P1/2q3K1 w - -" --depthLimit 1 --evalDecay 0 --proveMates
Root position:  3r4/3N2kr/1p6/pBpn1p2/Q2PR1p1/P7/1P4P1/2q3K1 w - -
evalDecay    :  0
Concurrency  :  16
Prove Mates  :  True
Starting date:  2023-06-12T10:37:58.557911
Search at depth  1
  cdb PV len:  10
  score     :  -29990
  PV        :  b5f1 h7h1 g1h1 c1f1 h1h2 d8h8 h2g3 f5e4 d7f8 f1f4 CHECKMATE (#-5)
  PV len    :  10
  max ply   :  10
  queryall  :  1942
  bf        :  1942.00
  inflightR :  8.96
  inflightQ :  11.45
  chessdbq  :  1467
  enqueued  :  0
  unscored  :  0
  reprobed  :  10 (0.68%)
  date      :  2023-06-12T10:39:48.438634
  total time:  0:01:49.88
  cdb time  :  74
  URL       :  https://chessdb.cn/queryc_en/?3r4/3N2kr/1p6/pBpn1p2/Q2PR1p1/P7/1P4P1/2q3K1_w_-_-_moves_b5f1_h7h1_g1h1_c1f1_h1h2_d8h8_h2g3_f5e4_d7f8_f1f4
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
