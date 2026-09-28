"""category icon

Icône choisie par l'admin pour une catégorie (rangée de catégories de l'accueil).

Revision ID: b1e7c4d9a2f6
Revises: a3d6e8f1c2b4
Create Date: 2026-09-28 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b1e7c4d9a2f6'
down_revision: Union[str, None] = 'a3d6e8f1c2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('categories', sa.Column('icon', sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column('categories', 'icon')
