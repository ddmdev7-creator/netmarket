<script setup lang="ts">
import { PhArrowCounterClockwise, PhCrosshair, PhGift, PhHandCoins, PhStorefront, PhTruck } from '@phosphor-icons/vue'
import type { ProductDeliveryQuote } from '~/types/api'

/**
 * Encart "confiance" sous le prix de la fiche produit : frais et délai de
 * livraison réels (dès que la position de l'acheteur est connue), moyens de
 * paiement, retrait en point, annulation remboursée.
 */
// pickupOfferMin : la boutique offre le retrait en point de retrait dès ce
// montant d'achat (null/undefined : pas d'offre).
const props = defineProps<{ productId: string; pickupOfferMin?: number | null }>()

const { apiFetch } = useApi()
const toast = useToastStore()
const { near, locating, resolve, requestPosition } = useNearPosition()

const quote = ref<ProductDeliveryQuote | null>(null)

async function loadQuote() {
  try {
    quote.value = await apiFetch<ProductDeliveryQuote>(`/products/${props.productId}/delivery-quote`, {
      query: { latitude: near.value?.lat, longitude: near.value?.lng },
    })
  } catch {
    quote.value = null
  }
}

async function locateMe() {
  try {
    await requestPosition()
    await loadQuote()
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Impossible de récupérer ta position.')
  }
}

onMounted(async () => {
  await resolve()
  await loadQuote()
})

const deliveryWindow = computed(() =>
  quote.value ? formatDeliveryEstimate(quote.value.estimated_delivery_min, quote.value.estimated_delivery_max) : null,
)
</script>

<template>
  <ul class="trust">
    <li class="trust__item trust__item--main">
      <span class="trust__icon" style="--hue: 150"><PhTruck :size="18" weight="duotone" /></span>
      <span class="trust__text">
        <template v-if="quote && quote.delivery_fee !== null">
          <strong>Livraison {{ quote.delivery_fee === 0 ? 'offerte' : formatGnf(quote.delivery_fee) }}</strong>
          <span>
            {{ deliveryWindow }}<template v-if="quote.distance_km !== null"> · à {{ quote.distance_km.toLocaleString('fr-FR') }} km de vous</template>
          </span>
        </template>
        <template v-else-if="quote">
          <strong>Livraison {{ quote.min_fee === 0 ? 'offerte' : `dès ${formatGnf(quote.min_fee)}` }}</strong>
          <span>
            {{ deliveryWindow }} ·
            <button type="button" class="trust__link" :disabled="locating" @click="locateMe">
              <PhCrosshair :size="13" weight="bold" />
              {{ locating ? 'Localisation…' : 'calculer pour ma position' }}
            </button>
          </span>
        </template>
        <template v-else>
          <strong>Livraison à domicile</strong>
          <span>Par zone et point de repère, sans adresse postale</span>
        </template>
      </span>
    </li>
    <li v-if="pickupOfferMin != null" class="trust__item trust__item--offer">
      <span class="trust__icon" style="--hue: 150"><PhGift :size="18" weight="fill" /></span>
      <span class="trust__text">
        <strong>Retrait offert par la boutique</strong>
        <span>
          Livraison gratuite en point de retrait<template v-if="pickupOfferMin > 0"> dès {{ formatGnf(pickupOfferMin) }} d'achat chez elle</template>, quelle que soit la distance
        </span>
      </span>
    </li>
    <li v-else class="trust__item">
      <span class="trust__icon" style="--hue: 215"><PhStorefront :size="18" weight="duotone" /></span>
      <span class="trust__text">
        <strong>Ou retrait en point de retrait</strong>
        <span>Choisissez le point le plus proche à la commande</span>
      </span>
    </li>
    <li class="trust__item">
      <span class="trust__icon" style="--hue: 35"><PhHandCoins :size="18" weight="duotone" /></span>
      <span class="trust__text">
        <strong>Paiement sécurisé en ligne</strong>
        <span>Mobile money, carte ou solde NdjouriBank</span>
      </span>
    </li>
    <li class="trust__item">
      <span class="trust__icon" style="--hue: 330"><PhArrowCounterClockwise :size="18" weight="duotone" /></span>
      <span class="trust__text">
        <strong>Annulation remboursée</strong>
        <span>Tant que le vendeur n'a pas commencé à préparer la commande</span>
      </span>
    </li>
  </ul>
</template>

<style scoped>
.trust {
  list-style: none;
  margin: 0;
  padding: 4px 0;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-md);
  background: var(--color-neutral-900);
}

.trust__item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 12px;
}

.trust__item + .trust__item {
  border-top: 1px solid var(--color-divider);
}

.trust__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  border-radius: 10px;
  background: hsl(var(--hue) 70% var(--tint-bg));
  color: hsl(var(--hue) 60% var(--tint-fg));
}

.trust__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  font-size: 12.5px;
  line-height: 1.35;
  color: var(--color-neutral-400);
}

.trust__text strong {
  font-size: 13.5px;
  color: var(--color-neutral-200);
}

.trust__item--main .trust__text strong {
  color: hsl(150 55% var(--tint-fg));
}

.trust__item--offer {
  background: hsl(150 70% var(--tint-bg));
}

.trust__item--offer .trust__text strong {
  color: hsl(150 55% var(--tint-fg));
}

.trust__link {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 0;
  border: 0;
  background: none;
  color: var(--color-primary-300);
  font-size: inherit;
  font-weight: 700;
  cursor: pointer;
}
</style>
