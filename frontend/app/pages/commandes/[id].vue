<script setup lang="ts">
import { PhArrowLeft, PhChatCircle, PhCheckCircle, PhImage, PhStar, PhWallet } from '@phosphor-icons/vue'
import type { BuyerWalletRead, OrderItemRead, OrderRead, ReviewRead } from '~/types/api'

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


// Annulation : confirmée dans un dialogue qui, pour une commande déjà
// payée, dit où revient l'argent — et, pour un paiement en ligne, laisse
// choisir le solde NdjouriBank (immédiat) plutôt que le mobile money.
const cancelOpen = ref(false)
const refundTo = ref<'original' | 'wallet'>('wallet')
const walletEnabled = ref(false)
const isPaid = computed(() => order.value?.payment_status === 'paid')
const canChooseWallet = computed(() => isPaid.value && order.value?.payment_method === 'online' && walletEnabled.value)

async function openCancel() {
  cancelOpen.value = true
  if (isPaid.value && order.value?.payment_method === 'online') {
    try {
      walletEnabled.value = (await apiFetch<BuyerWalletRead>('/ndjouribank')).enabled
    } catch {
      walletEnabled.value = false
    }
    refundTo.value = walletEnabled.value ? 'wallet' : 'original'
  }
}

async function cancelOrder() {
  if (!order.value) return
  cancelling.value = true
  try {
    order.value = await apiFetch<OrderRead>(`/orders/${orderId}/cancel`, {
      method: 'POST',
      body: { refund_to: canChooseWallet.value ? refundTo.value : 'original' },
    })
    cancelOpen.value = false
    toast.success(
      order.value.wallet_refunded_amount
        ? `Commande annulée — ${formatGnf(order.value.wallet_refunded_amount)} recrédités sur ton solde NdjouriBank.`
        : 'Commande annulée.',
    )
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'annuler cette commande."))
  } finally {
    cancelling.value = false
  }
}

function shortId(id: string) {
  return `#GN-${id.slice(0, 5).toUpperCase()}`
}

// Un seul dialogue de notation partagé, ciblé sur le livreur ou le point de
// retrait selon le bouton cliqué — même motif que reportTargetId dans
// ProductReviewList.vue.
const ratingDialog = ref<{ title: string; endpoint: string } | null>(null)
const ratingOpen = computed({
  get: () => ratingDialog.value !== null,
  set: (v: boolean) => {
    if (!v) ratingDialog.value = null
  },
})

// Avis produit : un par produit reçu (même produit commandé deux fois = un
// seul avis, modifiable) — voir composables/useReviewableProducts.ts.
const reviewable = useReviewableProducts()
const reviewTarget = ref<OrderItemRead | null>(null)
const reviewInitialRating = ref(0)
const reviewOpen = computed({
  get: () => reviewTarget.value !== null,
  set: (v: boolean) => {
    if (!v) reviewTarget.value = null
  },
})
function rateProduct(item: OrderItemRead, rating = 0) {
  reviewInitialRating.value = rating
  reviewTarget.value = item
}
function onProductReviewed(review: ReviewRead) {
  reviewable.applyReview(review)
}

function rateCourier(courierId: string) {
  ratingDialog.value = { title: 'Noter le livreur', endpoint: `/couriers/${courierId}/reviews` }
}

function ratePickupPoint(pointId: string) {
  ratingDialog.value = { title: 'Noter le point de retrait', endpoint: `/pickup-points/${pointId}/reviews` }
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

    <div class="detail-card">
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

        <div v-if="sub.courier_id" class="courier-block mt-2 mb-2">
          <div class="d-flex align-center ga-2 flex-wrap">
            <span class="text-meta">Livreur : {{ sub.courier_name ?? 'Assigné' }}</span>
            <v-chip v-if="sub.courier_status === 'approved'" size="x-small" color="success" variant="tonal">
              <PhCheckCircle :size="12" weight="fill" class="mr-1" />
              Approuvé
            </v-chip>
          </div>
          <div v-if="sub.courier_review_count > 0" class="d-flex align-center ga-1 mt-1">
            <PhStar
              v-for="n in 5"
              :key="n"
              :size="13"
              :weight="n <= Math.round(sub.courier_average_rating ?? 0) ? 'fill' : 'regular'"
              color="var(--color-accent)"
            />
            <span class="text-muted text-fine">({{ sub.courier_review_count }})</span>
          </div>
          <button
            v-if="sub.status === 'delivered'"
            type="button"
            class="rate-link mt-1"
            @click="rateCourier(sub.courier_id)"
          >
            Noter le livreur
          </button>
        </div>

        <div v-for="item in sub.items" :key="item.id" class="mt-2">
        <div class="order-item-row">
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
        <div v-if="sub.status === 'delivered'" class="item-review">
          <template v-if="reviewable.byProduct.value.get(item.product_id)?.review">
            <span class="item-review__stars" :aria-label="`Votre note : ${reviewable.byProduct.value.get(item.product_id)!.review!.rating} sur 5`">
              <PhStar
                v-for="n in 5"
                :key="n"
                :size="14"
                :weight="n <= reviewable.byProduct.value.get(item.product_id)!.review!.rating ? 'fill' : 'regular'"
                color="var(--color-accent)"
              />
            </span>
            <span class="text-muted text-fine">Votre avis</span>
            <button type="button" class="rate-link" @click="rateProduct(item)">Modifier</button>
          </template>
          <template v-else>
            <span class="item-review__prompt">Notez ce produit :</span>
            <span class="item-review__stars item-review__stars--pick">
              <button
                v-for="n in 5"
                :key="n"
                type="button"
                class="item-review__star"
                :aria-label="`Donner ${n} étoile${n > 1 ? 's' : ''}`"
                @click="rateProduct(item, n)"
              >
                <PhStar :size="18" />
              </button>
            </span>
          </template>
        </div>
        </div>

        <div v-if="sub.delivery_fee > 0" class="d-flex justify-space-between text-meta text-muted mt-2">
          <span>Livraison</span>
          <span class="amount">{{ formatGnf(sub.delivery_fee) }}</span>
        </div>

        <div v-if="sub.handoff_ready" class="qr-block mt-4">
          <OrderDeliveryQrCode :sub-order-id="sub.id" />
          <p class="text-muted mt-2 mb-0 text-meta" style="max-width: 220px">
            Présente ce code {{ order.delivery_type === 'pickup_point' ? 'au gestionnaire du point de retrait' : 'au livreur' }}
            à la remise du colis : son scan confirme la livraison. Le code change toutes les minutes, ne l'envoie pas
            en photo.
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

      <div v-if="order.delivery_type === 'pickup_point' && order.pickup_point_id" class="mb-4">
        <div v-if="order.pickup_point_review_count > 0" class="d-flex align-center ga-1 mb-1">
          <PhStar
            v-for="n in 5"
            :key="n"
            :size="13"
            :weight="n <= Math.round(order.pickup_point_average_rating ?? 0) ? 'fill' : 'regular'"
            color="var(--color-accent)"
          />
          <span class="text-muted text-fine">({{ order.pickup_point_review_count }})</span>
        </div>
        <button
          v-if="order.sub_orders.some((so) => so.status === 'delivered')"
          type="button"
          class="rate-link"
          @click="ratePickupPoint(order.pickup_point_id)"
        >
          Noter le point de retrait
        </button>
      </div>

      <h3 class="text-subtitle-2 text-muted mb-1">Paiement</h3>
      <div class="mb-4">
        <p class="mb-0 text-meta">{{ PAYMENT_METHOD_LABELS[order.payment_method].paid }}</p>
        <p v-if="order.payment_status === 'refund_pending'" class="mb-0 text-meta refund-note">
          Remboursement en cours{{ order.refund_delay_hours != null ? ` — estimé sous ${order.refund_delay_hours}h` : '' }}.
        </p>
        <p v-if="order.wallet_refunded_amount > 0" class="mb-0 text-meta refund-note refund-note--done">
          <PhWallet :size="14" weight="fill" class="mr-1" />
          {{ formatGnf(order.wallet_refunded_amount) }} remboursés sur ton
          <NuxtLink to="/ndjouribank" class="refund-link">solde NdjouriBank</NuxtLink>.
        </p>
        <p v-else-if="order.payment_status === 'refunded'" class="mb-0 text-meta refund-note refund-note--done">
          Remboursement effectué.
        </p>
        <p v-else-if="order.payment_status === 'refund_failed'" class="mb-0 text-meta refund-note refund-note--failed">
          Le remboursement a échoué — contacte le support, ta commande est déjà annulée.
        </p>
      </div>

      <div class="d-flex justify-space-between text-lg">
        <span>Total</span>
        <span class="amount amount--total">{{ formatGnf(order.total) }}</span>
      </div>

      <v-btn v-if="canCancel" variant="outlined" color="error" block class="mt-6" :loading="cancelling" @click="openCancel">
        Annuler la commande
      </v-btn>

      <v-dialog v-model="cancelOpen" max-width="420">
        <v-card class="pa-5">
          <h2 class="cancel-title">Annuler cette commande ?</h2>
          <template v-if="canChooseWallet">
            <p class="text-meta mb-2">Où veux-tu récupérer tes {{ formatGnf(order.total) }} ?</p>
            <v-radio-group v-model="refundTo" hide-details class="mb-2">
              <v-radio value="wallet" color="primary">
                <template #label>
                  <span class="refund-choice">
                    <strong>Sur mon solde NdjouriBank</strong>
                    <span class="text-muted text-fine">Immédiat, utilisable pour tes prochains achats</span>
                  </span>
                </template>
              </v-radio>
              <v-radio value="original" color="primary">
                <template #label>
                  <span class="refund-choice">
                    <strong>Sur le compte qui a payé</strong>
                    <span class="text-muted text-fine">Versement mobile money, sous quelques jours</span>
                  </span>
                </template>
              </v-radio>
            </v-radio-group>
          </template>
          <p v-else-if="isPaid && order.payment_method === 'wallet'" class="text-meta mb-2">
            {{ formatGnf(order.total) }} seront recrédités tout de suite sur ton solde NdjouriBank.
          </p>
          <p v-else-if="isPaid" class="text-meta mb-2">
            Tu seras remboursé sur le compte qui a payé (mobile money), sous quelques jours.
          </p>
          <p v-else class="text-meta mb-2">Les vendeurs seront prévenus et les articles remis en stock.</p>
          <div class="d-flex justify-end ga-2 mt-3">
            <v-btn variant="text" @click="cancelOpen = false">Garder ma commande</v-btn>
            <v-btn color="error" :loading="cancelling" @click="cancelOrder">Annuler la commande</v-btn>
          </div>
        </v-card>
      </v-dialog>

      <v-btn variant="text" block class="mt-3">
        <PhChatCircle :size="18" class="mr-1" />
        Contacter le support
      </v-btn>
    </div>

    <ProductReviewForm
      v-if="reviewTarget"
      v-model="reviewOpen"
      :product-id="reviewTarget.product_id"
      :product-name="reviewTarget.product_name"
      :product-image="reviewTarget.product_image"
      :existing="reviewable.byProduct.value.get(reviewTarget.product_id)?.review ?? null"
      :initial-rating="reviewInitialRating"
      @submitted="onProductReviewed"
    />

    <CommonRatingDialog
      v-model="ratingOpen"
      :title="ratingDialog?.title ?? ''"
      :endpoint="ratingDialog?.endpoint ?? ''"
      @submitted="refreshOrder"
    />
  </div>
</template>

<style scoped>
.cancel-title {
  margin: 0 0 10px;
  font-family: var(--font-heading);
  font-size: 18px;
  font-weight: 800;
}

.refund-choice {
  display: flex;
  flex-direction: column;
  line-height: 1.35;
}

.refund-link {
  color: inherit;
  font-weight: 700;
}

.item-review {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 8px;
  margin: 6px 0 0 50px;
}

.item-review__prompt {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--color-neutral-300);
}

.item-review__stars {
  display: inline-flex;
  align-items: center;
  gap: 1px;
}

.item-review__star {
  display: flex;
  padding: 2px;
  border: none;
  background: none;
  color: var(--color-neutral-500);
  cursor: pointer;
  transition: color 0.12s ease, transform 0.12s ease;
}

/* Survol : l'étoile survolée et toutes celles à sa gauche s'allument. */
.item-review__stars--pick:hover .item-review__star {
  color: var(--color-accent);
}

.item-review__stars--pick .item-review__star:hover ~ .item-review__star {
  color: var(--color-neutral-500);
}

.item-review__star:hover {
  transform: scale(1.15);
}

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

.refund-note {
  color: var(--color-warning, #e0822e);
}

.refund-note--done {
  color: var(--color-success);
}

.refund-note--failed {
  color: var(--color-error);
}

.qr-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.courier-block {
  padding: 8px 10px;
  background: var(--color-neutral-800);
  border-radius: var(--radius-sm);
}

.rate-link {
  background: none;
  border: none;
  padding: 0;
  color: var(--color-primary-300);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
</style>
