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

