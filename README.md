# doc-worker

A self-hosted service that turns network scanner emails into translated or summarized documents.

The scanner sends a scan to a plus-addressed mailbox. The `+tag` identifies who gets the result; mode and language are configured per-recipient in `config.yml`. The worker picks up unseen messages, runs OCR and the requested transformation via a pluggable AI backend, and emails the result back to the right person — along with the original file.

```
scanner → pipeline+alice@scan.example.com
                    │
                    └── person key → looks up address, mode, language in config.yml
```

---

## How it works

1. **Poll** — fetches all UNSEEN messages from the configured IMAP inbox every `poll_interval_seconds`. Messages stay UNSEEN until explicitly moved or deleted, so a crash before that leaves them available for reprocessing.
2. **Decode tag** — parses the `+tag` from the `To:` address to extract the person key and optional mode/language overrides.
3. **Extract attachments** — accepts PDFs and images up to `max_attachment_mb`. Others are skipped. If no supported attachment is found, an error is sent back and the message moves to the failed folder.
4. **Process** — calls the configured backend, which OCRs the document and translates or summarizes it. Multiple attachments are each processed individually and combined into a single reply.
5. **Reply** — sends the result as a styled HTML email (with plain text fallback) plus the original attachment(s) to the recipient's real address.
6. **Post-action** — moves or deletes the source message (configurable separately for success and failure).

On any error the original attachment is emailed back with an error note, and the message moves to the failed folder.

---

## Plus-addressing

One mailbox receives all scans. The `+tag` identifies the recipient and optionally overrides mode and language — no aliases or catch-all required.

```
pipeline+alice@example.com              → Alice, use config defaults
pipeline+alice.summary@example.com      → Alice, summary, config language
pipeline+alice.translate.de@example.com → Alice, translate, German
```

The tag is split on `.` or `-`. The first token is the person key and must match an entry in `recipients` in `config.yml`. Remaining tokens are classified by type:

| Token                                | Type     | Effect                    |
| ------------------------------------ | -------- | ------------------------- |
| `translate`, `t`                     | mode     | translate document        |
| `summary`, `summarize`, `s`          | mode     | summarize document        |
| two-letter code (`es`, `de`, `fr` …) | language | ISO 639-1 target language |

Unknown tokens are ignored. Priority for mode and language: **tag → recipient config → global defaults**.

---

## Backend

Two-step Mistral pipeline: `mistral-ocr-2512` for document extraction, then `mistral-small-latest` for translation or summarization. PDFs are sent natively — no client-side rendering required. Both models can be overridden in `config.yml` under `backends.mistral`.

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/gabrieltorresgamez/doc-worker
cd doc-worker
uv sync
```

### 2. Configure

```bash
cp config.example.yml config.yml
cp .env.example .env
```

Edit `config.yml` — at minimum:
- `smtp.from_address` — the pipeline mailbox address
- `recipients` — one entry per person, key matches the `+tag`
- `defaults.mode` and `defaults.language`

Fill `.env` with credentials (never commit this file):

| Variable          | Notes    |
| ----------------- | -------- |
| `IMAP_USER`       | required |
| `IMAP_PASSWORD`   | required |
| `SMTP_USER`       | required |
| `SMTP_PASSWORD`   | required |
| `MISTRAL_API_KEY` | required |

### 3. Set up the pipeline mailbox

Create a mailbox (e.g. `pipeline@yourdomain.com`) on Infomaniak. Plus-addressing works out of the box — no aliases needed. Configure your scanner to send to `pipeline+<name>@yourdomain.com`.

### 4. Run locally

```bash
uv run doc-worker
```

### 5. Run with Docker

```bash
docker compose up -d
```

To merge into an existing compose stack:

```bash
docker compose -f docker-compose.yml -f doc-worker/docker-compose.yml up -d
```

---

## Project layout

```
src/doc_worker/
├── __init__.py
├── main.py          # poll loop and per-message orchestration
├── config.py        # YAML + env config loading
├── alias.py         # tag parsing and person key extraction
├── documents.py     # attachment extraction
├── mailbox.py       # IMAP fetch/move/delete, SMTP send, markdown→HTML
└── backends/
    ├── __init__.py
    ├── base.py      # DocBackend protocol, shared prompt builders
    ├── factory.py   # get_backend() factory
    └── mistral.py
```

---

## Configuration reference

```yaml
poll_interval_seconds: 60

imap:
  host: mail.infomaniak.com
  port: 993
  folder_inbox: INBOX
  folder_processed: Processed  # destination after on_success: move
  folder_failed: Failed        # destination after on_failure: move

smtp:
  host: mail.infomaniak.com
  port: 587
  from_address: pipeline@yourdomain.com
  from_name: "Document Assistant"

backend: mistral

# Model overrides — defaults shown, omit section to use them as-is
backends:
  mistral:
    ocr_model: mistral-ocr-2512
    chat_model: mistral-small-latest

defaults:
  mode: translate     # translate | summary
  language: en        # ISO 639-1 code

languages:            # code → name used in AI prompts
  en: English
  es: Spanish
  fr: French
  de: German

recipients:           # person key = '+tag' in destination address
  alice:
    address: alice@example.com
    mode: translate   # overrides defaults.mode (optional)
    language: en      # overrides defaults.language (optional)
  bob:
    address: bob@example.com
    language: de

fallback_reply_to: alice@example.com  # used if person key is unknown

on_success: move      # move | delete
on_failure: move      # move | delete  ('move' recommended — no scan is silently lost)

max_attachment_mb: 25
```

---

## Privacy

All processing happens through the configured backend's API. No document content is written to disk or logged beyond filenames and byte counts. The source message is moved or deleted from the mailbox after handling. No database or external state store is used — IMAP flags are the only persistent state.
