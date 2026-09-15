"""add courier verification fields

Revision ID: a1c4f7e2b8d3
Revises: 5eb681501ebe
Create Date: 2026-09-15 07:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1c4f7e2b8d3'
down_revision: Union[str, None] = '5eb681501ebe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Comme pour 'courier' sur user_role (voir 9b25433107ab) : autogenerate ne
    # détecte pas les nouvelles valeurs d'un enum Postgres existant.
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'courier_verification_approved'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'courier_verification_rejected'")

    # Contrairement à ALTER TYPE ... ADD VALUE ci-dessus (enum existant), ce
    # type est nouveau — op.add_column ne le crée pas tout seul comme le
    # ferait op.create_table.
    op.execute("CREATE TYPE id_document_type AS ENUM ('cni_biometrique', 'passeport')")

    op.add_column(
        'couriers',
        sa.Column(
            'id_document_type',
            sa.Enum('cni_biometrique', 'passeport', name='id_document_type'),
            nullable=True,
        ),
    )
    op.add_column('couriers', sa.Column('id_document_front_key', sa.String(), nullable=True))
    op.add_column('couriers', sa.Column('id_document_back_key', sa.String(), nullable=True))
    op.add_column('couriers', sa.Column('face_photo_key', sa.String(), nullable=True))
    op.add_column('couriers', sa.Column('vehicle_name', sa.String(length=150), nullable=True))
    op.add_column('couriers', sa.Column('vehicle_plate_number', sa.String(length=50), nullable=True))
    op.add_column(
        'couriers',
        sa.Column(
            'vehicle_photo_keys',
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default='{}',
        ),
    )
    op.add_column('couriers', sa.Column('admin_note', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('couriers', 'admin_note')
    op.drop_column('couriers', 'vehicle_photo_keys')
    op.drop_column('couriers', 'vehicle_plate_number')
    op.drop_column('couriers', 'vehicle_name')
    op.drop_column('couriers', 'face_photo_key')
    op.drop_column('couriers', 'id_document_back_key')
    op.drop_column('couriers', 'id_document_front_key')
    op.drop_column('couriers', 'id_document_type')
    op.execute('DROP TYPE IF EXISTS id_document_type')
