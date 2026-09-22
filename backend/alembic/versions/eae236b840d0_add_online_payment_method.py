"""add online payment method

Nouvelle valeur "online" sur l'enum payment_method, pour le paiement en
ligne via Djomy (voir app/payments/provider.py::DjomyProvider) — s'ajoute
à cash_on_delivery plutôt que de le remplacer.

Revision ID: eae236b840d0
Revises: a8bb77863ecd
Create Date: 2026-09-22 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'eae236b840d0'
down_revision: Union[str, None] = 'a8bb77863ecd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE payment_method ADD VALUE IF NOT EXISTS 'online'")


def downgrade() -> None:
    # Postgres ne permet pas de retirer une valeur d'un enum — pas de downgrade
    # possible sans recréer le type (inutile ici : la valeur reste juste inerte).
    pass
