<script setup lang="ts">
import { PhImage, PhStar } from '@phosphor-icons/vue'
import type { ProductRead } from '~/types/api'

defineProps<{ product: ProductRead }>()

const apiBase = useApiBase()
</script>

<template>
  <NuxtLink :to="`/produits/${product.id}`" class="product-card">
    <v-card class="product-card__card">
      <div class="product-card__image">
        <img
          v-if="product.images[0]"
          :src="resolveImageUrl(product.images[0], apiBase)"
          :alt="product.name"
          loading="lazy"
        />
        <PhImage v-else :size="28" weight="light" color="var(--color-neutral-500)" />
      </div>
      <v-card-text class="pa-2 product-card__body">
        <div class="product-card__name">{{ product.name }}</div>
        <div class="product-card__price">{{ formatGnf(product.price) }}</div>
        <div v-if="product.average_rating !== null" class="product-card__rating">
          <PhStar :size="11" weight="fill" color="var(--color-accent)" />
          <span>{{ product.average_rating.toFixed(1) }}</span>
          <span class="product-card__rating-count">({{ product.review_count }})</span>
        </div>
        <div class="product-card__shop">{{ product.vendor_shop_name }}</div>
      </v-card-text>
    </v-card>
  </NuxtLink>
</template>

<style scoped>
.product-card {
  text-decoration: none;
  color: inherit;
  display: block;
  /* La grille (ProductGrid) étire déjà chaque item de rangée à la même
     hauteur (comportement grid par défaut) — sans cette hauteur explicite ici
     et sur .product-card__card ci-dessous, seule la zone cliquable suivrait,
     pas le cadre visuel de la carte, donc les bas de cartes resteraient
     décalés entre deux fiches de longueurs de nom différentes. */
  height: 100%;
}

.product-card__card {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.product-card__image {
  /* Carré plutôt qu'une bande basse et large : plus de hauteur pour que
     l'image se déploie vraiment, et un ratio stable quel que soit le format
     de la photo source. */
  aspect-ratio: 1 / 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-neutral-800);
  border-radius: var(--radius-md) var(--radius-md) 0 0;
  overflow: hidden;
  padding: 8px;
  box-sizing: border-box;
}

.product-card__image img {
  width: 100%;
  height: 100%;
  /* "contain" plutôt que "cover" : l'image entière reste visible (jamais
     rognée), quitte à laisser un léger fond neutre sur les côtés pour les
     photos qui ne sont pas déjà carrées. */
  object-fit: contain;
}

.product-card__body {
  display: flex;
  flex-direction: column;
  /* Comble le reste de la carte étirée par la grille, pour que le nom de
     boutique s'aligne en bas d'une rangée même quand les noms de produit
     font 1 ou 2 lignes selon la fiche. */
  flex: 1;
}

.product-card__name {
  font-size: 12.5px;
  line-height: 1.3;
  min-height: 2.6em;
}

.product-card__price {
  font-family: var(--font-heading);
  font-size: 13px;
  font-weight: 600;
  margin-top: 4px;
  /* Prix en orange, seule dérogation à la charte primary (bleu) sur la
     carte — même logique que les étoiles de notation : accroche l'œil sur
     ce qui doit se voir en premier, comme sur une fiche produit Ozon. */
  color: var(--color-accent);
}

.product-card__rating {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 10.5px;
  margin-top: 2px;
}

.product-card__rating-count {
  color: var(--color-neutral-500);
}

.product-card__shop {
  font-size: 10.5px;
  color: var(--color-neutral-500);
  /* auto plutôt qu'une valeur fixe : pousse le nom de boutique en bas de
     .product-card__body (flex column, flex: 1), pour aligner ce repère sur
     toute une rangée même quand les noms de produit font 1 ou 2 lignes. */
  margin-top: auto;
  padding-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
