from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError


MAX_IMAGE_PIXELS = 25_000_000
MAX_IMAGE_DIMENSION = 2400


class InvalidPropertyPhoto(Exception):
    pass


def normalize_property_photo(contents, max_bytes):
    if not contents:
        raise InvalidPropertyPhoto("The image is empty")
    if len(contents) > max_bytes:
        raise InvalidPropertyPhoto(
            f"Images must be no larger than {max_bytes // (1024 * 1024)} MB"
        )

    try:
        with Image.open(BytesIO(contents)) as image:
            image.verify()
        with Image.open(BytesIO(contents)) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise InvalidPropertyPhoto("Only JPG, PNG, and WebP images are supported")
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise InvalidPropertyPhoto("The image dimensions are too large")
            if getattr(image, "n_frames", 1) != 1:
                raise InvalidPropertyPhoto("Animated images are not supported")

            image_format = image.format
            image = ImageOps.exif_transpose(image)
            image.thumbnail(
                (MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION),
                Image.Resampling.LANCZOS,
            )
            output = BytesIO()
            if image_format == "JPEG":
                image.convert("RGB").save(
                    output, format="JPEG", quality=88, optimize=True
                )
                content_type = "image/jpeg"
            elif image_format == "PNG":
                image.convert("RGBA").save(output, format="PNG", optimize=True)
                content_type = "image/png"
            else:
                mode = "RGBA" if "A" in image.getbands() else "RGB"
                image.convert(mode).save(output, format="WEBP", quality=88)
                content_type = "image/webp"
    except InvalidPropertyPhoto:
        raise
    except (
        Image.DecompressionBombError,
        OSError,
        UnidentifiedImageError,
        ValueError,
    ) as error:
        raise InvalidPropertyPhoto("The uploaded file is not a valid supported image") from error

    normalized = output.getvalue()
    if len(normalized) > max_bytes:
        raise InvalidPropertyPhoto(
            f"Images must be no larger than {max_bytes // (1024 * 1024)} MB"
        )
    return normalized, content_type
