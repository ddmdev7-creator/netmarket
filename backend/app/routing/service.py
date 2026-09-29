"""Itinéraires routiers (tracé du trajet d'une livraison).

Interroge un serveur OSRM (par défaut le serveur public du projet OSRM, sans
clé) et garde les résultats en mémoire quelques minutes : les cartes de suivi
se rafraîchissent souvent, les trajets eux changent peu. En cas d'échec (serveur
injoignable, lenteur), renvoie None — l'interface trace alors une ligne droite.
"""

import logging
import time

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_CACHE_TTL_SECONDS = 600
_CACHE_MAX = 500
_cache: dict[tuple, tuple[float, dict | None]] = {}


def _key(points: list[tuple[float, float]]) -> tuple:
    # ~11 m de précision : un livreur qui bouge un peu réutilise le même trajet.
    return tuple((round(lat, 4), round(lng, 4)) for lat, lng in points)


async def get_route(points: list[tuple[float, float]]) -> dict | None:
    """Trajet routier passant par `points` ((lat, lng), dans l'ordre) :
    {"coordinates": [[lng, lat], ...], "distance_km": float, "duration_min": int}."""
    if len(points) < 2 or any(lat is None or lng is None for lat, lng in points):
        return None
    key = _key(points)
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    path = ";".join(f"{lng},{lat}" for lat, lng in points)
    url = f"{settings.routing_url.rstrip('/')}/route/v1/driving/{path}"
    result: dict | None = None
    try:
        async with httpx.AsyncClient(timeout=4) as client:
            response = await client.get(url, params={"overview": "full", "geometries": "geojson"})
        response.raise_for_status()
        body = response.json()
        route = (body.get("routes") or [None])[0]
        if body.get("code") == "Ok" and route:
            result = {
                "coordinates": route["geometry"]["coordinates"],
                "distance_km": round(route["distance"] / 1000, 1),
                # Durée voiture d'OSRM, majorée pour la circulation d'une grande ville.
                "duration_min": max(2, round(route["duration"] / 60 * 1.3)),
            }
    except (httpx.HTTPError, KeyError, ValueError):
        logger.info("Itinéraire indisponible pour %s", key, exc_info=True)

    if len(_cache) >= _CACHE_MAX:
        _cache.pop(next(iter(_cache)))
    _cache[key] = (time.monotonic(), result)
    return result
