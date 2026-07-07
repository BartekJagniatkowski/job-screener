# CV upload & parse — design spec

Date: 2026-07-06

## Goal

Settings page has a plain textarea for CV text. Add a file upload option (PDF, DOCX, TXT) that extracts text and fills the textarea, so users don't have to copy-paste manually.

## New dependencies

- `pypdf` — pure Python PDF text extraction, no heavy transitive deps (no Pillow/pdfminer), MIT license.
- `python-docx` — DOCX text extraction, standard choice.

Added via `uv add pypdf python-docx`.

## New module: `cv_parser.py`

```python
def parse_cv(file_storage) -> str:
    """Extract plain text from an uploaded CV file. Raises ValueError on
    unsupported extension, corrupt file, or empty extracted text."""
```

- Dispatches on file extension: `.pdf` → pypdf, `.docx` → python-docx, `.txt` → decode directly.
- In-memory only — file is never written to disk.
- Raises `ValueError` with a user-facing message for: unsupported extension, corrupt/unreadable file, empty extracted text (e.g. scanned/image-only PDF with no text layer — no OCR).

## New route: `POST /settings/cv_upload` (app.py)

- Login required, same as other `/settings` routes.
- Rate limit: 10/hour per user (`flask-limiter`, same pattern as `/analyze`).
- `app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024` (2MB) set globally at app init — simplest way to bound upload size; also applies to existing routes, which is fine (no existing route needs >2MB payloads).
- Reads `request.files['cv_file']`, calls `cv_parser.parse_cv()`.
- Response JSON:
  - Success: `{"success": true, "text": "<extracted plain text>"}`
  - Failure: `{"success": false, "error": "<message>"}` (400 status)
- CSRF: validated via `X-CSRFToken` header, same as other AJAX POSTs in the app (token read from `<meta name="csrf-token">`).

## Frontend: `settings.html`

- File input (`accept=".pdf,.docx,.txt"`) + "Upload CV" button placed next to the existing CV `<textarea>`.
- Flow on file select:
  1. POST file via `fetch()` (multipart/form-data), disable input/button, show "Parsing…" inline state.
  2. On success: fill `#cv` textarea with returned text, show inline confirmation message near the field. Existing **Save** button still required to persist — no auto-save, consistent with the rest of Settings.
  3. On error: show inline error message near the field, re-enable input for retry (same or different file).
- No new JS file — inline `<script>` in `settings.html`, consistent with how other AJAX behavior in the app is wired per-template.
- Styling: new classes only if needed, added to `static/style.css` per CLAUDE.md's zero-inline-styles rule.

## No-disk-storage guarantee

Legal/transparency requirement: the uploaded file must never be written to disk.

**Enforcing it in code:**
- `cv_parser.parse_cv()` only reads `file_storage.stream` / `.read()` into memory; bytes go straight into `BytesIO` and then `pypdf.PdfReader(...)` / `docx.Document(...)`. No `.save()`, no `open(path, 'wb')`, no temp files, ever.
- Route handler logs only filename/extension/size on error — never file content.
- gunicorn access log format (per CLAUDE.md) captures method/path/status only, never POST body, so raw bytes never land in `/tmp/screener-access.log` either.
- Regression test: monkeypatch `open()`/`tempfile` during the upload test, assert never called in write mode. Fails CI if a future change introduces disk writes.

**Proving it to the user:**
- About page (existing ethics section, v0.49): one sentence — "CV files are parsed in memory and never written to disk" — linking to `cv_parser.py` on the public GitHub repo, since the code is open source and directly inspectable.
- Inline note next to the upload button in Settings (small text or tooltip) with the same one-line reassurance, so it's visible at the point of upload, not just buried in About.

## Out of scope

- OCR for scanned/image-only PDFs — errors out, tells user to paste manually.
- Server-side storage of the uploaded file.
- Preview-before-insert confirmation step — parsed text is inserted automatically on success (per chosen flow), not staged for a separate accept step.

## Testing

- Unit tests for `cv_parser.parse_cv()`: valid PDF, valid DOCX, valid TXT, corrupt PDF, empty-text PDF, unsupported extension.
- Route test for `/settings/cv_upload`: success path, oversized file (413), unsupported extension (400), rate limit exceeded.
