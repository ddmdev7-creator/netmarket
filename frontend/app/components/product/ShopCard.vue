<script setup lang="ts">
import { PhCaretRight, PhGift, PhMapPin, PhSealCheck, PhStar } from '@phosphor-icons/vue'
import type { VendorPublicRead } from '~/types/api'

/** Encart boutique de la fiche produit : qui vend, sa réputation, ses autres produits. */
const props = defineProps<{ vendorId: string; shopName: string }>()

const { apiFetch } = useApi()
const { data: vendor } = await useAsyncData(`vendor-${props.vendorId}`, () =>
  apiFetch<VendorPublicRead>(`/vendors/${props.vendorId}`).catch(() => null),
)

const initials = computed(() =>
  props.shopName
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join(''),
)

const since = computed(() => {
  const raw = vendor.value?.created_at
  if (!raw) return null
  return new Date(raw).toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' })
})

const shopLink = computed(() => ({ path: '/', query: { shop: props.vendorId, shop_name: props.shopName } }))
</script>

<template>
  <NuxtLink :to="shopLink" class="shop">
    <span class="shop__avatar">{{ initials }}</span>
    <span class="shop__body">
      <span class="shop__name">
        {{ shopName }}
        <PhSealCheck v-if="vendor" :size="16" weight="fill" class="shop__seal" aria-label="Vendeur vérifié" />
      </span>
      <span class="shop__meta">
        <template v-if="vendor?.average_rating != null">
          <PhStar :size="12" weight="fill" color="var(--color-accent)" />
          {{ vendor.average_rating.toFixed(1).replace('.', ',') }} ({{ vendor.review_count }} avis)
          <span class="shop__dot">·</span>
        </template>
        <template v-if="vendor?.product_count != null">
          {{ vendor.product_count }} produit{{ vendor.product_count > 1 ? 's' : '' }}
        </template>
      </span>
      <span v-if="vendor?.offers_pickup_delivery" class="shop__offer">
        <PhGift :size="12" weight="fill" /> Retrait offert<template v-if="vendor.pickup_offer_max_amount"> jusqu'à {{ formatGnf(vendor.pickup_offer_max_amount) }}</template><template v-if="vendor.pickup_offer_min_amount"> dès {{ formatGnf(vendor.pickup_offer_min_amount) }} d'achat</template>
      </span>
      <span v-if="vendor?.zone || since" class="shop__meta">
        <template v-if="vendor?.zone"><PhMapPin :size="12" /> {{ vendor.zone }}</template>
        <template v-if="vendor?.zone && since"><span class="shop__dot">·</span></template>
        <template v-if="since">Sur NdjouriMarket depuis {{ since }}</template>
      </span>
    </span>
    <span class="shop__cta">
      Boutique
      <PhCaretRight :size="14" weight="bold" />
    </span>
  </NuxtLink>
</template>

<style scoped>
.shop__offer {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  align-self: flex-start;
  margin: 2px 0;
  padding: 2px 8px;
  border-radius: 999px;
  background: hsl(150 70% var(--tint-bg));
  color: hsl(150 55% var(--tint-fg));
  font-size: 11.5px;
  font-weight: 700;
}

.shop {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-md);
  background: var(--color-neutral-900);
  color: inherit;
  text-decoration: none;
  transition: border-color 0.15s ease;
}

.shop:hover {
  border-color: var(--color-primary);
}

.shop__avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 46px;
  height: 46px;
  flex-shrink: 0;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--color-primary), #4f46e5);
  color: #fff;
  font-family: var(--font-heading);
  font-weight: 800;
  font-size: 16px;
}

.shop__body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.shop__name {
  display: flex;
  align-items: center;
  gap: 4px;
  font-weight: 700;
  font-size: 14.5px;
  color: var(--color-neutral-200);
}

.shop__seal {
  color: var(--color-primary);
  flex-shrink: 0;
}

.shop__meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 3px;
  font-size: 12px;
  color: var(--color-neutral-400);
}

.shop__dot {
  margin: 0 2px;
}

.shop__cta {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
  padding: 7px 10px;
  border-radius: 999px;
  background: var(--color-primary-100);
  color: var(--color-primary-300);
  font-size: 12.5px;
  font-weight: 700;
}
</style>
