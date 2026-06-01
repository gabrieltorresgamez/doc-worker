# doc-worker

A self-hosted service that turns network scanner emails into translated or summarized documents.

The scanner sends a scan to a named mailbox alias. The alias local-part identifies who gets the result; mode and language are configured per-recipient in `config.yml`. The worker picks up unseen messages, runs OCR and the requested transformation via a pluggable AI backend, and emails the result back to the right person — along with the original file.

```
scanner → alice@scan.example.com
            │
            └── person key → looks up address, mode, language in config.yml
```

---

## How it works

1. **Poll** — fetches all UNSEEN messages from the configured IMAP inbox every `poll_interval_seconds`. Messages stay UNSEEN until explicitly moved or deleted, so a crash before that leaves them available for reprocessing.
2. **Decode alias** — maps the `To:` address local-part to a recipient entry in config.
3. **Extract attachments** — accepts PDFs and images up to `max_attachment_mb`. Others are skipped.
4. **Process** — calls the configured backend, which OCRs the document and translates or summarizes it.
5. **Reply** — sends the result plus the original attachment to the recipient's real address.
6. **Post-action** — moves or deletes the source message (configurable separately for success and failure).

On any error the original attachment is emailed back with an error note, and the message is moved to the failed folder.

---

## Mailbox aliases

Create one Infomaniak email alias per recipient, all delivering to the same main mailbox. The local-part of the alias is the **person key** — it must match an entry in `recipients` in `config.yml`.

```
Main mailbox:    scan@scan.example.com
Alias → Alice:   alice@scan.example.com  → scan@scan.example.com
Alias → Bob:     bob@scan.example.com    → scan@scan.example.com
```

Mode and language are set in `config.yml` under each recipient, with `defaults` as fallback. This means no parameter encoding in the address and no catch-all mailbox required.

---

## Backends

### Infomaniak (default)

Uses Infomaniak's OpenAI-compatible API with `mistralai/Ministral-3-14B-Instruct-2512` as a vision LLM. A single API call does OCR and transformation. PDFs are rendered to per-page PNG images first (via `pypdfium2`).

Swiss-sovereign compute; good choice for privacy-sensitive household documents.

### Mistral

Two-step pipeline: `mistral-ocr-2512` for OCR, then `mistral-small-latest` for translation or summarization. Best OCR accuracy, especially for printed documents with complex layouts. Two API calls per document. EU-based.

The backend is selected via `backend:` in `config.yml` or the `BACKEND` env var (env wins).

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
- `imap.host` / `smtp.host`
- `recipients` (person key → real email address)
- `backend` (`infomaniak` or `mistral`)
- `defaults.mode` and `defaults.language`

Fill `.env` with credentials (never commit this file):

| Variable                | Required for       |
| ----------------------- | ------------------ |
| `IMAP_USER`             | always             |
| `IMAP_PASSWORD`         | always             |
| `SMTP_USER`             | always             |
| `SMTP_PASSWORD`         | always             |
| `INFOMANIAK_TOKEN`      | Infomaniak backend |
| `INFOMANIAK_PRODUCT_ID` | Infomaniak backend |
| `MISTRAL_API_KEY`       | Mistral backend    |

### 3. Run locally

```bash
uv run doc-worker
```

### 4. Run with Docker

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
├── alias.py         # destination address parsing
├── documents.py     # attachment extraction, PDF→PNG rendering
├── mailbox.py       # IMAP fetch/move/delete, SMTP send
└── backends/
    ├── __init__.py
    ├── base.py      # DocBackend protocol, shared prompt builders
    ├── factory.py   # get_backend() factory
    ├── infomaniak.py
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
  from_address: scan@scan.example.com
  from_name: "Document Assistant"

backend: infomaniak   # infomaniak | mistral
                      # overridden by BACKEND env var

# Model overrides — defaults shown, omit section to use them as-is
backends:
  infomaniak:
    model: mistralai/Ministral-3-14B-Instruct-2512
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

recipients:           # person key = Infomaniak alias local-part
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
