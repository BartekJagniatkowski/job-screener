import io

import docx
import pytest
from pypdf import PdfWriter

from cv_parser import parse_cv


class _FakeFileStorage:
    def __init__(self, filename, data):
        self.filename = filename
        self._data = data

    def read(self):
        return self._data


def _make_pdf_bytes(with_text=True):
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    if with_text:
        # pypdf's PdfWriter has no simple text-drawing API; blank pages
        # extract as empty text, which is exactly the "no text layer" case.
        pass
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _make_docx_bytes(text):
    document = docx.Document()
    document.add_paragraph(text)
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


def test_parse_txt():
    text = parse_cv(_FakeFileStorage("cv.txt", "Senior Engineer, 10 years".encode("utf-8")))
    assert text == "Senior Engineer, 10 years"


def test_parse_docx():
    text = parse_cv(_FakeFileStorage("cv.docx", _make_docx_bytes("Product Manager, 5 years")))
    assert "Product Manager, 5 years" in text


def test_parse_pdf_empty_text_raises():
    with pytest.raises(ValueError, match="No text could be extracted"):
        parse_cv(_FakeFileStorage("cv.pdf", _make_pdf_bytes()))


def test_parse_corrupt_pdf_raises():
    with pytest.raises(ValueError, match="corrupt"):
        parse_cv(_FakeFileStorage("cv.pdf", b"not a real pdf"))


def test_parse_corrupt_docx_raises():
    with pytest.raises(ValueError, match="corrupt"):
        parse_cv(_FakeFileStorage("cv.docx", b"not a real docx"))


def test_parse_unsupported_extension_raises():
    with pytest.raises(ValueError, match="Unsupported file type"):
        parse_cv(_FakeFileStorage("cv.rtf", b"whatever"))


def test_parse_empty_txt_raises():
    with pytest.raises(ValueError, match="No text could be extracted"):
        parse_cv(_FakeFileStorage("cv.txt", b"   "))


def test_parse_cv_never_writes_to_disk(monkeypatch):
    def _forbidden_open(*args, **kwargs):
        raise AssertionError("parse_cv must never open a file on disk")

    monkeypatch.setattr("builtins.open", _forbidden_open)
    text = parse_cv(_FakeFileStorage("cv.txt", "Senior Engineer".encode("utf-8")))
    assert text == "Senior Engineer"
