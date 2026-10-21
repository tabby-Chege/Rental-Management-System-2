from io import BytesIO

from PIL import Image, UnidentifiedImageError


MAX_IMAGE_PIXELS = 25_000_000


class InvalidTenantDocument(Exception):
    pass


def normalize_tenant_document(contents, max_bytes):
    if not contents:
        raise InvalidTenantDocument("The uploaded document is empty")
    if len(contents) > max_bytes:
        raise InvalidTenantDocument(
            f"Documents must be no larger than {max_bytes // (1024 * 1024)} MB"
        )

    if contents.startswith(b"%PDF-") and b"%%EOF" in contents[-1024:]:
        return contents, "application/pdf"

    try:
        with Image.open(BytesIO(contents)) as image:
            image.verify()
        with Image.open(BytesIO(contents)) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise InvalidTenantDocument(
                    "Only PDF, JPEG, PNG, and WebP documents are supported"
                )
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise InvalidTenantDocument("The image dimensions are too large")
            output = BytesIO()
            if image.format == "JPEG":
                image.convert("RGB").save(output, format="JPEG", quality=90, optimize=True)
                content_type = "image/jpeg"
            elif image.format == "PNG":
                image.convert("RGBA").save(output, format="PNG", optimize=True)
                content_type = "image/png"
            else:
                mode = "RGBA" if "A" in image.getbands() else "RGB"
                image.convert(mode).save(output, format="WEBP", quality=90)
                content_type = "image/webp"
    except InvalidTenantDocument:
        raise
    except (Image.DecompressionBombError, OSError, UnidentifiedImageError, ValueError) as error:
        raise InvalidTenantDocument(
            "The uploaded file is not a valid PDF or supported image"
        ) from error

    normalized = output.getvalue()
    if len(normalized) > max_bytes:
        raise InvalidTenantDocument(
            f"Documents must be no larger than {max_bytes // (1024 * 1024)} MB"
        )
    return normalized, content_type
