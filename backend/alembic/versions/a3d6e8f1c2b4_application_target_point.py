"""application target point

Invitation d'un acheteur existant à gérer un point de retrait QUI EXISTE
DÉJÀ (dossier réduit à l'identité, rattachement au point à la validation).

Revision ID: a3d6e8f1c2b4
Revises: f7c2a9e4b1d8
Create Date: 2026-09-23 21:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a3d6e8f1c2b4'
down_revision: Union[str, None] = 'f7c2a9e4b1d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('pickup_point_applications', sa.Column('target_pickup_point_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_pickup_point_applications_target_point',
        'pickup_point_applications',
        'pickup_points',
        ['target_pickup_point_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_pickup_point_applications_target_point', 'pickup_point_applications', type_='foreignkey')
    op.drop_column('pickup_point_applications', 'target_pickup_point_id')
