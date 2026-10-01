"""Profile photo processing.

Every upload is opened with Pillow and re-drawn as a brand-new 256x256 JPEG.
That one step does several safety jobs at once:
  * only real images get through (a renamed .exe or .html fails to open);
  * hidden data is dropped (GPS location in phone photos, scripts, etc.);
  * every stored photo is small (~10-20 KB), so the database stays light.
"""
import io
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

PHOTO_SIZE = 256                                 # stored photos are 256x256 px
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}  # checked from the file's contents, not its name

# A tiny file can claim to be a gigantic image (a "decompression bomb") and
# use up all the server's memory when opened. 25 million pixels is far more
# than any phone camera produces, so anything bigger is refused.
MAX_PIXELS = 25_000_000
# Pillow's own guard only *refuses* images over twice its limit (between 1x
# and 2x it merely warns), so we also check the size ourselves below.
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class PhotoError(ValueError):
    """Raised with a user-friendly message when an upload can't be used."""


def process_photo(file_storage):
    """Turn an uploaded file into JPEG bytes, or raise PhotoError."""
    if not file_storage or not file_storage.filename:
        raise PhotoError("Please choose a photo to upload.")

    try:
        with warnings.catch_warnings():
            # Pillow only *warns* about mid-sized bombs; turn that into an error
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(file_storage.stream)
        if image.format not in ALLOWED_FORMATS:
            raise PhotoError("Please upload a JPG, PNG, WebP or GIF image.")
        # Check the claimed size BEFORE decoding, while it's still cheap
        width, height = image.size
        if width * height > MAX_PIXELS:
            raise PhotoError("That image is too large. Please use a smaller photo.")
        image.load()   # actually decode it, so broken files fail here
    except PhotoError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise PhotoError("That image is too large. Please use a smaller photo.")
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise PhotoError("That file isn't an image we can read. Please upload a JPG, PNG, WebP or GIF.")

    # Phones often store photos sideways plus a "rotate me" note; apply it
    image = ImageOps.exif_transpose(image)

    # JPEG has no transparency, so put see-through images on a white background
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        image = image.convert("RGBA")
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.getchannel("A"))
        image = background
    else:
        image = image.convert("RGB")

    # Crop to a centred square and resize, so every avatar is the same shape
    image = ImageOps.fit(image, (PHOTO_SIZE, PHOTO_SIZE), Image.Resampling.LANCZOS)

    output = io.BytesIO()
    image.save(output, format="JPEG", quality=85, optimize=True)
    return output.getvalue()