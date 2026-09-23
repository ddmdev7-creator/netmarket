"""Codes de remise (QR) opaques et tournants.

Un QR de remise ne contient qu'un code du type « NDJ:7Q2KX9M4RT8WB3ZP » :
aucune information lisible (ni identifiant de commande, ni date). Le code
est un HMAC de (sous-commande, étape, nombre aléatoire de l'étape, créneau
de 60 s) avec une clé dérivée du secret serveur :
- il change toutes les 60 s — une photo ou une capture d'écran devient vite
  inutilisable ;
- la base ne stocke que le nombre aléatoire (SubOrder.handoff_nonce), qui ne
  permet pas de calculer un code sans la clé du serveur ;
- le nombre aléatoire est propre à l'étape (SubOrder.handoff_stage) et
  effacé à chaque changement de statut : un code scanné, ou d'une étape
  passée, ne sert plus jamais.

Le serveur retrouve la sous-commande en ne comparant le code qu'aux colis
affectés à la personne qui scanne (voir service.confirm_delivery_by_code) —
un code n'est donc utilisable que par le livreur ou le gestionnaire affecté,
connecté dans l'application.
"""

import base64
import hashlib
import hmac
import secrets
import time

from app.core.config import get_settings
from app.orders.models import SubOrder

settings = get_settings()

WINDOW_SECONDS = 60
PREFIX = "NDJ:"
_CODE_LENGTH = 16
# Clé dédiée, dérivée du secret JWT : un code de remise ne peut jamais servir
# de jeton d'authentification, et inversement.
_KEY = hashlib.sha256(b"netmarket-handoff:" + settings.jwt_secret_key.encode()).digest()


def _window(now: float) -> int:
    return int(now // WINDOW_SECONDS)


def _code(sub_order: SubOrder, window: int) -> str:
    message = f"{sub_order.id}:{sub_order.handoff_stage}:{sub_order.handoff_nonce}:{window}".encode()
    digest = hmac.new(_KEY, message, hashlib.sha256).digest()
    return base64.b32encode(digest).decode()[:_CODE_LENGTH]


def ensure_stage_nonce(sub_order: SubOrder) -> None:
    """Tire un nombre aléatoire pour l'étape en cours s'il n'y en a pas encore
    (le caller commit)."""
    stage = sub_order.status.value
    if sub_order.handoff_nonce is None or sub_order.handoff_stage != stage:
        sub_order.handoff_nonce = secrets.token_urlsafe(24)
        sub_order.handoff_stage = stage


def reset(sub_order: SubOrder) -> None:
    """Appelé à chaque changement de statut : invalide tout code émis."""
    sub_order.handoff_nonce = None
    sub_order.handoff_stage = None


def current_code(sub_order: SubOrder, now: float | None = None) -> tuple[str, int]:
    """(contenu du QR, secondes avant renouvellement)."""
    now = time.time() if now is None else now
    expires_in = WINDOW_SECONDS - int(now % WINDOW_SECONDS)
    return PREFIX + _code(sub_order, _window(now)), expires_in


def normalize(raw: str) -> str:
    value = raw.strip().upper()
    return value[len(PREFIX):] if value.startswith(PREFIX) else value


def matches(sub_order: SubOrder, code: str, now: float | None = None) -> bool:
    """Code valable pour l'étape en cours : créneau actuel ou précédent (un QR
    affiché juste avant son renouvellement reste lisible le temps du scan)."""
    if not sub_order.handoff_nonce or sub_order.handoff_stage != sub_order.status.value:
        return False
    now = time.time() if now is None else now
    window = _window(now)
    return any(hmac.compare_digest(code, _code(sub_order, w)) for w in (window, window - 1))
