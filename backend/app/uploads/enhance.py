"""Automatic product photo enhancement — premium vendor feature (see
app/subscriptions/). Runs entirely locally (rembg + the u2netp ONNX model,
baked into the Docker image at build time, see backend/Dockerfile) so it
carries no runtime network dependency, same spirit as self-hosting MinIO
instead of a cloud storage provider (see app/core/storage.py).

Removes the background, crops to the detected subject with a small margin,
composites onto a plain white background (standard product-photo look),
then auto-contrasts/sharpens and upscales if the crop left it small. The
result is handed to storage.upload_image(), which re-compresses/stores it
exactly like a normal upload — this module only ever returns JPEG bytes.
"""

import io

from PIL import Image, ImageEnhance, ImageOps
from rembg import new_session, remove

_TARGET_DIMENSION = 1200
_CROP_MARGIN_RATIO = 0.08
_JPEG_QUALITY = 90

# One session for the process lifetime — loading the ONNX model per request
# would dominate processing time.
_session = new_session("u2netp")


def _padded_bbox(bbox: tuple[int, int, int, int], size: tuple[int, int]) -> tuple[int, int, int, int]:
    left, top, right, bottom = bbox
    width, height = size
    pad_x = round((right - left) * _CROP_MARGIN_RATIO)
    pad_y = round((bottom - top) * _CROP_MARGIN_RATIO)
    return (
        max(0, left - pad_x),
        max(0, top - pad_y),
        min(width, right + pad_x),
        min(height, bottom + pad_y),
    )


def enhance_image(content: bytes) -> bytes:
    image = Image.open(io.BytesIO(content)).convert("RGB")

    cutout = remove(image, session=_session)  # RGBA, subject on transparent background
    bbox = cutout.getbbox()
    if bbox is not None:
        cutout = cutout.crop(_padded_bbox(bbox, cutout.size))

    canvas = Image.new("RGB", cutout.size, (255, 255, 255))
    canvas.paste(cutout, mask=cutout.split()[3])

    canvas = ImageOps.autocontrast(canvas, cutoff=1)
    canvas = ImageEnhance.Sharpness(canvas).enhance(1.15)

    if max(canvas.size) < _TARGET_DIMENSION:
        ratio = _TARGET_DIMENSION / max(canvas.size)
        canvas = canvas.resize((round(canvas.width * ratio), round(canvas.height * ratio)), Image.LANCZOS)

    buffer = io.BytesIO()
    canvas.save(buffer, format="JPEG", quality=_JPEG_QUALITY)
    return buffer.getvalue()
