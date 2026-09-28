<script setup lang="ts">
import { PhHeart, PhHeartBreak, PhTrendDown } from '@phosphor-icons/vue'
import type { FavoriteRead } from '~/types/api'

definePageMeta({ middleware: 'auth' })

const { apiFetch } = useApi()
const favoritesStore = useFavoritesStore()

const { data: favorites, pending, refresh } = await useAsyncData(
  'my-favorites',
  () => apiFetch<FavoriteRead[]>('/favorites'),
  { default: () => [], getCachedData: hydrateThenRefetch },
)

// Un cœur décoché sur cette page retire la carte (sans recharger).
const visible = computed(() =>
  favorites.value.filter((f) => !favoritesStore.loaded || favoritesStore.has(f.product.id)),
)

function currentPrice(f: FavoriteRead): number {
  const prices = f.product.variants.map((v) => v.price ?? f.product.price)
  return prices.length ? Math.min(...prices) : f.product.price
}

function dropPct(f: FavoriteRead): number | null {
  const now = currentPrice(f)
  if (now >= f.price_at_add) return null
  return Math.round(((f.price_at_add - now) / f.price_at_add) * 100)
}

const drops = computed(() => visible.value.filter((f) => dropPct(f) !== null).length)

onMounted(() => {
  favoritesStore.ensureLoaded()
})
</script>

<template>
  <div class="fav-page">
    <header class="fav-page__head">
      <span class="fav-page__icon"><PhHeart :size="22" weight="fill" /></span>
      <div>
        <h1 class="fav-page__title">Mes favoris</h1>
        <p class="fav-page__sub">
          <template v-if="visible.length">
            {{ visible.length }} produit{{ visible.length > 1 ? 's' : '' }}
            <template v-if="drops"> · <strong>{{ drops }} en baisse de prix</strong></template>
          </template>
          <template v-else>Gardez ici les produits qui vous plaisent.</template>
        </p>
      </div>
    </header>

    <p v-if="visible.length" class="fav-page__hint">
      Nous vous prévenons quand un favori baisse de prix ou revient en stock.
    </p>

    <div v-if="pending && !favorites.length" class="product-grid-lite">
      <v-skeleton-loader v-for="n in 4" :key="n" type="card" />
    </div>

    <div v-else-if="!visible.length" class="fav-empty">
      <span class="fav-empty__icon"><PhHeartBreak :size="34" weight="duotone" /></span>
      <h2>Aucun favori pour l'instant</h2>
      <p>Touchez le cœur sur un produit pour le retrouver ici et être alerté des baisses de prix.</p>
      <v-btn color="primary" to="/">Découvrir les produits</v-btn>
    </div>

    <div v-else class="product-grid-lite">
      <div v-for="f in visible" :key="f.product.id" class="fav-cell">
        <span v-if="dropPct(f)" class="fav-cell__drop">
          <PhTrendDown :size="12" weight="bold" /> −{{ dropPct(f) }} %
        </span>
        <ProductCard :product="f.product" />
      </div>
    </div>

    <div v-if="!pending && visible.length" class="text-center mt-4">
      <v-btn variant="text" size="small" @click="refresh()">Actualiser</v-btn>
    </div>
  </div>
</template>

<style scoped>
.fav-page {
  padding: 16px 12px;
}

@media (min-width: 960px) {
  .fav-page {
    padding: 24px 32px;
  }
}

.fav-page__head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.fav-page__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: hsl(355 80% var(--tint-bg));
  color: #e5484d;
}

.fav-page__title {
  font-family: var(--font-heading);
  font-size: 20px;
  font-weight: 800;
  margin: 0;
}

.fav-page__sub {
  margin: 0;
  font-size: 13px;
  color: var(--color-neutral-400);
}

.fav-page__sub strong {
  color: var(--color-success);
}

.fav-page__hint {
  margin: 0 0 14px;
  font-size: 12.5px;
  color: var(--color-neutral-500);
}

.product-grid-lite {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 8px;
}

@media (min-width: 960px) {
  .product-grid-lite {
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 16px;
  }
}

/* Le badge se pose en bas à gauche de la photo (carrée, en haut de la
   carte) : 100cqw = largeur de la carte = hauteur de la photo. Le coin
   haut-gauche reste à l'étiquette de stock, le haut-droit au cœur. */
.fav-cell {
  position: relative;
  container-type: inline-size;
}

.fav-cell__drop {
  position: absolute;
  z-index: 3;
  top: calc(100cqw - 32px);
  left: 8px;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--color-success);
  color: #fff;
  font-size: 11px;
  font-weight: 800;
}

.fav-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 48px 16px;
}

.fav-empty__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 72px;
  margin-bottom: 14px;
  border-radius: 50%;
  background: hsl(355 80% var(--tint-bg));
  color: #e5484d;
}

.fav-empty h2 {
  font-family: var(--font-heading);
  font-size: 18px;
  font-weight: 800;
  margin: 0 0 6px;
}

.fav-empty p {
  max-width: 320px;
  margin: 0 0 18px;
  font-size: 13.5px;
  color: var(--color-neutral-400);
}
</style>
