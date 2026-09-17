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
     .app-shell--catalog) sans media query dédiée ici — 2 colonnes sur
     téléphone (comportement inchangé), jusqu'à 6+ sur grand écran. */
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 10px;
}
</style>
