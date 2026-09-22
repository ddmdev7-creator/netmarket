<script setup lang="ts">
import { PhArrowLeft, PhChatCircle, PhImage } from '@phosphor-icons/vue'
import type { OrderRead } from '~/types/api'

definePageMeta({ middleware: 'auth', layout: 'blank' })

const route = useRoute()
const router = useRouter()
const { apiFetch } = useApi()
const toast = useToastStore()
const notifications = useNotificationStore()
const apiBase = useApiBase()

const orderId = route.params.id as string

const { data: order, error, refresh: refreshOrder } = await useAsyncData(`order-${orderId}`, () =>
  apiFetch<OrderRead>(`/orders/${orderId}`),
)

// Retour du portail Djomy (voir checkout.vue et payments/router.py) : le
// webhook a pu ne pas encore atteindre l'API à cet instant (délai réseau,
// ou en dev où Djomy ne peut pas nous joindre) — une resynchronisation
// explicite ici évite d'afficher "en attente" alors que le paiement a déjà
// réussi. Une seule fois : le paramètre est retiré de l'URL juste après.
if (route.query.djomy === 'return') {
  try {
    order.value = await apiFetch<OrderRead>(`/orders/${orderId}/payment/sync`, { method: 'POST' })
  } catch {
    // Le statut affiché reste celui du GET initial — pas bloquant.
  }
  router.replace({ query: {} })
}

// Une notification de changement de statut poussée en direct pendant que
// l'acheteur est déjà sur cette page ne doit pas rester lettre morte : sans
// ça, la page reste figée sur l'ancien statut tant qu'elle n'est pas
// rechargée manuellement — le côté "temps réel" ne serait visible que dans
// la cloche, pas sur le suivi de commande lui-même.
watch(
  () => notifications.items[0],
  (latest) => {
    if (latest?.type === 'order_status_changed' && latest.order_id === orderId) refreshOrder()
  },
)

const cancelling = ref(false)

const canCancel = computed(() => order.value?.status === 'pending')

const paymentLabels: Record<string, string> = { cash_on_delivery: 'Paiement à la livraison', online: 'Payé en ligne' }

async function cancelOrder() {
  if (!order.value) return
  cancelling.value = true
  try {
    order.value = await apiFetch<OrderRead>(`/orders/${orderId}/cancel`, { method: 'POST' })
    toast.success('Commande annulée.')
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'annuler cette commande."))
  } finally {
    cancelling.value = false
  }
}

function shortId(id: string) {
  return `#GN-${id.slice(0, 5).toUpperCase()}`
}
</script>

<template>
  <div v-if="error" class="pa-6">
    <CommonEmptyState message="Commande introuvable." />
  </div>
  <div v-else-if="order" class="app-shell" style="padding-bottom: 32px">
    <div class="d-flex align-center pa-2 ga-2">
      <v-btn icon variant="text" @click="router.back()">
        <PhArrowLeft :size="20" />
      </v-btn>
      <h1 class="text-h6">Commande {{ shortId(order.id) }}</h1>
      <LayoutHomeLink />
    </div>

    <div class="px-4">
      <div v-for="sub in order.sub_orders" :key="sub.id" class="mb-6">
        <div class="d-flex justify-space-between align-center mb-3">
          <span class="text-meta" style="font-weight: 600">{{ sub.shop_name }}</span>
          <StatusBadge :status="sub.status" />
        </div>
        <OrderTimeline :status="sub.status" :delivery-type="order.delivery_type" />
        <p
          v-if="sub.estimated_delivery_min && sub.estimated_delivery_max && !['delivered', 'cancelled'].includes(sub.status)"
          class="text-muted mt-2 mb-3 text-meta"
        >
          Livraison estimée :
          <strong>{{ formatDeliveryEstimate(sub.estimated_delivery_min, sub.estimated_delivery_max) }}</strong>
        </p>
        <div v-for="item in sub.items" :key="item.id" class="order-item-row mt-2">
          <NuxtLink :to="`/produits/${item.product_id}`" class="order-item-row__thumb">
            <img
              v-if="item.product_image"
              :src="resolveImageUrl(item.product_image, apiBase)"
              :alt="item.product_name"
              loading="lazy"
            />
            <PhImage v-else :size="18" weight="light" color="var(--color-neutral-500)" />
          </NuxtLink>
          <span class="order-item-row__label text-meta"
            >{{ item.product_name }}<span v-if="item.variant_label" class="text-muted"> ({{ item.variant_label }})</span> ×
            {{ item.quantity }}</span
          >
          <span class="amount">{{ formatGnf(item.unit_price * item.quantity) }}</span>
        </div>

        <div v-if="sub.delivery_fee > 0" class="d-flex justify-space-between text-meta text-muted mt-2">
          <span>Livraison</span>
          <span class="amount">{{ formatGnf(sub.delivery_fee) }}</span>
        </div>

        <div v-if="sub.delivery_token" class="qr-block mt-4">
          <OrderDeliveryQrCode :token="sub.delivery_token" />
          <p class="text-muted mt-2 mb-0 text-meta" style="max-width: 220px">
            Présentez ce code au livreur à la remise du colis — il confirme la livraison automatiquement.
          </p>
        </div>

        <v-divider class="mt-4" />
      </div>

      <h3 class="text-subtitle-2 text-muted mb-1">Livraison</h3>
      <OrderDeliveryDetails
        class="mb-4"
        :zone="order.delivery_zone"
        :address="order.delivery_address"
        :instructions="order.delivery_instructions"
        :delivery-type="order.delivery_type"
        :recipient-name="order.recipient_name"
        :recipient-phone="order.recipient_phone"
        :pickup-point-contacts="order.pickup_point_contacts"
        :note="order.delivery_type === 'pickup_point' ? 'Vous récupérerez cette commande vous-même à ce point de retrait.' : null"
      />

      <h3 class="text-subtitle-2 text-muted mb-1">Paiement</h3>
      <p class="mb-4 text-meta">{{ paymentLabels[order.payment_method] }}</p>

      <div class="d-flex justify-space-between text-lg">
        <span>Total</span>
        <span class="amount amount--total">{{ formatGnf(order.total) }}</span>
      </div>

      <v-btn v-if="canCancel" variant="outlined" color="error" block class="mt-6" :loading="cancelling" @click="cancelOrder">
        Annuler la commande
      </v-btn>

      <v-btn variant="text" block class="mt-3">
        <PhChatCircle :size="18" class="mr-1" />
        Contacter le support
      </v-btn>
    </div>
  </div>
</template>

<style scoped>
.order-item-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.order-item-row__thumb {
  width: 40px;
  height: 40px;
  flex: none;
  border-radius: var(--radius-sm);
  background: var(--color-neutral-800);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.order-item-row__thumb img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.order-item-row__label {
  flex: 1 1 auto;
  min-width: 0;
}

@media (min-width: 960px) {
  .order-item-row__thumb {
    width: 52px;
    height: 52px;
  }
}

.amount {
  font-family: var(--font-heading);
  font-weight: 600;
  color: var(--color-primary-300);
}

.amount--total {
  font-size: 17px;
  font-weight: 700;
}

.qr-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}
</style>
