import io
import re

from errors import AppError


def _clean(text: str) -> str:
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text(filename: str, data: bytes) -> str:
    """Return the readable text of a .txt or .pdf upload, or raise AppError."""
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

    if suffix == "txt":
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("latin-1")
    elif suffix == "pdf":
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                try:
                    unlocked = reader.decrypt("")
                except Exception:
                    unlocked = 0
                if not unlocked:
                    raise AppError(
                        "encrypted_pdf",
                        "This PDF is password-protected. Remove the password and upload it again.",
                        422,
                    )
            text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
        except AppError:
            raise
        except Exception:
            raise AppError(
                "bad_pdf",
                "This PDF could not be read. Check that the file isn't damaged, or export it as TXT.",
                422,
            )
    else:
        raise AppError("unsupported_file", "Upload a PDF or TXT file.", 415)

    text = _clean(text)
    if not text:
        raise AppError(
            "no_text",
            "No readable text was found. If this is a scanned PDF, run OCR on it first and upload the text version.",
            422,
        )
    return text
