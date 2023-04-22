# Explore and extend the Chess Cloud Database 

Explores and searches the largest online database (db) of chess positions and openings:

[chessdb](https://chessdb.cn/queryc_en/)

## Purpose

Build a search tree from a particular position, using a mini-max like algorithm,
finding the best line, extending the db as needed.

Using some concurrency, fairly deep exploration is quickly possible

## Usage

This is a command line program. 

```
usage: search.py [-h] [--epd EPD] [--concurrency CONCURRENCY] [--evalDecay EVALDECAY]

Explore and extend the Chess Cloud Database (https://chessdb.cn/queryc_en/). Builds a search tree for a given position (FEN/EPD)

options:
  -h, --help            show this help message and exit
  --epd EPD             epd to explore (default: rnbqkbnr/pppppppp/8/8/6P1/8/PPPPPP1P/RNBQKBNR b KQkq g3)
  --concurrency CONCURRENCY
                        concurrency of requests. This is the maximum number of requests made to chessdb at the same time. (default: 16)
  --evalDecay EVALDECAY
                        depth decrease per cp eval-to-best. A small number will use a very narrow search, 0 will essentially just follow PV lines. A wide search will
                        likely enqueue many positions (default: 2)
``` 

Sample output:

```
Search at depth  15
  score     :  132
  PV        :  d7d5 h2h3 h7h5 g4h5 e7e5 c2c3 d8h4 g1f3 h4h5 d2d3 g8e7 e2e4 b8c6 c1e3 f7f6 b1d2 c8e6 f1e2 h5f7 d1a4 e6d7 a4c2 e8c8 
  queryall  :  6897
  bf        :  1.80
  inflight  :  13.20
  chessdbq  :  1837
  enqueued  :  0
  date      :  2023-04-22T17:23:34.553357
  total time:  88958
  req. time :  48
  URL       :  https://chessdb.cn/queryc_en/?rnbqkbnr/pppppppp/8/8/6P1/8/PPPPPP1P/RNBQKBNR_b_KQkq_-_moves_d7d5_h2h3_h7h5_g4h5_e7e5_c2c3_d8h4_g1f3_h4h5_d2d3_g8e7_e2e4_b8c6_c1e3_f7f6_b1d2_c8e6_f1e2_h5f7_d1a4_e6d7_a4c2_e8c8
```

Meaning of the fields:

```
score      : The standard minimax score found, not using the decay that cdb implements
PV         : Best line found
queryall   : Number of positions visited in the search tree, with results provided by cdb or the local cache.
bf         : Branching factor computed from the last (i.e. queryall relative to depth)
inflight   : Number of active/concurrent requests made to cdb on average
chessdbq   : Number of positions requested to cdb
enqueued   : Number of positions that did not exist in the database but have been added as part of the search.
date       : ... you guess it
total time : Time spent in milliseconds since the start of the search
req. time  : Average time needed to get a cdb list of moves for a position (including those that required enqueuing).
URL        : link displaying the found PV in chessdb
```

