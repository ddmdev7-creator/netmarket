"""Product image uploads: vendor-only, multipart straight to object storage
(see app/core/storage.py). Returns the object keys the vendor then adds to
Product.images (POST/PATCH /products) — uploading is a separate step from
saving the product, same as picking a file before submitting a form.

Also serves those images back (GET /images/{key}, public — no auth, product
listings are public) — the browser never talks to MinIO directly, only to
this API, so accessing the app from another device on the LAN only ever
depends on the API's own address being reachable, not a second one for
object storage (see app/core/storage.py's module docstring).
"""

import re

from fastapi import APIRouter, Depends, File, Response, UploadFile
from PIL import UnidentifiedImageError

from app.core.deps import require_role
from app.core.exceptions import ConflictError, NotFoundError
from app.core.storage import fetch_image, upload_image
from app.subscriptions.deps import require_premium_vendor
from app.uploads.enhance import enhance_image
from app.uploads.schemas import UploadedImages
from app.users.models import UserRole

router = APIRouter(prefix="/uploads", tags=["uploads"])

_MAX_FILES = 6
_MAX_SIZE_BYTES = 8 * 1024 * 1024
_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
# Toujours "<uuid>.jpg" — voir storage.upload_image. Rejeter tout le reste
# évite de faire suivre à MinIO des clés bizarres (ex. contenant "/").
_KEY_PATTERN = re.compile(r"^[0-9a-f-]{36}\.jpg$")


async def _read_validated(files: list[UploadFile]) -> list[tuple[str, bytes]]:
    """Applies the shared upload constraints, returns (filename, content) pairs."""
    if len(files) > _MAX_FILES:
        raise ConflictError(f"Maximum {_MAX_FILES} images à la fois.")

    contents: list[tuple[str, bytes]] = []
    for file in files:
        if file.content_type not in _ALLOWED_CONTENT_TYPES:
            raise ConflictError(f"Format non supporté pour « {file.filename} ». Utilise JPEG, PNG ou WebP.")

        content = await file.read()
        if len(content) > _MAX_SIZE_BYTES:
            raise ConflictError(f"« {file.filename} » dépasse la taille maximale de 8 Mo.")

        contents.append((file.filename or "image", content))

    return contents


@router.post("/images", response_model=UploadedImages, dependencies=[Depends(require_role(UserRole.VENDOR))])
async def upload_images(files: list[UploadFile] = File(...)) -> UploadedImages:
    contents = await _read_validated(files)

    keys: list[str] = []
    for filename, content in contents:
        try:
            keys.append(upload_image(content))
        except UnidentifiedImageError as exc:
            raise ConflictError(f"« {filename} » n'est pas une image valide.") from exc

    return UploadedImages(keys=keys)


@router.post("/images/enhance", response_model=UploadedImages, dependencies=[Depends(require_premium_vendor)])
async def enhance_images(files: list[UploadFile] = File(...)) -> UploadedImages:
    """Same constraints as /images, but runs each photo through the
    background-removal/crop/upscale pipeline first — see app/uploads/enhance.py.
    Reserved for vendors with an active subscription (app/subscriptions/)."""
    contents = await _read_validated(files)

    keys: list[str] = []
    for filename, content in contents:
        try:
            keys.append(upload_image(enhance_image(content)))
        except UnidentifiedImageError as exc:
            raise ConflictError(f"« {filename} » n'est pas une image valide.") from exc

    return UploadedImages(keys=keys)


@router.get("/images/{key}")
async def get_image(key: str) -> Response:
    if not _KEY_PATTERN.match(key):
        raise NotFoundError("Image introuvable.")
    content = fetch_image(key)
    if content is None:
        raise NotFoundError("Image introuvable.")
    # 1 an, immuable : chaque upload obtient une clé fraîche (uuid4), une
    # image existante ne change donc jamais de contenu sous la même clé.
    return Response(content=content, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=31536000, immutable"})
