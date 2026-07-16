"""Extraccion de texto plano a partir de distintos formatos de documento."""
from pathlib import Path

from pypdf import PdfReader
from docx import Document as DocxDocument


def load_text(path: Path) -> str:
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)

    if suffix == ".docx":
        doc = DocxDocument(str(path))
        return "\n".join(p.text for p in doc.paragraphs)

    if suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="ignore")

    raise ValueError(f"Formato no soportado: {suffix}")
