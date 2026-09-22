"""Application settings, loaded from environment variables (.env in local dev)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    api_port: int = 8000

    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    # Secret gating POST /auth/admin-bootstrap (app/auth/service.py::bootstrap_admin) —
    # the one-time endpoint that creates the first admin account. Unset by
    # default so the endpoint is refused (no default admin backdoor).
    admin_bootstrap_token: str | None = None

    # Envoi via l'API transactionnelle Brevo (plus de SMTP) — voir
    # app/core/email.py. Sans clé (dev/CI sans compte Brevo), l'email est
    # juste loggé, jamais réellement envoyé.
    brevo_api_key: str | None = None
    brevo_sender_name: str = "Marketplace Guinée"
    brevo_sender_email: str = "no-reply@netmarket.ndjouri.com"

    # Base du frontend, pour construire les URLs de retour transmises aux
    # prestataires de paiement externes (returnUrl Djomy, voir
    # app/payments/provider.py::DjomyProvider) — jamais utilisée pour un appel
    # serveur, seulement pour composer un lien renvoyé au navigateur.
    frontend_url: str = "https://netmarket.ndjouri.com"

    # Paiement en ligne via Djomy (https://developers.djomy.africa) — voir
    # app/payments/djomy_client.py. Sans clé, seul CashOnDeliveryProvider
    # reste enregistré (app/payments/provider.py), aucun compte externe requis
    # pour développer/tester le reste de l'app.
    djomy_client_id: str | None = None
    djomy_client_secret: str | None = None
    djomy_base_url: str = "https://sandbox-api.djomy.africa"

    # Stockage objet (MinIO en dev, S3-compatible) pour les images produit —
    # voir app/core/storage.py. Uniquement le réseau docker interne : l'API
    # est la seule à parler à MinIO directement, le navigateur passe par
    # GET /uploads/images/{key} (voir app/uploads/router.py) plutôt que par
    # une deuxième adresse publique à tenir à jour.
    storage_endpoint: str = "http://localhost:9000"
    storage_access_key: str = "minioadmin"
    storage_secret_key: str = "minioadmin"
    storage_bucket: str = "product-images"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (avoids re-parsing env on every call)."""
    return Settings()
