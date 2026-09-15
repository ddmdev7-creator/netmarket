"""Object storage for uploaded files (product images) — MinIO in dev
(S3-compatible, self-hosted, no cloud account needed — see cahier des
charges §5.1). Swappable for a real S3/cloud provider later by changing the
STORAGE_* settings only.

Images are proxied through the API (GET /uploads/images/{key}, see
app/uploads/router.py) rather than the browser talking to MinIO directly —
what upload_image returns, and what gets stored in Product.images, is just
the bare object key. That keeps the app reachable from any device on the
LAN through a single address (the API's own host:port, already
auto-detected client-side — see frontend/app/composables/useApiBase.ts):
no second address (MinIO's own host:port) to keep in sync with whatever
network/IP the machine currently has.
"""

import io
import uuid

import boto3
from botocore.exceptions import ClientError
from PIL import Image

from app.core.config import get_settings

settings = get_settings()

# Connectivité mobile lente et coûteuse en Guinée (cahier des charges §1) —
# chaque image est recompressée pour rester légère, quel que soit le poids
# du fichier d'origine envoyé par le vendeur. Elles sont donc toujours
# ré-encodées en JPEG : content-type fixe côté lecture, pas besoin de le
# stocker/retrouver par image.
_MAX_DIMENSION = 1600
_JPEG_QUALITY = 82

_client = boto3.client(
    "s3",
    endpoint_url=settings.storage_endpoint,
    aws_access_key_id=settings.storage_access_key,
    aws_secret_access_key=settings.storage_secret_key,
)

_bucket_ready = False


def _ensure_bucket() -> None:
    global _bucket_ready
    if _bucket_ready:
        return
    try:
        _client.head_bucket(Bucket=settings.storage_bucket)
    except ClientError:
        # Pas de politique publique ici : le bucket n'est plus exposé
        # directement au navigateur, seule l'API (qui a ses propres
        # identifiants) y lit — voir fetch_image ci-dessous.
        _client.create_bucket(Bucket=settings.storage_bucket)
    _bucket_ready = True


def _compress(content: bytes) -> bytes:
    image = Image.open(io.BytesIO(content))
    image = image.convert("RGB")
    image.thumbnail((_MAX_DIMENSION, _MAX_DIMENSION))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
    return buffer.getvalue()


def upload_image(content: bytes, *, prefix: str = "") -> str:
    """Compresses then uploads one image, returns its object key (not a URL —
    see module docstring). `prefix` namespaces the key within the same bucket
    (e.g. "courier-docs/") for content that isn't served through the public
    product-image route — see app/couriers/router.py."""
    _ensure_bucket()
    compressed = _compress(content)
    key = f"{prefix}{uuid.uuid4()}.jpg"
    _client.put_object(Bucket=settings.storage_bucket, Key=key, Body=compressed, ContentType="image/jpeg")
    return key


def fetch_image(key: str) -> bytes | None:
    """Reads back an uploaded image's bytes, or None if the key doesn't
    exist (deleted from the bucket, or never valid — e.g. a malformed key
    guessed by a client)."""
    _ensure_bucket()
    try:
        response = _client.get_object(Bucket=settings.storage_bucket, Key=key)
    except ClientError:
        return None
    return response["Body"].read()
