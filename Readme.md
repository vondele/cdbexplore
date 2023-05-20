# Explore and extend the Chess Cloud Database 

Explores and searches [chessdb.cn](https://chessdb.cn/queryc_en/), the largest online database (db) of chess positions and openings.

## Purpose

Build a search tree from a particular position, using a mini-max like algorithm,
finding the best line, extending the db as needed.

Using some concurrency, fairly deep exploration is quickly possible.

## `cdbsearch`

This is a command line program to explore a single position.

```
usage: cdbsearch.py [-h] [--epd EPD | --san SAN] [--depthLimit DEPTHLIMIT] [--concurrency CONCURRENCY] [--evalDecay EVALDECAY]

Explore and extend the Chess Cloud Database (https://chessdb.cn/queryc_en/). Builds a search tree for a given position.

options:
  -h, --help            show this help message and exit
  --epd EPD             EPD/FEN to explore: acceptable are FENs w/ and w/o move counters, as well as the extended "moves m1 m2 m3" syntax from cdb's API. (default: rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - moves g2g4)
  --san SAN             Moves in SAN notation that lead to the position to be explored. E.g. "1. g4". (default: None)
  --depthLimit DEPTHLIMIT
                        Finish the exploration at the specified depth. (default: None)
  --concurrency CONCURRENCY
                        Concurrency of requests. This is the maximum number of requests made to chessdb at the same time. (default: 16)
  --evalDecay EVALDECAY
                        Depth decrease per cp eval-to-best. A small number will use a very narrow search, 0 will essentially just follow PV lines. A wide search will likely enqueue many positions. (default: 2)
  --cursedWins          Treat cursed wins as wins. (default: False)
``` 

Sample output:

```
Search at depth  11
  score     :  131
  PV        :  d7d5 e2e3 b8c6 b1c3 e7e5 d2d4 c8e6 d4e5 c6e5 h2h3 h7h5 g1f3
  queryall  :  23791
  bf        :  2.50
  inflight  :  13.01
  chessdbq  :  9805
  enqueued  :  75
  unscored  :  88
  date      :  2023-05-20T14:15:27.826349
  total time:  0:05:52.63
  req. time :  35
  URL       :  https://chessdb.cn/queryc_en/?rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR_w_KQkq_-_moves_g2g4_d7d5_e2e3_b8c6_b1c3_e7e5_d2d4_c8e6_d4e5_c6e5_h2h3_h7h5_g1f3
```

Meaning of the fields:

```
score      : The standard minimax score found, not using the decay that cdb implements.
PV         : Best line found.
queryall   : Number of positions visited in the search tree, with results provided by cdb or the local cache.
bf         : Branching factor q^(1/d) computed from queryall q and depth d.
inflight   : Number of active/concurrent requests made to cdb on average.
chessdbq   : Number of positions requested to cdb.
enqueued   : Number of positions that did not exist within cdb but have been added as part of the search.
unscored   : Number of existing unscored moves within cdb that were assigned a score as part of the search.
date       : ... you guessed it
total time : Time spent since the start of the search.
req. time  : Average time (in milliseconds) needed to get a cdb list of moves for a position (including those that required enqueuing).
URL        : Link displaying the found PV in chessdb.
```

## `cdbbulksearch`

This is a command line program to sequentially explore several positions.

```
usage: cdbbulksearch.py [-h] [--depthLimit DEPTHLIMIT] [--concurrency CONCURRENCY] [--evalDecay EVALDECAY] [--bulkConcurrency BULKCONCURRENCY] [--forever] filename

Sequentially call cdbsearch for EPDs or book exits stored in a file.

positional arguments:
  filename              PGN file if suffix is .pgn, o/w a text file with EPDs.

options:
  -h, --help            show this help message and exit
  --depthLimit DEPTHLIMIT
                        Argument passed to cdbsearch. (default: 5)
  --concurrency CONCURRENCY
                        Argument passed to cdbsearch. (default: 16)
  --evalDecay EVALDECAY
                        Argument passed to cdbsearch. (default: 2)
  --cursedWins          Argument passed to cdbsearch. (default: False)
  --bulkConcurrency BULKCONCURRENCY
                        Number of concurrent processes running cdbsearch. (default: 4)
  --forever             Pass positions from filename to cdbsearch in an infinite loop. (default: False)
```

Example:
```shell
echo '[Event "*"]\n\n1. g4 *\n\n1. g4 d5 *\n' > book.pgn
git clone https://github.com/vondele/cdbexplore && pip install -r cdbexplore/requirements.txt
python3 cdbexplore/cdbbulksearch.py book.pgn --forever >& cdbsearch_book.log &
```

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
