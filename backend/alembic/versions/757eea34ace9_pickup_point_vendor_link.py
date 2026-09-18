"""pickup point vendor link

Un point de retrait peut désormais être rattaché à une boutique (vendor_id,
optionnel) — le vendeur garde son compte habituel, aucun rôle supplémentaire
à gérer côté auth. Un point de retrait n'est pas forcément une boutique : ce
champ reste nullable pour les locaux dédiés uniquement au retrait.

Revision ID: 757eea34ace9
Revises: 3b99d0db7232
Create Date: 2026-09-18 04:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '757eea34ace9'
down_revision: Union[str, None] = '3b99d0db7232'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('pickup_points', sa.Column('vendor_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'pickup_points_vendor_id_fkey', 'pickup_points', 'vendors', ['vendor_id'], ['id'], ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('pickup_points_vendor_id_fkey', 'pickup_points', type_='foreignkey')
    op.drop_column('pickup_points', 'vendor_id')
