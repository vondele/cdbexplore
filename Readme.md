# Explore and extend the Chess Cloud Database 

Explores and searches [chessdb.cn](https://chessdb.cn/queryc_en/), the largest online database (db) of chess positions and openings.

## Purpose

Build a search tree from a particular position, using a mini-max like algorithm,
finding the best line, extending the db as needed.

Using some concurrency, fairly deep exploration is quickly possible.

## `cdbsearch`

This is a command line program to explore a single position.

```
usage: cdbsearch.py [-h] [--epd EPD | --san SAN] [--chess960] [--depthLimit DEPTHLIMIT] [--timeLimit TIMELIMIT] [--concurrency CONCURRENCY] [--evalDecay EVALDECAY] [--cursedWins] [--TBsearch] [--proveMates] [--user USER] [--suppressErrors]

Explore and extend the Chess Cloud Database (https://chessdb.cn/queryc_en/). Builds a search tree for a given position.

options:
  -h, --help            show this help message and exit
  --epd EPD             EPD/FEN to explore: acceptable are FENs w/ and w/o move counters, as well as the extended "['startpos'|FEN] moves m1 m2 m3" syntax. (default: startpos moves g2g4)
  --san SAN             Moves in SAN notation that lead to the position to be explored. E.g. "1. g4". (default: None)
  --chess960            Enable chess960. (default: False)
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
  --suppressErrors      Suppress any error messages resulting from the API calls. (default: False)
``` 

Sample output:

```
Search at depth  8
  position  :  rnbqkbnr/pppppppp/8/8/6P1/8/PPPPPP1P/RNBQKBNR b KQkq -
  cdb PV len:  39
  score     :  174
  PV        :  d7d5 c2c4 c8g4 d1b3 e7e6 h2h3 g4f5 c4d5 d8d5 b3d5 e6d5 b1c3 c7c6 g1f3 f8d6 f3d4 f5g6 h3h4 g8f6 f1h3
  PV len    :  20
  level     :  25
  max level :  39
  queryall  :  1409
  bf        :  2.48
  chessdbq  :  713 (50.60% of queryall)
  enqueued  :  8
  requeued  :  0
  unscored  :  0 (0.00% of enqueued)
  reprobed  :  113 (15.85% of chessdbq)
  inflightQ :  38.71
  inflightR :  11.15
  cdb time  :  22
  date      :  2026-01-05T21:05:02.452997
  total time:  0:00:16.24
  URL       :
https://chessdb.cn/queryc_en/?rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR_w_KQkq_-_moves_g2g4_d7d5_c2c4_c8g4_d1b3_e7e6_h2h3_g4f5_c4d5_d8d5_b3d5_e6d5_b1c3_c7c6_g1f3_f8d6_f3d4_f5g6_h3h4_g8f6_f1h3
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
Starting date:  2026-01-05T21:05:30.827169
Search at depth  1
  position  :  3r4/3N2kr/1p6/pBpn1p2/Q2PR1p1/P7/1P4P1/2q3K1 w - -
  cdb PV len:  10
  score     :  -29990
  PV        :  g1f2 f5e4 a4b3 h7h1 b3c3 d5c3 b5f1 c1f4 f2e1 f4e3 CHECKMATE (#-5)
  PV len    :  10
  level     :  10
  max level :  10
  queryall  :  3332
  bf        :  3332.00
  chessdbq  :  1965 (58.97% of queryall)
  enqueued  :  0
  requeued  :  0
  unscored  :  0 (0.00% of enqueued)
  reprobed  :  10 (0.51% of chessdbq)
  inflightQ :  15.87
  inflightR :  5.91
  cdb time  :  61
  date      :  2026-01-05T21:07:30.809123
  total time:  0:01:59.98
  URL       :  https://chessdb.cn/queryc_en/?3r4/3N2kr/1p6/pBpn1p2/Q2PR1p1/P7/1P4P1/2q3K1_w_-_-_moves_g1f2_f5e4_a4b3_h7h1_b3c3_d5c3_b5f1_c1f4_f2e1_f4e3
```

## `cdbbulksearch`

This is a command line program to sequentially explore several positions.

```
usage: cdbbulksearch.py [-h] [--excludeFile EXCLUDEFILE] [--chess960] [--plyBegin PLYBEGIN] [--plyEnd PLYEND] [--shuffle] [--depthLimit DEPTHLIMIT] [--timeLimit TIMELIMIT] [--concurrency CONCURRENCY] [--evalDecay EVALDECAY] [--cursedWins] [--TBsearch] [--proveMates] [--user USER] [--suppressErrors] [--bulkConcurrency BULKCONCURRENCY] [--forever] [--maxDepthLimit MAXDEPTHLIMIT] [--reload] filename

Invoke cdbsearch for positions loaded from a file.

positional arguments:
  filename              PGN file if suffix is .pgn(.gz), o/w a file with FENs/EPDs. The latter may use the extended "['startpos'|FEN] moves m1 m2 m3" syntax.

options:
  -h, --help            show this help message and exit
  --excludeFile EXCLUDEFILE
                        A file with FENs/EPDs that should not be loaded from filename. (default: None)
  --chess960            Enable chess960. (default: False)
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
  --suppressErrors      Argument passed to cdbsearch. (default: False)
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
python cdbexplore/cdbbulksearch.py book.pgn --forever >& cdbsearch_book.log &
```

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
