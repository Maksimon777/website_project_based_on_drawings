from pathlib import Path

from django.core.exceptions import ValidationError

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".docx", ".zip", ".dwg", ".dxf", ".cdw", ".frw", ".m3d", ".a3d", ".spw"}
SIGNATURE_BYTES = 1024


def validate_source_file(upload):
    extension = Path(upload.name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValidationError(f"Файл «{upload.name}»: этот формат не разрешён.")
    if not upload.size:
        raise ValidationError(f"Файл «{upload.name}» пуст.")
    position = upload.tell()
    header = upload.read(SIGNATURE_BYTES)
    upload.seek(position)
    valid = not header.startswith(b"MZ")
    if extension == ".pdf":
        valid = b"%PDF-" in header
    elif extension in {".jpg", ".jpeg"}:
        valid = header.startswith(b"\xff\xd8\xff")
    elif extension == ".png":
        valid = header.startswith(b"\x89PNG\r\n\x1a\n")
    elif extension in {".zip", ".docx"}:
        valid = header.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"))
    elif extension == ".dwg":
        valid = header.startswith(b"AC10")
    elif extension == ".dxf":
        valid = header.startswith(b"AutoCAD Binary DXF") or b"SECTION" in header.upper()
    # KOMPAS formats are stored without conversion or execution. Header checks are
    # basic format checks, not antivirus scanning or proof that a CAD file is valid.
    if not valid:
        raise ValidationError(f"Файл «{upload.name}»: содержимое не соответствует формату.")
