"""reseed default subscription plan if missing

La ligne "Premium mensuel" créée par 5eb681501ebe (bulk_insert dans la même
migration que la table) n'existe plus sur au moins un environnement de
production, alors qu'alembic la considère comme déjà appliquée — plus aucun
plan n'est donc jamais retourné par GET /subscriptions/plans, et
/vendeur/abonnement n'affiche aucune offre à laquelle s'abonner. Cette
migration réinsère le plan par défaut, mais seulement si la table est
vide : sans cette garde, elle dupliquerait le plan sur tout environnement
où le seed original a bien fonctionné.

Revision ID: 279c1a5b4d0b
Revises: 6efa305dfebd
Create Date: 2026-09-17 15:40:00.000000

"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '279c1a5b4d0b'
down_revision: Union[str, None] = '6efa305dfebd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    already_seeded = conn.execute(sa.text("SELECT 1 FROM subscription_plans LIMIT 1")).first()
    if already_seeded:
        return

    conn.execute(
        sa.text(
            """
            INSERT INTO subscription_plans (id, name, price_gnf, duration_days, is_active, created_at, updated_at)
            VALUES (:id, :name, :price_gnf, :duration_days, :is_active, now(), now())
            """
        ),
        {
            'id': uuid.uuid4(),
            'name': 'Premium mensuel',
            'price_gnf': 20000,
            'duration_days': 30,
            'is_active': True,
        },
    )


def downgrade() -> None:
    # Migration de données uniquement (pas de changement de schéma) -- rien
    # à annuler qui ne risquerait pas de retirer un plan légitimement recréé
    # entre-temps.
    pass
