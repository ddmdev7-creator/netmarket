"""generalize email verification codes into purpose-scoped email codes

Revision ID: 6efa305dfebd
Revises: f3d8b21a9c47
Create Date: 2026-09-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6efa305dfebd'
down_revision: Union[str, None] = 'f3d8b21a9c47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

purpose_enum = sa.Enum('email_verification', 'password_reset', name='email_code_purpose')


def upgrade() -> None:
    op.drop_constraint('email_verification_codes_user_id_key', 'email_verification_codes', type_='unique')
    op.rename_table('email_verification_codes', 'email_codes')

    purpose_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'email_codes',
        sa.Column('purpose', purpose_enum, nullable=False, server_default='email_verification'),
    )
    op.alter_column('email_codes', 'purpose', server_default=None)

    op.create_unique_constraint('email_codes_user_id_purpose_key', 'email_codes', ['user_id', 'purpose'])


def downgrade() -> None:
    op.drop_constraint('email_codes_user_id_purpose_key', 'email_codes', type_='unique')
    op.drop_column('email_codes', 'purpose')
    purpose_enum.drop(op.get_bind(), checkfirst=True)
    op.rename_table('email_codes', 'email_verification_codes')

    # A user could have both an email-verification and a password-reset code
    # pending — collapse to one row per user before restoring the old
    # single-column unique constraint (arbitrary pick, downgrade path only).
    op.execute(
        """
        DELETE FROM email_verification_codes a
        USING email_verification_codes b
        WHERE a.user_id = b.user_id AND a.id < b.id
        """
    )
    op.create_unique_constraint('email_verification_codes_user_id_key', 'email_verification_codes', ['user_id'])
