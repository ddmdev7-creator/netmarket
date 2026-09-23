"""pickup point applications

Candidatures gestionnaire de point de retrait (app/pickup_point_applications) :
dossier du candidat, examen admin (validation, seconde chance, refus
définitif), invitations. Horaires d'ouverture sur les points de retrait.

Revision ID: f7c2a9e4b1d8
Revises: e5b9c3d1a7f2
Create Date: 2026-09-23 20:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f7c2a9e4b1d8'
down_revision: Union[str, None] = 'e5b9c3d1a7f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

application_status = postgresql.ENUM(
    'draft', 'submitted', 'changes_requested', 'approved', 'rejected', name='pickup_application_status', create_type=False
)
application_origin = postgresql.ENUM('self', 'invited', name='pickup_application_origin', create_type=False)
id_document_type = postgresql.ENUM('cni_biometrique', 'passeport', name='id_document_type', create_type=False)

NOTIFICATION_TYPES = (
    'pickup_application_invited',
    'pickup_application_submitted',
    'pickup_application_approved',
    'pickup_application_changes_requested',
    'pickup_application_rejected',
)


def upgrade() -> None:
    for value in NOTIFICATION_TYPES:
        op.execute(f"ALTER TYPE notification_type ADD VALUE IF NOT EXISTS '{value}'")
    bind = op.get_bind()
    application_status.create(bind, checkfirst=True)
    application_origin.create(bind, checkfirst=True)

    op.create_table(
        'pickup_point_applications',
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('status', application_status, nullable=False),
        sa.Column('origin', application_origin, nullable=False),
        sa.Column('invited_by', sa.UUID(), nullable=True),
        sa.Column('invited_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('first_name', sa.String(length=100), nullable=True),
        sa.Column('last_name', sa.String(length=100), nullable=True),
        sa.Column('birth_date', sa.Date(), nullable=True),
        sa.Column('residence_address', sa.String(length=300), nullable=True),
        sa.Column('id_document_type', id_document_type, nullable=True),
        sa.Column('id_document_number', sa.String(length=50), nullable=True),
        sa.Column('id_document_front_key', sa.String(), nullable=True),
        sa.Column('id_document_back_key', sa.String(), nullable=True),
        sa.Column('portrait_photo_key', sa.String(), nullable=True),
        sa.Column('point_name', sa.String(length=150), nullable=True),
        sa.Column('point_address', sa.String(length=300), nullable=True),
        sa.Column('point_landmark', sa.String(length=300), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('opening_hours', sa.String(length=300), nullable=True),
        sa.Column('storage_capacity', sa.Integer(), nullable=True),
        sa.Column('premises_photo_keys', postgresql.ARRAY(sa.String()), nullable=False, server_default='{}'),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('submission_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('admin_note', sa.String(length=500), nullable=True),
        sa.Column('admin_suggestion', sa.String(length=500), nullable=True),
        sa.Column('reviewed_by', sa.UUID(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pickup_point_id', sa.UUID(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['pickup_point_id'], ['pickup_points.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )
    op.add_column('pickup_points', sa.Column('opening_hours', sa.String(length=300), nullable=True))


def downgrade() -> None:
    op.drop_column('pickup_points', 'opening_hours')
    op.drop_table('pickup_point_applications')
    bind = op.get_bind()
    application_origin.drop(bind, checkfirst=True)
    application_status.drop(bind, checkfirst=True)
