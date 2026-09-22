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
  /* auto-fit + minmax plutôt que des colonnes fixes : suit naturellement la
     largeur de .app-shell (480px mobile, pleine largeur de la fenêtre sur
     desktop via .app-shell--catalog, sans plafond -- voir main.css) -- 2
     colonnes sur téléphone (comportement inchangé, un minmax plus élevé ne
     changerait rien tant qu'il reste sous le seuil qui ferait basculer à 1
     colonne sur les petits écrans). Le gap plus serré (8px, au lieu de 10)
     et le padding de page réduit (voir pages/index.vue) sont ce qui élargit
     réellement chaque carte ici -- à nombre de colonnes égal, c'est le seul
     levier qui compte. auto-fit (pas auto-fill) : sur un grand écran avec peu
     de résultats (recherche/filtre, ou catalogue encore petit), les colonnes
     vides s'effondrent au lieu de laisser les cartes existantes se tasser à
     gauche avec un grand vide à droite -- les cartes restantes se partagent
     alors toute la largeur. */
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 8px;
}

/* Desktop : un minmax bien plus large réduit le nombre de colonnes (au
   profit de cartes nettement plus grandes) qu'une grille dense de petites
   vignettes sur un grand écran -- plus lisible. */
@media (min-width: 960px) {
  .product-grid {
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 16px;
  }
}
</style>
