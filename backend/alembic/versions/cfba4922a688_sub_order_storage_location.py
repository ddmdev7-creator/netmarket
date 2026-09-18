"""sub order storage location

Emplacement de stockage (étagère, case...) au point de retrait, renseigné
par le gestionnaire pour retrouver rapidement un colis à la remise. Texte
libre, optionnel, sans effet sur le cycle de statut de la commande.

Revision ID: cfba4922a688
Revises: 757eea34ace9
Create Date: 2026-09-18 04:05:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'cfba4922a688'
down_revision: Union[str, None] = '757eea34ace9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('sub_orders', sa.Column('storage_location', sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column('sub_orders', 'storage_location')
