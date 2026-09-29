"""courier live position

Horodatage de la dernière position envoyée en direct par un livreur pendant
une course (suivi du colis par l'acheteur).

Revision ID: e2b6d9a4c7f1
Revises: d4a8e2f6b1c9
Create Date: 2026-09-29 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e2b6d9a4c7f1'
down_revision: Union[str, None] = 'd4a8e2f6b1c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('couriers', sa.Column('position_updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('couriers', 'position_updated_at')
