---
description: Run captures-to-md on a wiki folder to convert new PDFs/images/Office docs into markdown via the Extend Parse API. Use when the user wants to ingest, parse, or process files from their wiki inbox.
argument-hint: "<path to wiki _RAW folder>"
allowed-tools: Bash(captures-to-md:*), Bash(find:*), Bash(ls:*), Read
---

The user wants to ingest files from their wiki folder: $ARGUMENTS

1. Run `captures-to-md scan` against that folder via the Bash tool. Quote the path correctly (it may contain spaces or `~`). The scan can take 30-60s per unparsed file; let it run to completion rather than timing out.
2. Report the summary line (`processed=X failed=Y skipped=Z`) from the output. If `processed=0` and `skipped=0`, tell the user no supported files were found.
3. If `processed > 0`: list the newly-created `.md` files in the target directory (those modified in the last 15 minutes). Offer to summarize or open any of them.
4. If `failed > 0`: surface the failure reason from the log output and suggest a next step (re-run the scan, check `EXTEND_API_KEY`, or inspect the file).
5. Do not re-run the scan or invoke `watch` — one scan pass is enough.
