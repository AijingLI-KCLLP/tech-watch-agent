import hashlib
import mimetypes
import re
from io import BytesIO
from pathlib import Path

from config import IMAGE_EXTRACTION_MODE, ROOT, UPLOADS_DIR
from core.models import OriginalType


class ContentExtractionError(ValueError):
    """Raised when submitted content cannot be turned into usable text."""


def normalize_text(text: str) -> str:
    """Preserve paragraph boundaries while removing transport and whitespace noise."""
    cleaned = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = []
    for paragraph in re.split(r"\n\s*\n", cleaned):
        normalized = " ".join(paragraph.split())
        if normalized:
            paragraphs.append(normalized)

    result = "\n\n".join(paragraphs)
    if not result:
        raise ContentExtractionError("The submitted content contains no readable text.")
    return result


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def persist_upload(content: bytes, filename: str, digest: str) -> str:
    """Store raw uploads by content hash so repeated uploads do not duplicate files."""
    suffix = Path(filename).suffix.lower()
    path = UPLOADS_DIR / f"{digest}{suffix}"
    if not path.exists():
        path.write_bytes(content)
    return str(path.relative_to(ROOT))


def _detect_type(filename: str, mime_type: str | None) -> tuple[OriginalType, str]:
    guessed_mime_type, _ = mimetypes.guess_type(filename)
    resolved_mime_type = (mime_type or guessed_mime_type or "").lower()
    extension = Path(filename).suffix.lower()

    if resolved_mime_type == "application/pdf" or extension == ".pdf":
        return OriginalType.PDF, "application/pdf"
    if resolved_mime_type.startswith("image/") or extension in {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".gif",
        ".tiff",
    }:
        return OriginalType.IMAGE, resolved_mime_type or "image/*"
    if resolved_mime_type.startswith("text/") or extension in {
        ".txt",
        ".md",
        ".markdown",
        ".html",
        ".htm",
        ".csv",
    }:
        return OriginalType.TEXT, resolved_mime_type or "text/plain"

    raise ContentExtractionError(
        "Unsupported file type. Upload text, PDF, or image content."
    )


def _extract_pdf(content: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(content))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    except ImportError as exc:
        raise ContentExtractionError("Install pypdf to extract PDF files.") from exc
    except Exception as exc:
        raise ContentExtractionError(f"Could not extract PDF text: {exc}") from exc


def _extract_image(content: bytes) -> str:
    if IMAGE_EXTRACTION_MODE == "vision":
        raise ContentExtractionError(
            "IMAGE_EXTRACTION_MODE=vision is not implemented yet. "
            "Use IMAGE_EXTRACTION_MODE=ocr."
        )
    if IMAGE_EXTRACTION_MODE != "ocr":
        raise ContentExtractionError(
            "IMAGE_EXTRACTION_MODE must be either 'ocr' or 'vision'."
        )

    try:
        import pytesseract
        from PIL import Image

        image = Image.open(BytesIO(content))
        return pytesseract.image_to_string(image)
    except ImportError as exc:
        raise ContentExtractionError(
            "Install Pillow and pytesseract to extract image text."
        ) from exc
    except pytesseract.TesseractNotFoundError as exc:
        raise ContentExtractionError(
            "Tesseract is not installed. On macOS run: brew install tesseract"
        ) from exc
    except Exception as exc:
        raise ContentExtractionError(f"Could not OCR image text: {exc}") from exc


def extract_file_content(
    content: bytes,
    filename: str,
    mime_type: str | None,
) -> tuple[OriginalType, str, str]:
    """Return input type, normalized MIME type, and extracted text for one upload."""
    original_type, normalized_mime_type = _detect_type(filename, mime_type)

    if original_type is OriginalType.TEXT:
        extracted_text = content.decode("utf-8", errors="replace")
    elif original_type is OriginalType.PDF:
        extracted_text = _extract_pdf(content)
    else:
        extracted_text = _extract_image(content)

    return original_type, normalized_mime_type, normalize_text(extracted_text)
