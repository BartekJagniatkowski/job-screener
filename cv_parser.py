"""Extract plain text from an uploaded CV file. In-memory only — never
written to disk."""

import io

import docx
from pypdf import PdfReader


def parse_cv(file_storage) -> str:
    """Extract plain text from an uploaded CV file. Raises ValueError on
    unsupported extension, corrupt file, or empty extracted text."""
    filename = (file_storage.filename or "").lower()
    data = file_storage.read()

    if filename.endswith(".pdf"):
        text = _parse_pdf(data)
    elif filename.endswith(".docx"):
        text = _parse_docx(data)
    elif filename.endswith(".txt"):
        text = _parse_txt(data)
    else:
        raise ValueError("Unsupported file type. Upload a PDF, DOCX, or TXT file.")

    text = text.strip()
    if not text:
        raise ValueError(
            "No text could be extracted from this file. If it's a scanned or "
            "image-only document, paste the CV text manually instead."
        )
    return text


def _parse_pdf(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        raise ValueError("Could not read this PDF file — it may be corrupt.")


def _parse_docx(data: bytes) -> str:
    try:
        document = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in document.paragraphs)
    except Exception:
        raise ValueError("Could not read this DOCX file — it may be corrupt.")


def _parse_txt(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("Could not decode this TXT file — expected UTF-8 text.")
