"""
PDF parsing module.
Extracts plain text from resume PDFs using pdfplumber.
Falls back to PyMuPDF if pdfplumber fails.
"""
import io
from typing import Union

import pdfplumber
import fitz  # PyMuPDF


def parse_pdf(file_bytes: bytes) -> str:
    """
    Extract plain text from a PDF file.

    Args:
        file_bytes: Raw bytes of the PDF file.

    Returns:
        Extracted text as a single string.

    Raises:
        ValueError: If both parsers fail to extract text.
    """
    # Try pdfplumber first (better for structured PDFs)
    try:
        text = _parse_with_pdfplumber(file_bytes)
        if text and text.strip():
            return _clean_text(text)
    except Exception as e:
        print(f"pdfplumber failed: {e}, falling back to PyMuPDF")

    # Fallback to PyMuPDF
    try:
        text = _parse_with_pymupdf(file_bytes)
        if text and text.strip():
            return _clean_text(text)
    except Exception as e:
        print(f"PyMuPDF failed: {e}")

    raise ValueError("Failed to extract text from PDF with both parsers")


def _parse_with_pdfplumber(file_bytes: bytes) -> str:
    """Extract text using pdfplumber."""
    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n\n".join(text_parts)


def _parse_with_pymupdf(file_bytes: bytes) -> str:
    """Extract text using PyMuPDF as fallback."""
    text_parts = []
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    try:
        for page in doc:
            page_text = page.get_text()
            if page_text:
                text_parts.append(page_text)
    finally:
        doc.close()
    return "\n\n".join(text_parts)


def _clean_text(text: str) -> str:
    """Basic cleaning: normalize whitespace, remove empty lines."""
    # Split into lines, strip each, drop empty
    lines = [line.strip() for line in text.split("\n")]
    lines = [line for line in lines if line]
    return "\n".join(lines)


# ============================================================
# Quick test (run this file directly to test)
# ============================================================
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python pdf_parser.py <path_to_pdf>")
        sys.exit(1)

    with open(sys.argv[1], "rb") as f:
        pdf_bytes = f.read()

    text = parse_pdf(pdf_bytes)
    print(f"Extracted {len(text)} characters")
    print("=" * 50)
    print(text[:500])
    print("..." if len(text) > 500 else "")