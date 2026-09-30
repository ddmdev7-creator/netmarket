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

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.concurrency import run_in_threadpool
from PIL import UnidentifiedImageError

from app.core.deps import get_db, require_role
from app.core.exceptions import ConflictError, NotFoundError
from app.core.storage import VARIANT_WIDTHS, fetch_image, fetch_image_variant, upload_image
from app.subscriptions import quotas
from app.subscriptions.models import UsageKind
from app.vendors import service as vendors_service
from app.uploads.enhance import enhance_image
from app.uploads.schemas import UploadedImages
from app.users.models import User, UserRole
from app.vendors.models import Vendor

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


async def _enhancing_vendor(
    current_user: User = Depends(require_role(UserRole.VENDOR)), db: AsyncSession = Depends(get_db)
) -> Vendor:
    return await vendors_service.get_my_vendor(db, current_user)


@router.post("/images/enhance", response_model=UploadedImages)
async def enhance_images(
    files: list[UploadFile] = File(...),
    vendor: Vendor = Depends(_enhancing_vendor),
    db: AsyncSession = Depends(get_db),
) -> UploadedImages:
    """Same constraints as /images, but runs each photo through the
    background-removal/crop/upscale pipeline first — see app/uploads/enhance.py.
    Counted against the vendor's monthly AI quota (app/subscriptions/quotas.py)."""
    contents = await _read_validated(files)
    await quotas.ensure_ai_available(db, vendor.id, len(contents))

    keys: list[str] = []
    for filename, content in contents:
        try:
            # Détourage ONNX : plusieurs secondes de CPU — hors de la boucle
            # d'événements, sinon toute l'API se fige pendant ce temps.
            keys.append(await run_in_threadpool(_enhance_and_store, content))
        except UnidentifiedImageError as exc:
            raise ConflictError(f"« {filename} » n'est pas une image valide.") from exc

    await quotas.record_usage(db, vendor.id, UsageKind.AI_ENHANCEMENT, len(keys))
    return UploadedImages(keys=keys)


def _enhance_and_store(content: bytes) -> str:
    return upload_image(enhance_image(content))


@router.post("/images/{key}/enhance", response_model=UploadedImages)
async def enhance_stored_image(
    key: str, vendor: Vendor = Depends(_enhancing_vendor), db: AsyncSession = Depends(get_db)
) -> UploadedImages:
    """Améliore une photo déjà envoyée (bouton « Améliorer » sur la vignette).
    L'original reste intact sous sa clé : le résultat reçoit une clé neuve,
    que le formulaire met à la place de l'ancienne."""
    if not _KEY_PATTERN.match(key):
        raise NotFoundError("Image introuvable.")
    content = await run_in_threadpool(fetch_image, key)
    if content is None:
        raise NotFoundError("Image introuvable.")
    await quotas.ensure_ai_available(db, vendor.id, 1)
    fresh = await run_in_threadpool(_enhance_and_store, content)
    await quotas.record_usage(db, vendor.id, UsageKind.AI_ENHANCEMENT)
    return UploadedImages(keys=[fresh])


@router.get("/images/{key}")
async def get_image(
    key: str,
    request: Request,
    w: int | None = Query(default=None, description="Largeur réduite (160, 320, 480 ou 800)"),
) -> Response:
    if not _KEY_PATTERN.match(key):
        raise NotFoundError("Image introuvable.")
    if w is not None:
        # Largeur hors liste : ramenée à la plus proche au-dessus (ou la plus grande).
        width = next((v for v in VARIANT_WIDTHS if v >= w), VARIANT_WIDTHS[-1])
        webp = "image/webp" in request.headers.get("accept", "")
        variant = await run_in_threadpool(fetch_image_variant, key, width, webp=webp)
        if variant is None:
            raise NotFoundError("Image introuvable.")
        content, media_type = variant
        return Response(
            content=content,
            media_type=media_type,
            headers={"Cache-Control": "public, max-age=31536000, immutable", "Vary": "Accept"},
        )
    content = fetch_image(key)
    if content is None:
        raise NotFoundError("Image introuvable.")
    # 1 an, immuable : chaque upload obtient une clé fraîche (uuid4), une
    # image existante ne change donc jamais de contenu sous la même clé.
    return Response(content=content, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=31536000, immutable"})
