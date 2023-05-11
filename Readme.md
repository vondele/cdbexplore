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
``` 

Sample output:

```
Search at depth  15
  score     :  124
  PV        :  d7d5 h2h3 h7h5 g4h5 e7e5 c2c3 h8h5 d2d4 b8c6 d4e5 c6e5 c1f4 e5g6 f4h2 f8d6 b1d2 d6h2 h1h2 g8f6 e2e3 d8d6 h2g2 e8f8 g2g3 a7a5 f1e2 h5e5
  queryall  :  5357
  bf        :  1.77
  inflight  :  11.44
  chessdbq  :  1463
  enqueued  :  0
  date      :  2023-05-06T21:37:31.630978
  total time:  60905
  req. time :  41
  URL       :  https://chessdb.cn/queryc_en/?rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR_w_KQkq_-_moves_g2g4_d7d5_h2h3_h7h5_g4h5_e7e5_c2c3_h8h5_d2d4_b8c6_d4e5_c6e5_c1f4_e5g6_f4h2_f8d6_b1d2_d6h2_h1h2_g8f6_e2e3_d8d6_h2g2_e8f8_g2g3_a7a5_f1e2_h5e5
```

Meaning of the fields:

```
score      : The standard minimax score found, not using the decay that cdb implements.
PV         : Best line found.
queryall   : Number of positions visited in the search tree, with results provided by cdb or the local cache.
bf         : Branching factor q^(1/d) computed from queryall q and depth d.
inflight   : Number of active/concurrent requests made to cdb on average.
chessdbq   : Number of positions requested to cdb.
enqueued   : Number of positions that did not exist in the database but have been added as part of the search.
date       : ... you guessed it
total time : Time spent in milliseconds since the start of the search.
req. time  : Average time needed to get a cdb list of moves for a position (including those that required enqueuing).
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
                        Argument passed to cdbsearch. (default: 22)
  --concurrency CONCURRENCY
                        Argument passed to cdbsearch. (default: 16)
  --evalDecay EVALDECAY
                        Argument passed to cdbsearch. (default: 2)
  --bulkConcurrency BULKCONCURRENCY
                        Number of concurrent processes running cdbsearch. (default: 1)
  --forever             Pass positions from filename to cdbsearch in an infinite loop. (default: False)
```

Example:
```shell
echo '[Event "*"]\n\n1. g4 *\n\n1. g4 d5 *\n' > book.pgn
git clone https://github.com/vondele/cdbexplore
python3 cdbexplore/cdbbulksearch.py book.pgn --forever >& cdbsearch_book.log &
```

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
