"""
document_reader.py — Document perception channel for Digi-Soul's language faculty.

Lets the digital body "read" an external document (PDF or plain .txt) as a
sensory/perception event. This module is deliberately *pure*: it knows nothing
about the MessageBus or the LanguageModule. Its only job is to turn a file path
into plain text — or raise a clear, typed error. The bus wiring that routes the
extracted text into language memory lives in language_module.py (cmd "perceive").

Provenance:
    The PyPDF2 page-by-page extraction idea was salvaged from an old PDF→TXT
    Colab export. Everything else from that script — the Google-Drive mount,
    hardcoded /content/drive paths, !pip shell magics, and the word-frequency /
    stopword blocks — was intentionally discarded, not ported.

Public API:
    read_document(path) -> str            # dispatch by extension (.pdf / .txt)
    extract_text_from_pdf(path) -> str
    extract_text_from_txt(path) -> str

Errors (all subclasses of DocumentReadError, plus stdlib FileNotFoundError):
    UnsupportedDocumentError              # not a .pdf or .txt
    EmptyDocumentError                    # no extractable text (image-only PDF)
"""

from pathlib import Path

SUPPORTED_SUFFIXES = {".pdf", ".txt"}


class DocumentReadError(Exception):
    """Base error for any document-perception failure."""


class UnsupportedDocumentError(DocumentReadError):
    """Raised when the file type is not a supported document format."""


class EmptyDocumentError(DocumentReadError):
    """Raised when a document yields no extractable text (e.g. image-only PDF)."""


def extract_text_from_txt(path: str | Path) -> str:
    """Read a plain-text file. Falls back to latin-1 for legacy encodings so a
    stray byte never crashes perception."""
    path = Path(path)
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1", errors="replace")


def extract_text_from_pdf(path: str | Path) -> str:
    """Extract text from a PDF page by page using PyPDF2.

    Returns the concatenated text of all pages (may be empty for an
    image-only / scanned PDF — the caller is responsible for treating an
    empty result as an EmptyDocumentError; read_document() does this)."""
    path = Path(path)
    try:
        import PyPDF2
    except ImportError as exc:
        raise DocumentReadError(
            "PyPDF2 is required to read PDF documents — "
            "install it with `pip install PyPDF2`."
        ) from exc

    parts: list[str] = []
    with open(path, "rb") as fh:
        reader = PyPDF2.PdfReader(fh)
        for page in reader.pages:
            extracted = page.extract_text() or ""
            if extracted:
                parts.append(extracted)
    return "\n".join(parts)


def read_document(path: str | Path) -> str:
    """Perceive a document at `path` and return its plain text.

    Dispatches on file extension (.pdf / .txt). Raises:
        FileNotFoundError        — path does not exist
        DocumentReadError        — path is not a file
        UnsupportedDocumentError — extension is neither .pdf nor .txt
        EmptyDocumentError       — no extractable text was found
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Document not found: {path}")
    if not path.is_file():
        raise DocumentReadError(f"Not a file: {path}")

    suffix = path.suffix.lower()
    if suffix == ".txt":
        text = extract_text_from_txt(path)
    elif suffix == ".pdf":
        text = extract_text_from_pdf(path)
    else:
        raise UnsupportedDocumentError(
            f"Unsupported document type '{suffix or '(none)'}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_SUFFIXES))}"
        )

    if not text or not text.strip():
        raise EmptyDocumentError(
            f"No extractable text in {path.name} "
            "(empty file or image-only/scanned PDF)."
        )
    return text
