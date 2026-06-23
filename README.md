# krevati

A small semantic-search daemon for a local folder of Markdown notes.

It watches a directory (an Obsidian-style "vault"), chunks and embeds every
note into a [Chroma](https://www.trychroma.com/) vector database, and keeps the
index live as files change. You can then run natural-language searches over your
notes and get back the closest-matching passages — no keyword matching, no cloud
services, everything runs locally.

> This is a learning project — I built it to practice Python. It's a working tool
> rather than a polished, production-hardened one, and the source carries a few
> TODOs marking things I'd still like to improve.

## How it works

```
                   ┌──────────────┐
   notes (*.md) ──▶│   Watcher    │ filesystem events (watchfiles)
                   └──────┬───────┘
                          │ upsert / delete
                          ▼
   query ──▶  ┌───────────────────────┐
              │   Chroma (embeddings) │  chunk → embed → vector DB
              └───────────┬───────────┘
                          │ nearest-neighbour search
              ┌───────────┴───────────┐
              ▼                       ▼
        Unix socket             HTTP /search
        (local CLI)             (POST JSON)
```

On startup the daemon:

1. **Indexes the vault.** Every file matching the glob (default `*.md`) is read,
   split into overlapping character chunks sized to the embedding model's
   context window, embedded, and upserted into Chroma. Already-indexed files are
   skipped unless their mtime, the chunking parameters, or the schema version
   have changed (see `is_stale` in `db.py`). The initial full scan runs at idle
   I/O priority so it doesn't hog the disk.
2. **Watches for changes.** A background thread listens for filesystem events and
   re-indexes, adds, or deletes files as they change on disk.
3. **Serves queries** over two interfaces (either can be disabled in config):
   - a **Unix socket** at `/tmp/krevati.sock`, for fast local lookups;
   - an **HTTP server** with a `POST /search` endpoint, for everything else.

Embeddings are produced locally with [fastembed](https://github.com/qdrant/fastembed)
using the `BAAI/bge-small-en-v1.5` model — the model is downloaded once and cached.

## Requirements

- Python ≥ 3.14
- [uv](https://docs.astral.sh/uv/) for dependency management

## Setup

```bash
uv sync
```

Configuration is read from a TOML file at
**`~/.config/krevati/config.toml`** (or `$XDG_CONFIG_HOME/krevati/config.toml`).
The file is **required** — `config.py` holds no default values, only the schema,
so the daemon refuses to start if the file is missing or any key is absent.

On first run, if no config file exists, krevati copies the shipped
`config.toml.example` to that path and exits, so you just edit the values and run
again:

```console
$ uv run main.py
No config file found — wrote a starter config to /home/you/.config/krevati/config.toml. Edit the values and run again.
```

| Key               | Example                  | Notes                                     |
| ----------------- | ------------------------ | ----------------------------------------- |
| `vault_path`      | `/home/rich/vault`       | directory of notes to index               |
| `file_match_glob` | `*.md`                   | which files to include                    |
| `cache_dir`       | `/home/rich/.cache`      | where the Chroma DB is stored             |
| `socket_path`     | `/tmp/krevati.sock`      | Unix socket for local queries             |
| `server_enabled`  | `true`                   | enable the HTTP server                    |
| `socket_enabled`  | `true`                   | enable the Unix socket                    |
| `host` / `port`   | `0.0.0.0` / `5000`       | HTTP bind address                         |
| `model_string`    | `BAAI/bge-small-en-v1.5` | fastembed model                           |
| `model_context`   | `512`                    | max tokens per embedding request          |
| `overlap`         | `150`                    | character overlap between adjacent chunks |

An API key is required for non-local HTTP requests. Set it either in the config
file (`api_key = "..."`) or, preferably, in the environment — the environment
variable takes precedence over the file:

```bash
export KREVATI_API_KEY=your-secret-here
```

## Running

Start the daemon (indexes, then watches and serves):

```bash
uv run main.py
```

Useful flags:

- `--verbose` — debug-level logging
- `--dangerously-wipe-db` — delete all indexed data before re-indexing
- `--search "your query"` — send a one-off query to the **already-running**
  daemon over the socket and print the results, instead of starting a daemon

### Querying

**Via the CLI** (talks to the running daemon's socket):

```bash
uv run main.py --search "notes about distributed consensus"
```

**Via HTTP:**

```bash
curl -X POST http://localhost:5000/search \
  -H 'Content-Type: application/json' \
  -d '{"query": "notes about distributed consensus", "limit": 5}'
```

Requests from `127.0.0.1`/`::1` skip authentication; remote requests must send
`Authorization: Bearer $KREVATI_API_KEY`. The HTTP endpoint returns a JSON array
of results, each with `path`, `score`, `header`, and `snippet`.

## Project layout

| File            | Responsibility                                                       |
| --------------- | -------------------------------------------------------------------- |
| `main.py`       | entry point, argument parsing, daemon wiring                         |
| `config.py`     | all configuration                                                    |
| `db.py`         | `Searcher`/`Indexer` protocols, `SearchResult` type, staleness logic |
| `chroma.py`     | Chroma-backed implementation: embedding plus upsert/delete/search    |
| `filesystem.py` | filesystem watcher and the initial full index scan                   |
| `server.py`     | HTTP (`Webserver`) and Unix-socket (`Socketserver`) front ends       |
| `client.py`     | socket client used by `--search`                                     |
| `misc.py`       | helpers: `get_mtime`, the text chunker                               |

The `Searcher` and `Indexer` `Protocol`s in `db.py` define the interface between
the storage backend and the rest of the app, so the Chroma backend could in
principle be swapped out without touching the watcher or servers.

## Development

Run the full check suite (lint, type-check, tests, then a live run):

```bash
./run
```

Or the pieces individually:

```bash
uv run ruff check .   # lint
uv run pyright        # type-check
uv run pytest         # tests
```

Tests live alongside the modules they cover (`test_*.py`) and run with a
1-second per-test timeout.

## Name

*krevati* (κρεβάτι) is Greek for "bed" — a place to keep your notes.
