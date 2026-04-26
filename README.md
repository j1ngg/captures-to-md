# captures-to-md

Feed PDFs, images, and Word / Excel / PowerPoint files into your LLM-native second brain.

Inspired by Karpathy's "second brain" approach — a markdown wiki organized
so an LLM can read it like a human — `captures-to-md` adapts the idea to
handle the formats a plain markdown vault can't ingest on its own: PDFs
with tables and figures, scanned images, Word / Excel / PowerPoint files.

Drop a file into your wiki's inbox folder. A few minutes later, the parsed
markdown appears in a `parsed_outputs/` subfolder — figures, tables, and all —
ready for Claude, Obsidian, or whatever reads your notes.

## Install

Needs Python 3.10+ and [pipx](https://pipx.pypa.io/). On macOS:

```bash
brew install pipx && pipx ensurepath
```

Install `captures-to-md`:

```bash
pipx install git+https://github.com/j1ngg/captures-to-md.git
```

Add your Extend API key to `~/.zshrc` (or `~/.bashrc`):

```bash
export EXTEND_API_KEY=sk-...
```

Open a new terminal (or `source ~/.zshrc`) and you're ready. Get your
API key from your Extend dashboard.

To update later: `pipx upgrade captures-to-md`.

## Ingest a folder

```bash
captures-to-md scan /path/to/your/wiki/inbox
```

Replace the path with wherever you drop files — an Obsidian `_RAW` folder,
a plain `~/Dropbox/inbox`, whatever you use.

Supported extensions: `.pdf`, `.png`, `.jpg`, `.jpeg`, `.docx`, `.xlsx`,
`.pptx`. Anything else is ignored. Running the command twice is safe:
files already processed are skipped automatically.

After a successful run, all parsed `.md` files land in a
`parsed_outputs/` folder inside the directory you scanned, and any
figures land in `parsed_outputs/assets/` with relative links — so
Obsidian (or any markdown renderer) shows the images inline.

## Use it from Claude Code

Install the included slash command globally so it works from any project:

```bash
mkdir -p ~/.claude/commands
curl -fsSL https://raw.githubusercontent.com/j1ngg/captures-to-md/main/.claude/commands/ingest-wiki.md \
  -o ~/.claude/commands/ingest-wiki.md
```

Then in any Claude Code session:

```
/ingest-wiki /path/to/your/wiki/inbox
```

Claude runs the scan, reports what was processed, and lists the new `.md`
files — so you can summarize or query them in the same session.

## Automate it

Two options depending on how fresh you want the output.

### Periodic scans via cron (recommended)

Scan every 6 hours in the background, no process to manage:

```bash
crontab -e
```

Add these two lines, substituting your API key and wiki path:

```
EXTEND_API_KEY=sk-...
0 */6 * * * $HOME/.local/bin/captures-to-md scan "/path/to/your/wiki/inbox" >> $HOME/Library/Logs/captures-to-md.log 2>&1
```

The first line sets the API key (cron doesn't inherit your shell's
env vars). The second line runs the scan every 6 hours.

If `$HOME/.local/bin/captures-to-md` doesn't exist on your system, run
`which captures-to-md` to find the actual path and use that instead.

Cron is the right choice here: unlike macOS launchd, it doesn't clutter
System Settings → Login Items with a background agent.

**macOS gotcha:** if your wiki lives in `~/Documents`, `~/Desktop`, or
iCloud Drive, grant Full Disk Access to `/usr/sbin/cron` once in
System Settings → Privacy & Security → Full Disk Access. Wikis stored
elsewhere (e.g., `~/Code/`) don't need this.

### Real-time mode

If you want files ingested within seconds of dropping them rather than
at the next cron tick:

```bash
captures-to-md watch /path/to/your/wiki/inbox
```

Listens for filesystem events and processes each file as it arrives.
Ctrl-C to stop. Useful for instant feedback; otherwise `scan` + cron is
simpler and doesn't tie up a terminal.

## Options

Override defaults via CLI flags or env vars:

| Flag | Env var | Default | Purpose |
|---|---|---|---|
| `--workers N` / `-w N` | `CAPTURES_TO_MD_WORKERS` | 3 | Concurrent files |
| `--log-level` | `CAPTURES_TO_MD_LOG_LEVEL` | INFO | DEBUG / INFO / WARNING / ERROR |
| `--env-file` | — | `.env` | Alternate env file |
| — | `CAPTURES_TO_MD_STABILITY_SECONDS` | 2.0 | Wait this long for a file to finish copying before uploading. Bump to 10+ for iCloud / Dropbox folders. |

## Troubleshooting

- **"no supported files found"** — your folder has no PDFs, images, or
  Word / Excel / PowerPoint files — or they're all inside an `assets/`
  subfolder (which is ignored).
- **Parsing keeps failing** — check `EXTEND_API_KEY` is set and valid.
  Full errors are in `~/Library/Logs/captures-to-md.log` (if you set up
  cron) or in the terminal you ran it from.
- **iCloud / Dropbox files uploaded partially** — set
  `CAPTURES_TO_MD_STABILITY_SECONDS=10` so the tool waits for the sync
  to finish before uploading.
- **Rate limits (429)** — the tool retries automatically. If you see
  sustained 429s, lower `--workers` to 1 or 2.

## Contributing

Clone the repo and install in editable mode inside a venv:

```bash
git clone https://github.com/j1ngg/captures-to-md.git
cd captures-to-md
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
```

All tests run offline — the Extend SDK and figure downloads are mocked.
