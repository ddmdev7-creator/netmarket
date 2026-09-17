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
  /* auto-fill + minmax plutôt que des colonnes fixes : suit naturellement
     la largeur de .app-shell (480px mobile, jusqu'à 1120px sur desktop via
     .app-shell--catalog) -- 2 colonnes sur téléphone (comportement
     inchangé, un minmax plus élevé ne changerait rien tant qu'il reste
     sous le seuil qui ferait basculer à 1 colonne sur les petits écrans).
     Le gap plus serré (8px, au lieu de 10) et le padding de page réduit
     (voir pages/index.vue) sont ce qui élargit réellement chaque carte ici
     -- à nombre de colonnes égal, c'est le seul levier qui compte. */
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 8px;
}

/* Desktop : un minmax bien plus large réduit le nombre de colonnes (4 sur
   la largeur de .app-shell--catalog, au lieu de 6-7 avec le seuil mobile)
   au profit de cartes nettement plus grandes -- plus lisible qu'une grille
   dense de petites vignettes sur un grand écran. */
@media (min-width: 960px) {
  .product-grid {
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 16px;
  }
}
</style>
