"""courier invitation email purpose

Ajoute 'courier_invitation' à l'enum email_code_purpose — un compte livreur
créé directement par un admin reçoit désormais un code par email pour
activer son compte (définir son mot de passe) avant de compléter lui-même
son profil (pièces d'identité, véhicule).

Revision ID: 524706130b04
Revises: cfba4922a688
Create Date: 2026-09-18 05:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '524706130b04'
down_revision: Union[str, None] = 'cfba4922a688'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE email_code_purpose ADD VALUE IF NOT EXISTS 'courier_invitation'")


def downgrade() -> None:
    pass  # Postgres n'autorise pas de retirer une valeur d'enum facilement
