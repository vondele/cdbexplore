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
Search at depth  23
  score     :  -89
  PV        :  a5b7 a2a4 c8d7 e3c3 c7b6 a4b5 a6b5 a1a8 f8a8 b2b4 f6e8 d2b3 g8f8 c1d2 a8c8 c3c8 d7c8 c2d3 b7d8 b3a5 h7h6
  queryall  :  3683
  bf        :  1.43
  inflight  :  6.64
  chessdbq  :  1313
  enqueued  :  291
  date      :  2023-04-16T13:41:00.235615
  total time:  416193
  req. time :  316
```

Meaning of the fields:

```
score      : The standard minimax score found, not using the decay that cdb implements
PV         : Best line found
queryall   : Number of positions requested to cdb
bf         : Branching factor computed from the last (i.e. queryall relative to depth)
inflight   : Number of active/concurrent requests made to cdb on average
enqueued   : Number of positions that did not exist in the database but have been added as part of the search.
date       : ... you guess it
total time : Time spent in milliseconds since the start of the search
req. time  : Average time needed to get a cdb list of moves for a position (including those that required enqueuing).
```

