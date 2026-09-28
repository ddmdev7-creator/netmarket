<script setup lang="ts">
import type { ProductRead } from '~/types/api'

defineProps<{ products: ProductRead[]; loading?: boolean }>()
</script>

<template>
  <div v-if="loading" class="product-grid">
    <v-skeleton-loader v-for="n in 4" :key="n" type="card" />
  </div>
  <CommonEmptyState v-else-if="products.length === 0" message="Aucun produit ne correspond à ces critères." />
  <div v-else class="product-grid">
    <ProductCard v-for="product in products" :key="product.id" :product="product" />
  </div>
</template>

<style scoped>
.product-grid {
  display: grid;
  /* auto-fill (pas auto-fit) : les colonnes vides sont conservées, donc une
     catégorie à 1 ou 2 produits garde des cartes de taille normale alignées
     à gauche au lieu de les étirer sur toute la largeur de l'écran. 2
     colonnes sur téléphone, davantage à mesure que la fenêtre s'élargit. */
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 8px;
}

/* Desktop : un minmax bien plus large réduit le nombre de colonnes (au
   profit de cartes nettement plus grandes) qu'une grille dense de petites
   vignettes sur un grand écran -- plus lisible. */
@media (min-width: 960px) {
  .product-grid {
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 16px;
  }
}
</style>
