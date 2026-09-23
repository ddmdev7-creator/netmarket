<script setup lang="ts">
/**
 * Demande de livraison reçue en direct par le livreur. N'affiche que ce qui
 * le concerne — son gain, les distances, où récupérer et où livrer — jamais
 * le prix des articles (détail : GET /orders/sub-orders/{id}/delivery-offer).
 */
import { PhClock, PhMapPin, PhMotorcycle, PhPackage, PhPhone, PhStorefront, PhUser } from '@phosphor-icons/vue'
import type { DeliveryOfferRead } from '~/types/api'

const notifications = useNotificationStore()
const { apiFetch } = useApi()
const toast = useToastStore()
const router = useRouter()

const request = computed(() => notifications.pendingDeliveryRequest)
const offer = ref<DeliveryOfferRead | null>(null)
const loadingOffer = ref(false)
const responding = ref(false)
const secondsLeft = ref(0)
let countdown: ReturnType<typeof setInterval> | undefined

watch(
  () => request.value?.sub_order_id,
  async (subOrderId) => {
    offer.value = null
    clearInterval(countdown)
    if (!subOrderId) return
    loadingOffer.value = true
    try {
      offer.value = await apiFetch<DeliveryOfferRead>(`/orders/sub-orders/${subOrderId}/delivery-offer`)
      secondsLeft.value = offer.value.expires_in_seconds
      countdown = setInterval(() => {
        secondsLeft.value = Math.max(secondsLeft.value - 1, 0)
      }, 1000)
    } catch {
      // Offre déjà expirée ou attribuée : le texte de la notification reste affiché.
    } finally {
      loadingOffer.value = false
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => clearInterval(countdown))

async function accept() {
  const subOrderId = request.value?.sub_order_id
  if (!subOrderId) return
  responding.value = true
  try {
    await apiFetch(`/orders/sub-orders/${subOrderId}/accept-delivery`, { method: 'POST' })
    toast.success('Livraison acceptée.')
    notifications.clearDeliveryRequest()
    // Espace livreur à jour tout de suite, même s'il est déjà affiché (un
    // simple router.push vers la page courante ne recharge rien).
    await refreshNuxtData('courier-deliveries')
    await router.push('/livreur')
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'accepter cette livraison — elle a peut-être déjà été prise."))
    notifications.clearDeliveryRequest()
  } finally {
    responding.value = false
  }
}

async function decline() {
  const subOrderId = request.value?.sub_order_id
  if (!subOrderId) {
    notifications.clearDeliveryRequest()
    return
  }
  responding.value = true
  try {
    await apiFetch(`/orders/sub-orders/${subOrderId}/decline-delivery`, { method: 'POST' })
  } catch {
    // Best-effort — même si le refus explicite échoue, le minuteur côté
    // serveur avancera de toute façon à l'expiration (voir _run_dispatch).
  } finally {
    responding.value = false
    notifications.clearDeliveryRequest()
  }
}

function km(value: number | null): string {
  return value == null ? '—' : `${value.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} km`
}
</script>

<template>
  <v-dialog :model-value="!!request" max-width="400" persistent>
    <v-card v-if="request" class="pa-4">
      <div class="d-flex align-center ga-2 mb-3">
        <PhMotorcycle :size="24" color="var(--color-primary)" />
        <span class="offer-title">Nouvelle demande de livraison</span>
        <span v-if="offer && secondsLeft > 0" class="offer-timer ml-auto"><PhClock :size="13" /> {{ secondsLeft }} s</span>
      </div>

      <v-skeleton-loader v-if="loadingOffer" type="list-item-three-line" />

      <template v-else-if="offer">
        <div class="offer-earning">
          <span class="offer-earning__label">Ton gain</span>
          <span class="offer-earning__value">{{ formatGnf(offer.courier_earning) }}</span>
        </div>

        <div class="offer-stats">
          <div><span class="offer-stats__value">{{ km(offer.distance_to_shop_km) }}</span><span>jusqu'à la boutique</span></div>
          <div><span class="offer-stats__value">{{ km(offer.delivery_distance_km) }}</span><span>boutique → livraison</span></div>
          <div><span class="offer-stats__value">{{ offer.item_count }}</span><span>article(s)</span></div>
        </div>

        <div class="offer-line">
          <PhStorefront :size="16" />
          <div>
            <div class="offer-line__label">Récupérer chez</div>
            <div class="offer-line__value">{{ offer.shop_name }}<span v-if="offer.shop_zone" class="text-muted"> · {{ offer.shop_zone }}</span></div>
          </div>
        </div>

        <div v-if="offer.delivery_type === 'pickup_point'" class="offer-line">
          <PhMapPin :size="16" />
          <div>
            <div class="offer-line__label">Déposer au point de retrait</div>
            <div class="offer-line__value">{{ offer.pickup_point_name ?? offer.destination_zone }}</div>
            <div v-if="offer.pickup_point_zone" class="text-muted text-fine">{{ offer.pickup_point_zone }}</div>
            <div v-for="c in offer.pickup_point_contacts" :key="c.phone" class="offer-contact">
              <PhPhone :size="12" /> {{ c.name ?? 'Gestionnaire' }} · <a :href="`tel:${c.phone}`">{{ c.phone }}</a>
            </div>
            <div v-if="!offer.pickup_point_contacts.length" class="text-muted text-fine">Aucun gestionnaire renseigné</div>
          </div>
        </div>

        <div v-else class="offer-line">
          <PhMapPin :size="16" />
          <div>
            <div class="offer-line__label">Livrer à domicile</div>
            <div class="offer-line__value">{{ offer.destination_zone }}</div>
            <div v-if="offer.recipient_name" class="offer-contact"><PhUser :size="12" /> {{ offer.recipient_name }}</div>
            <div v-if="offer.delivery_instructions" class="text-muted text-fine">« {{ offer.delivery_instructions }} »</div>
          </div>
        </div>

        <p class="text-muted text-fine mt-2 mb-0">
          <PhPackage :size="12" /> Les coordonnées complètes s'affichent dans ton espace une fois la livraison acceptée.
        </p>
      </template>

      <p v-else class="mb-0" style="font-size: 13.5px">{{ request.body }}</p>

      <div class="d-flex ga-2 mt-4">
        <v-btn variant="outlined" class="flex-grow-1" :disabled="responding" @click="decline">Refuser</v-btn>
        <v-btn color="primary" class="flex-grow-1" :loading="responding" @click="accept">Accepter</v-btn>
      </div>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.offer-title {
  font-family: var(--font-heading);
  font-size: 17px;
  font-weight: 800;
}

.offer-timer {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  font-weight: 700;
  color: var(--color-accent);
  font-variant-numeric: tabular-nums;
}

.offer-earning {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding: 12px 14px;
  border-radius: var(--radius-md);
  background: var(--color-primary-900, rgba(37, 99, 235, 0.08));
}

.offer-earning__label {
  font-size: 13px;
  color: var(--color-neutral-300);
}

.offer-earning__value {
  font-family: var(--font-heading);
  font-size: 22px;
  font-weight: 800;
  color: var(--color-primary);
  font-variant-numeric: tabular-nums;
}

.offer-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin: 10px 0 12px;
}

.offer-stats > div {
  display: flex;
  flex-direction: column;
  padding: 8px;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-sm);
  font-size: 11px;
  color: var(--color-neutral-400);
}

.offer-stats__value {
  font-size: 14px;
  font-weight: 800;
  color: var(--color-neutral-200);
  font-variant-numeric: tabular-nums;
}

.offer-line {
  display: flex;
  gap: 10px;
  padding: 8px 0;
  border-top: 1px solid var(--color-divider);
  color: var(--color-neutral-400);
}

.offer-line svg {
  flex: none;
  margin-top: 2px;
}

.offer-line__label {
  font-size: 11.5px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.offer-line__value {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--color-neutral-200);
}

.offer-contact {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12.5px;
  color: var(--color-neutral-300);
}

.offer-contact a {
  color: var(--color-primary);
}
</style>
