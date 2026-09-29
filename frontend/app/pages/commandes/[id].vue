<script setup lang="ts">
import {
  PhChatCircle,
  PhImage,
  PhMotorcycle,
  PhQrCode,
  PhSealCheck,
  PhStar,
  PhStorefront,
  PhWallet,
} from '@phosphor-icons/vue'
import type { BuyerWalletRead, OrderItemRead, OrderRead, ReviewRead } from '~/types/api'

definePageMeta({ middleware: 'auth', layout: 'focus' })

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

function formatDateTime(iso: string) {
  return new Date(iso).toLocaleDateString('fr-FR', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const itemsTotal = computed(() => order.value?.sub_orders.reduce((n, so) => n + so.amount, 0) ?? 0)
const deliveryTotal = computed(() => order.value?.sub_orders.reduce((n, so) => n + so.delivery_fee, 0) ?? 0)
const articleCount = computed(
  () => order.value?.sub_orders.reduce((n, so) => n + so.items.reduce((m, i) => m + i.quantity, 0), 0) ?? 0,
)

const PAYMENT_STATUS_META: Record<string, { label: string; tone: 'success' | 'warning' | 'error' | 'neutral' }> = {
  pending: { label: 'En attente de paiement', tone: 'warning' },
  paid: { label: 'Payée', tone: 'success' },
  failed: { label: 'Paiement échoué', tone: 'error' },
  cancelled: { label: 'Paiement annulé', tone: 'neutral' },
  refund_pending: { label: 'Remboursement en cours', tone: 'warning' },
  refunded: { label: 'Remboursée', tone: 'success' },
  refund_failed: { label: 'Remboursement échoué', tone: 'error' },
}
const paymentMeta = computed(() => {
  const status = order.value?.payment_status
  if (!status) return order.value?.payment_method === 'cash_on_delivery' ? { label: 'À régler à la livraison', tone: 'neutral' as const } : null
  return PAYMENT_STATUS_META[status] ?? null
})

// Bandeau d'en-tête : ce qui compte le plus pour l'acheteur, maintenant.
const headline = computed(() => {
  const o = order.value
  if (!o) return null
  const subs = o.sub_orders
  if (subs.some((so) => so.handoff_ready)) {
    return o.delivery_type === 'pickup_point'
      ? { text: 'Votre colis vous attend au point de retrait : présentez votre QR code.', tone: 'warning' }
      : { text: 'Votre livreur arrive : gardez votre QR code prêt pour la remise.', tone: 'info' }
  }
  if (subs.some((so) => so.status === 'shipped')) return { text: 'Un colis est en route vers vous.', tone: 'info' }
  if (o.status === 'delivered') return { text: 'Commande livrée. Merci pour votre confiance !', tone: 'success' }
  if (o.status === 'cancelled') return { text: 'Cette commande a été annulée.', tone: 'error' }
  return { text: 'Votre commande est en cours de préparation.', tone: 'primary' }
})

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
  <div v-else-if="order" class="od">
    <!-- En-tête -->
    <header class="od-head">
      <div class="od-head__main">
        <div class="od-head__row">
          <h1 class="od-head__title">Commande <OrderNumber :id="order.id" size="lg" /></h1>
          <StatusBadge :status="order.status" />
        </div>
        <p class="od-head__meta">
          Passée le {{ formatDateTime(order.created_at) }} · {{ articleCount }} article{{ articleCount > 1 ? 's' : '' }}
          · {{ order.sub_orders.length }} colis
        </p>
      </div>
      <div class="od-head__total">
        <span>Total</span>
        <strong>{{ formatGnf(order.total) }}</strong>
      </div>
    </header>

    <div v-if="headline" class="od-alert" :class="`od-alert--${headline.tone}`">{{ headline.text }}</div>

    <div class="od-layout">
      <!-- Colis -->
      <div class="od-main">
        <section v-for="(sub, index) in order.sub_orders" :key="sub.id" class="od-card parcel">
          <header class="parcel__head">
            <span class="parcel__shop">
              <span class="parcel__num">Colis {{ index + 1 }}/{{ order.sub_orders.length }}</span>
              <strong><PhStorefront :size="16" /> {{ sub.shop_name }}</strong>
            </span>
            <StatusBadge :status="sub.status" />
          </header>

          <div class="parcel__grid">
            <div class="parcel__track">
              <OrderTracker
                :status="sub.status"
                :delivery-type="order.delivery_type"
                :events="sub.status_events ?? []"
                :estimated-min="sub.estimated_delivery_min"
                :estimated-max="sub.estimated_delivery_max"
              />
              <OrderLiveTrackingMap v-if="sub.status === 'shipped' && sub.courier_id" :sub-order-id="sub.id" class="mt-3" />
            </div>

            <aside v-if="sub.handoff_ready" class="parcel__qr">
              <div class="parcel__qr-title">
                <PhQrCode :size="16" weight="bold" /> Code de remise
              </div>
              <OrderDeliveryQrCode :sub-order-id="sub.id" />
              <p>
                Présentez-le {{ order.delivery_type === 'pickup_point' ? 'au gestionnaire du point de retrait' : 'au livreur' }} :
                son scan confirme la remise. Il change chaque minute, ne l'envoyez pas en photo.
              </p>
            </aside>
          </div>

          <div v-if="sub.courier_id" class="courier">
            <span class="courier__avatar"><PhMotorcycle :size="18" weight="duotone" /></span>
            <span class="courier__body">
              <span class="courier__name">
                {{ sub.courier_name ?? 'Livreur assigné' }}
                <PhSealCheck v-if="sub.courier_status === 'approved'" :size="15" weight="fill" class="courier__seal" aria-label="Livreur vérifié" />
              </span>
              <span v-if="sub.courier_review_count > 0" class="courier__rating">
                <PhStar :size="12" weight="fill" /> {{ (sub.courier_average_rating ?? 0).toFixed(1).replace('.', ',') }}
                ({{ sub.courier_review_count }} avis)
              </span>
              <span v-else class="courier__rating">Livreur</span>
            </span>
            <button v-if="sub.status === 'delivered'" type="button" class="rate-link" @click="rateCourier(sub.courier_id)">
              Noter le livreur
            </button>
          </div>

          <ul class="items">
            <li v-for="item in sub.items" :key="item.id" class="item">
              <div class="order-item-row">
                <NuxtLink :to="`/produits/${item.product_id}`" class="order-item-row__thumb">
                  <img
                    v-if="item.product_image"
                    :src="resolveImageUrl(item.product_image, apiBase, 160)"
                    :alt="item.product_name"
                    loading="lazy"
                  />
                  <PhImage v-else :size="18" weight="light" color="var(--color-neutral-500)" />
                </NuxtLink>
                <span class="order-item-row__label">
                  <NuxtLink :to="`/produits/${item.product_id}`" class="item__name">{{ item.product_name }}</NuxtLink>
                  <span class="item__meta">
                    <template v-if="item.variant_label">{{ item.variant_label }} · </template>
                    {{ item.quantity }} × {{ formatGnf(item.unit_price) }}
                  </span>
                </span>
                <span class="item__price">{{ formatGnf(item.unit_price * item.quantity) }}</span>
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
            </li>
          </ul>

          <footer class="parcel__foot">
            <span>Livraison</span>
            <span v-if="sub.vendor_delivery_fee" class="parcel__offered">Retrait offert par {{ sub.shop_name }}</span>
            <span v-else>{{ sub.delivery_fee > 0 ? formatGnf(sub.delivery_fee) : 'Offerte' }}</span>
          </footer>
        </section>
      </div>

      <!-- Récapitulatif -->
      <aside class="od-aside">
        <section class="od-card">
          <h2 class="od-card__title">Récapitulatif</h2>
          <div class="sum-line"><span>Articles ({{ articleCount }})</span><span>{{ formatGnf(itemsTotal) }}</span></div>
          <div class="sum-line"><span>Livraison</span><span>{{ deliveryTotal ? formatGnf(deliveryTotal) : 'Offerte' }}</span></div>
          <div class="sum-line sum-line--total"><span>Total</span><span>{{ formatGnf(order.total) }}</span></div>

          <div class="pay">
            <span class="pay__icon"><PhWallet :size="18" weight="duotone" /></span>
            <span class="pay__body">
              <strong>{{ PAYMENT_METHOD_LABELS[order.payment_method].short }}</strong>
              <span v-if="paymentMeta" class="pay__status" :class="`pay__status--${paymentMeta.tone}`">{{ paymentMeta.label }}</span>
            </span>
          </div>
          <p v-if="order.payment_status === 'refund_pending'" class="refund-note">
            Remboursement en cours{{ order.refund_delay_hours != null ? ` — estimé sous ${order.refund_delay_hours} h` : '' }}.
          </p>
          <p v-if="order.wallet_refunded_amount > 0" class="refund-note refund-note--done">
            {{ formatGnf(order.wallet_refunded_amount) }} remboursés sur votre
            <NuxtLink to="/ndjouribank" class="refund-link">solde NdjouriBank</NuxtLink>.
          </p>
          <p v-else-if="order.payment_status === 'refunded'" class="refund-note refund-note--done">Remboursement effectué.</p>
          <p v-else-if="order.payment_status === 'refund_failed'" class="refund-note refund-note--failed">
            Le remboursement a échoué — contactez le support, votre commande est déjà annulée.
          </p>
        </section>

        <section class="od-card">
          <h2 class="od-card__title">
            {{ order.delivery_type === 'pickup_point' ? 'Point de retrait' : 'Adresse de livraison' }}
          </h2>
          <OrderDeliveryDetails
            :zone="order.delivery_zone"
            :address="order.delivery_address"
            :instructions="order.delivery_instructions"
            :delivery-type="order.delivery_type"
            :recipient-name="order.recipient_name"
            :recipient-phone="order.recipient_phone"
            :pickup-point-contacts="order.pickup_point_contacts"
            :note="order.delivery_type === 'pickup_point' ? 'Vous récupérerez cette commande vous-même à ce point de retrait.' : null"
          />
          <div v-if="order.delivery_type === 'pickup_point' && order.pickup_point_id" class="mt-2">
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
        </section>

        <section class="od-card od-help">
          <h2 class="od-card__title">Besoin d'aide ?</h2>
          <v-btn v-if="canCancel" variant="outlined" color="error" block :loading="cancelling" @click="openCancel">
            Annuler la commande
          </v-btn>
          <p v-if="canCancel" class="od-help__hint">Possible tant que les vendeurs n'ont pas confirmé.</p>
          <v-btn variant="tonal" block class="mt-2">
            <PhChatCircle :size="18" class="mr-1" />
            Contacter le support
          </v-btn>
        </section>
      </aside>
    </div>

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
.parcel__offered {
  color: hsl(150 55% var(--tint-fg));
  font-weight: 700;
}

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
  margin: 6px 0 0 62px;
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



.rate-link {
  background: none;
  border: none;
  padding: 0;
  color: var(--color-primary-300);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

/* --- Mise en page ----------------------------------------------------------- */
.od {
  max-width: 1600px;
  margin: 0 auto;
  padding: 16px 12px 40px;
}

@media (min-width: 960px) {
  .od {
    padding: 24px 32px 48px;
  }
}

.od-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 12px;
}

.od-head__row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.od-head__title {
  margin: 0;
  font-family: var(--font-heading);
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.02em;
}

@media (min-width: 960px) {
  .od-head__title {
    font-size: 26px;
  }
}

.od-head__meta {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--color-neutral-400);
}

.od-head__meta::first-letter {
  text-transform: uppercase;
}

.od-head__total {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  font-size: 12px;
  color: var(--color-neutral-400);
}

@media (max-width: 600px) {
  .od-head__total {
    flex-direction: row;
    align-items: baseline;
    gap: 8px;
  }
}

.od-head__total strong {
  font-family: var(--font-heading);
  font-size: 22px;
  font-weight: 800;
  color: var(--color-neutral-200);
}

.od-alert {
  margin-bottom: 16px;
  padding: 12px 14px;
  border-radius: var(--radius-md);
  font-size: 13.5px;
  font-weight: 600;
  border-left: 4px solid currentColor;
}

.od-alert--primary {
  background: hsl(220 80% var(--tint-bg-soft));
  color: hsl(220 70% var(--tint-fg));
}

.od-alert--info {
  background: hsl(200 80% var(--tint-bg-soft));
  color: hsl(200 70% var(--tint-fg));
}

.od-alert--warning {
  background: hsl(38 90% var(--tint-bg-soft));
  color: hsl(30 75% var(--tint-fg));
}

.od-alert--success {
  background: hsl(150 70% var(--tint-bg-soft));
  color: hsl(150 55% var(--tint-fg));
}

.od-alert--error {
  background: hsl(355 80% var(--tint-bg-soft));
  color: hsl(355 65% var(--tint-fg));
}

.od-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 16px;
}

@media (min-width: 1024px) {
  .od-layout {
    grid-template-columns: minmax(0, 1fr) 360px;
    gap: 24px;
    align-items: start;
  }

  .od-aside {
    position: sticky;
    top: 80px;
  }
}

.od-main,
.od-aside {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

/* Tablette : récapitulatif et adresse côte à côte sous les colis. */
@media (min-width: 720px) and (max-width: 1023px) {
  .od-aside {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    align-items: start;
  }

  .od-help {
    grid-column: 1 / -1;
  }
}

.od-card {
  padding: 16px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-divider);
  background: var(--color-neutral-900);
  box-shadow: var(--shadow-sm);
}

@media (min-width: 960px) {
  .od-card {
    padding: 20px;
  }
}

.od-card__title {
  margin: 0 0 12px;
  font-family: var(--font-heading);
  font-size: 15px;
  font-weight: 800;
}

/* --- Colis ------------------------------------------------------------------ */
.parcel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 14px;
}

.parcel__shop {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.parcel__num {
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--color-neutral-500);
}

.parcel__shop strong {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 15px;
}

.parcel__grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 16px;
}

@media (min-width: 720px) {
  .parcel__grid:has(.parcel__qr) {
    grid-template-columns: minmax(0, 1fr) 240px;
    align-items: start;
  }
}

.parcel__qr {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 14px;
  border-radius: var(--radius-md);
  background: hsl(220 80% var(--tint-bg-soft));
  border: 1px dashed hsl(220 70% 55% / 0.4);
  text-align: center;
}

.parcel__qr-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 800;
  color: var(--color-primary-300);
}

.parcel__qr p {
  margin: 0;
  font-size: 12px;
  color: var(--color-neutral-400);
}

.courier {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  background: var(--color-neutral-800);
}

.courier__avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  border-radius: 50%;
  background: hsl(25 90% var(--tint-bg));
  color: hsl(25 75% var(--tint-fg));
}

.courier__body {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.courier__name {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13.5px;
  font-weight: 700;
}

.courier__seal {
  color: var(--color-primary);
}

.courier__rating {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  color: var(--color-neutral-400);
}

.courier__rating svg {
  color: var(--color-accent);
}

.items {
  list-style: none;
  margin: 14px 0 0;
  padding: 0;
}

.item {
  padding: 10px 0;
  border-top: 1px solid var(--color-divider);
}

.item__name {
  display: block;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--color-neutral-200);
  text-decoration: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item__name:hover {
  color: var(--color-primary-300);
}

.item__meta {
  display: block;
  font-size: 12px;
  color: var(--color-neutral-400);
}

.item__price {
  flex-shrink: 0;
  font-weight: 700;
  font-size: 13.5px;
}

.parcel__foot {
  display: flex;
  justify-content: space-between;
  padding-top: 10px;
  border-top: 1px solid var(--color-divider);
  font-size: 13px;
  color: var(--color-neutral-400);
}

/* --- Récapitulatif ------------------------------------------------------------ */
.sum-line {
  display: flex;
  justify-content: space-between;
  padding: 4px 0;
  font-size: 13.5px;
  color: var(--color-neutral-400);
}

.sum-line--total {
  margin-top: 6px;
  padding-top: 10px;
  border-top: 1px solid var(--color-divider);
  font-family: var(--font-heading);
  font-size: 18px;
  font-weight: 800;
  color: var(--color-neutral-200);
}

.pay {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  background: var(--color-neutral-800);
}

.pay__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: hsl(260 70% var(--tint-bg));
  color: hsl(260 60% var(--tint-fg));
}

.pay__body {
  display: flex;
  flex-direction: column;
  font-size: 13px;
}

.pay__status {
  font-size: 12px;
  font-weight: 700;
}

.pay__status--success {
  color: var(--color-success);
}

.pay__status--warning {
  color: hsl(30 75% var(--tint-fg));
}

.pay__status--error {
  color: var(--color-error);
}

.pay__status--neutral {
  color: var(--color-neutral-400);
}

.refund-note {
  margin: 10px 0 0;
  font-size: 12.5px;
}

.od-help__hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--color-neutral-400);
}
</style>
