"""add product variants

Nouvelle fonctionnalité : un produit peut désormais avoir des variantes
génériques (couleur, taille, etc. — pas de taxonomie partagée, attributs en
texte libre par variante, cf. product_variant_attributes). Entièrement
optionnel : un produit sans variante n'est pas concerné, aucune donnée
existante n'est modifiée par cette migration.

Product.stock reste tel quel dans le schéma ; côté application, dès qu'un
produit a au moins une variante, ce champ devient une somme dénormalisée du
stock de ses variantes (voir app/catalog/service.py::_sync_product_stock_from_variants)
— choix délibéré pour que les filtres/tris/tableaux de bord existants
(in_stock, stock_level...) continuent de fonctionner sans modification.

cart_items.variant_id est en ON DELETE CASCADE (donnée transitoire : si une
variante est supprimée, la ligne panier qui la référence disparaît plutôt
que de retomber silencieusement sur le produit de base avec le mauvais
stock/prix). order_items.variant_id est en ON DELETE SET NULL + nouvelle
colonne variant_label figée, même logique que product_name/unit_price déjà
présents sur order_items : une commande passée doit continuer à afficher ce
qui a été acheté même après suppression de la variante.

Note sur la contrainte unique de cart_items : Postgres traite chaque NULL
comme distinct, donc uq_cart_items_user_product_variant (user_id, product_id,
variant_id) n'empêche pas à elle seule deux lignes sans variante pour le
même produit — comme aujourd'hui, la vraie protection contre les doublons
reste applicative (app/cart/repository.py::get_item_by_product_and_variant).

Revision ID: 3b99d0db7232
Revises: 279c1a5b4d0b
Create Date: 2026-09-17 17:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '3b99d0db7232'
down_revision: Union[str, None] = '279c1a5b4d0b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'product_variants',
        sa.Column('product_id', sa.UUID(), nullable=False),
        sa.Column('sku', sa.String(length=64), nullable=True),
        sa.Column('price', sa.Integer(), nullable=True),
        sa.Column('stock', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('images', sa.ARRAY(sa.String()), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('price >= 0', name='ck_product_variants_price_non_negative'),
        sa.CheckConstraint('stock >= 0', name='ck_product_variants_stock_non_negative'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'product_variant_attributes',
        sa.Column('variant_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('value', sa.String(length=100), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['variant_id'], ['product_variants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('variant_id', 'name', name='uq_product_variant_attributes_variant_name'),
    )

    op.add_column('cart_items', sa.Column('variant_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'cart_items_variant_id_fkey', 'cart_items', 'product_variants', ['variant_id'], ['id'], ondelete='CASCADE'
    )
    op.drop_constraint('uq_cart_items_user_product', 'cart_items', type_='unique')
    op.create_unique_constraint(
        'uq_cart_items_user_product_variant', 'cart_items', ['user_id', 'product_id', 'variant_id']
    )

    op.add_column('order_items', sa.Column('variant_id', sa.UUID(), nullable=True))
    op.add_column('order_items', sa.Column('variant_label', sa.String(length=300), nullable=True))
    op.create_foreign_key(
        'order_items_variant_id_fkey', 'order_items', 'product_variants', ['variant_id'], ['id'], ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('order_items_variant_id_fkey', 'order_items', type_='foreignkey')
    op.drop_column('order_items', 'variant_label')
    op.drop_column('order_items', 'variant_id')

    op.drop_constraint('uq_cart_items_user_product_variant', 'cart_items', type_='unique')
    op.create_unique_constraint('uq_cart_items_user_product', 'cart_items', ['user_id', 'product_id'])
    op.drop_constraint('cart_items_variant_id_fkey', 'cart_items', type_='foreignkey')
    op.drop_column('cart_items', 'variant_id')

    op.drop_table('product_variant_attributes')
    op.drop_table('product_variants')
