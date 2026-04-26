# captures-to-md

Watch a folder, parse PDFs / images / Word & Excel & PowerPoint files into LLM-readable markdown.

Drop a file into the folder. A few minutes later, the parsed markdown
appears in a `parsed_outputs/` subfolder — figures, tables, and all —
ready for Claude, Obsidian, or any tool that reads markdown.

## Why this exists

Markdown is a first-class citizen for AI agents. They read it as text,
link to it, write it back, reason over it natively. Anything else —
PDFs, decks, screenshots — is second-class: parsed from images on every
read, with structure that shifts between runs and no stable handle the
agent can quote later.

`captures-to-md` does the conversion once so unstructured files can
join the cognitive substrate your notes already live in:

- **Available for connection.** A parsed `.md` has actual text that
  wikilinks, embeds, and concept pages can quote and anchor in — so a
  passage from a PDF can be cross-referenced from anywhere in your
  notes the way a paragraph you typed yourself can be.
- **Eligible for synthesis.** YAML frontmatter (tags, status, dates)
  lets parsed sources participate in Karpathy-style synthesis
  workflows — queryable, filterable, indexable alongside your own notes
  rather than sitting outside the graph.

For a one-shot read, just open the PDF — this is overkill. The value
compounds when many sources need to live alongside your notes,
addressable by reference and durable across agent sessions.

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

## Use it

```bash
captures-to-md scan /path/to/your/folder
```

The folder can be anywhere, named anything — an Obsidian `_RAW`, a
plain `~/Dropbox/inbox`, a project subdirectory, whatever you use.

Supported extensions: `.pdf`, `.png`, `.jpg`, `.jpeg`, `.docx`, `.xlsx`,
`.pptx`. Anything else is ignored. Running the command twice is safe:
files already processed are skipped automatically.

After a successful run, parsed `.md` files land in a `parsed_outputs/`
subfolder inside the directory you scanned, and any figures land in
`parsed_outputs/assets/` with relative links — so Obsidian (or any
markdown renderer) shows the images inline.

## Use it from Claude Code

Install the included slash command globally so it works from any project:

```bash
mkdir -p ~/.claude/commands
curl -fsSL https://raw.githubusercontent.com/j1ngg/captures-to-md/main/.claude/commands/parse-folder.md \
  -o ~/.claude/commands/parse-folder.md
```

Then in any Claude Code session:

```
/parse-folder /path/to/your/folder
```

Claude runs the scan, reports what was processed, and lists the new
`.md` files — so you can summarize or query them in the same session.

## Automate it

Two options depending on how fresh you want the output.

### Periodic scans via cron (recommended)

Scan every 6 hours in the background, no process to manage:

```bash
crontab -e
```

Add these two lines, substituting your API key and folder path:

```
EXTEND_API_KEY=sk-...
0 */6 * * * $HOME/.local/bin/captures-to-md scan "/path/to/your/folder" >> $HOME/Library/Logs/captures-to-md.log 2>&1
```

The first line sets the API key (cron doesn't inherit your shell's
env vars). The second line runs the scan every 6 hours.

If `$HOME/.local/bin/captures-to-md` doesn't exist on your system, run
`which captures-to-md` to find the actual path and use that instead.

Cron is the right choice here: unlike macOS launchd, it doesn't clutter
System Settings → Login Items with a background agent.

**macOS gotcha:** if your folder lives in `~/Documents`, `~/Desktop`, or
iCloud Drive, grant Full Disk Access to `/usr/sbin/cron` once in
System Settings → Privacy & Security → Full Disk Access. Folders
stored elsewhere (e.g., `~/Code/`) don't need this.

### Real-time mode

If you want files ingested within seconds of dropping them rather than
at the next cron tick:

```bash
captures-to-md watch /path/to/your/folder
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
