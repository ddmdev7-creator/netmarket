"""delivery fee tier transit days

Durée de trajet (en jours, au-delà de la préparation du vendeur) par palier
de distance, lue par le même calcul que le tarif (voir
app/delivery/service.py::compute_transit_days) plutôt qu'une heuristique de
zones séparée — remplace app/common/delivery_estimate.py::_is_same_zone.
Les paliers existants démarrent à 1 jour ; à ajuster palier par palier
depuis /admin/frais-livraison.

Revision ID: a8bb77863ecd
Revises: e7b3c9a15f42
Create Date: 2026-09-22 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a8bb77863ecd'
down_revision: Union[str, None] = 'e7b3c9a15f42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'delivery_fee_tiers', sa.Column('transit_days', sa.Integer(), server_default='1', nullable=False)
    )
    op.create_check_constraint(
        'ck_delivery_fee_tiers_transit_days_non_negative', 'delivery_fee_tiers', 'transit_days >= 0'
    )
    # Le défaut serveur n'a servi qu'à remplir les lignes existantes ; les
    # nouveaux paliers passent toujours transit_days explicitement (voir
    # DeliveryFeeTierCreate côté API).
    op.alter_column('delivery_fee_tiers', 'transit_days', server_default=None)


def downgrade() -> None:
    op.drop_constraint('ck_delivery_fee_tiers_transit_days_non_negative', 'delivery_fee_tiers', type_='check')
    op.drop_column('delivery_fee_tiers', 'transit_days')
