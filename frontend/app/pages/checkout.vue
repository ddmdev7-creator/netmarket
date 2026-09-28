<script setup lang="ts">
import {
  PhArrowLeft,
  PhCheck,
  PhDeviceMobile,
  PhHouse,
  PhImage,
  PhMoney,
  PhPencilSimple,
  PhPlus,
  PhShieldCheck,
  PhStar,
  PhStorefront,
  PhWallet,
} from '@phosphor-icons/vue'
import type { AddressFormValues } from '~/components/address/AddressForm.vue'
import type { AddressRead, BuyerWalletRead, DeliveryQuoteRead, OrderRead, PaymentMethod } from '~/types/api'

definePageMeta({ middleware: 'auth', layout: 'blank' })

const cartStore = useCartStore()
const auth = useAuthStore()
const router = useRouter()
const { apiFetch } = useApi()
const toast = useToastStore()
const apiBase = useApiBase()

await useAsyncData('checkout-cart', () => cartStore.fetchCart())

// Un aller-retour navigateur ("précédent") après confirmation d'une commande
// remonte sur cette page avec un panier déjà vidé côté serveur — sans ce
// garde-fou, l'acheteur se retrouverait sur un écran de paiement vide qu'il
// pourrait même tenter de soumettre à nouveau. Vérifié une seule fois ici
// (pas un watcher) : l'écran de succès affiché juste après confirmOrder
// tourne sur cette même page avec le panier déjà réinitialisé.
if ((cartStore.cart?.vendors.length ?? 0) === 0) {
  await navigateTo('/panier')
}

const { data: addresses } = await useAsyncData('checkout-addresses', () => apiFetch<AddressRead[]>('/addresses'), {
  default: () => [],
})

// "new" est une valeur de sélection à part entière (comme les adresses
// enregistrées) plutôt qu'un simple booléen.
const NEW_ADDRESS = 'new' as const
// Adresse par défaut présélectionnée (sinon la première enregistrée).
const selectedId = ref<string>(
  (addresses.value.find((a) => a.is_default) ?? addresses.value[0])?.id ?? NEW_ADDRESS,
)

const newAddressForm = ref<AddressFormValues>({
  label: '',
  delivery_type: 'home_delivery',
  zone: '',
  pickup_point_id: null,
  recipient_name: '',
  recipient_phone: '',
  instructions: '',
  latitude: null,
  longitude: null,
  is_default: false,
})
const saveNewAddress = ref(true)

const submitting = ref(false)
const confirmedOrder = ref<OrderRead | null>(null)

// Paiement à la livraison par défaut, sauf si l'acheteur a choisi autre
// chose à sa dernière commande (mémorisé sur l'appareil).
const LAST_PAYMENT_KEY = 'nm-last-payment'
const paymentMethod = ref<PaymentMethod>('cash_on_delivery')
const payerPhone = ref(auth.user?.phone ?? '')

// Solde NdjouriBank : option proposée si le service est ouvert ou s'il reste
// un solde à dépenser. Chargé sans bloquer la page.
const buyerWallet = ref<BuyerWalletRead | null>(null)
onMounted(async () => {
  try {
    const last = localStorage.getItem(LAST_PAYMENT_KEY)
    if (last === 'online' || last === 'cash_on_delivery') paymentMethod.value = last
  } catch {
    // Stockage indisponible : on garde le défaut.
  }
  try {
    buyerWallet.value = await apiFetch<BuyerWalletRead>('/ndjouribank')
  } catch {
    buyerWallet.value = null
  }
})
const showWalletOption = computed(
  () => !!buyerWallet.value && (buyerWallet.value.enabled || buyerWallet.value.balance > 0),
)

const cart = computed(() => cartStore.cart)

/**
 * Frais de livraison : devis calculé côté serveur (même calcul que le
 * checkout, par colis vendeur) dès que la destination est connue. Tant que
 * le devis n'est pas là (ou en échec), le récapitulatif retombe sur le total
 * panier sans frais plutôt que d'afficher un montant inventé.
 */
const destination = computed(() => {
  const source =
    selectedId.value === NEW_ADDRESS
      ? newAddressForm.value
      : addresses.value.find((a) => a.id === selectedId.value)
  if (!source) return null
  if (source.delivery_type === 'pickup_point' && !source.pickup_point_id) return null
  return {
    delivery_type: source.delivery_type,
    pickup_point_id: source.pickup_point_id ?? undefined,
    latitude: source.latitude ?? undefined,
    longitude: source.longitude ?? undefined,
  }
})

const quote = ref<DeliveryQuoteRead | null>(null)
let quoteRequestId = 0
watch(
  destination,
  async (value) => {
    const requestId = ++quoteRequestId
    quote.value = null
    if (!value) return
    try {
      const result = await apiFetch<DeliveryQuoteRead>('/orders/delivery-quote', { method: 'POST', body: value })
      // Ignore une réponse périmée : l'acheteur a changé d'adresse entre-temps.
      if (requestId === quoteRequestId) quote.value = result
    } catch {
      // Le checkout recalcule de toute façon les frais côté serveur.
    }
  },
  { immediate: true, deep: true },
)

const orderTotal = computed(() => quote.value?.total ?? cart.value?.total ?? 0)
const walletShortfall = computed(() =>
  buyerWallet.value ? Math.max(orderTotal.value - buyerWallet.value.balance, 0) : 0,
)
// Solde devenu insuffisant (frais de livraison ajoutés au devis) : on ne
// laisse pas l'option sélectionnée.
watch(walletShortfall, (shortfall) => {
  if (shortfall > 0 && paymentMethod.value === 'wallet') paymentMethod.value = 'cash_on_delivery'
})

function deliveryFeeFor(vendorId: string): number | null {
  return quote.value?.vendors.find((v) => v.vendor_id === vendorId)?.delivery_fee ?? null
}

function deliveryEstimateFor(vendorId: string): string | null {
  const match = quote.value?.vendors.find((v) => v.vendor_id === vendorId)
  return match ? formatDeliveryEstimate(match.estimated_delivery_min, match.estimated_delivery_max) : null
}

/**
 * zoneText() est la source unique de la zone affichée, réutilisée à la fois
 * pour le texte combiné (delivery_address, gardé pour les anciennes
 * commandes / fallback simple) et pour le champ structuré delivery_zone
 * envoyé séparément — le vendeur n'a pas de carte pour l'instant, donc si
 * l'acheteur n'a laissé qu'une position GPS sans description, on lui donne
 * au moins les coordonnées en clair plutôt qu'un texte vide.
 */
function zoneText(fields: { zone: string; latitude?: number | null; longitude?: number | null }): string {
  return (
    fields.zone.trim() ||
    (fields.latitude != null && fields.longitude != null
      ? `Position GPS : ${fields.latitude.toFixed(4)}, ${fields.longitude.toFixed(4)}`
      : '')
  )
}

/**
 * Texte combiné conservé pour affichage simple/fallback (ex: commandes
 * passées avant l'ajout des champs structurés delivery_zone/instructions/
 * recipient_*, voir OrderDeliveryDetails.vue). Pour un point de retrait,
 * l'adresse (zone) est déjà celle du point lui-même (voir
 * AddressForm.selectPickupPoint) — on n'y ajoute donc jamais de destinataire
 * personnel, seulement une mention rappelant que c'est l'acheteur final qui
 * viendra chercher son colis sur place.
 */
function buildAddressText(
  fields: {
    zone: string
    recipient_name?: string | null
    recipient_phone?: string | null
    instructions?: string | null
    latitude?: number | null
    longitude?: number | null
  },
  deliveryType: string,
): string {
  const parts = [zoneText(fields)]
  if (deliveryType === 'pickup_point') {
    parts.push('Retrait en personne par le client')
  } else {
    if (fields.recipient_name?.trim()) parts.push(`Destinataire: ${fields.recipient_name.trim()}`)
    if (fields.recipient_phone?.trim()) parts.push(`Tél: ${fields.recipient_phone.trim()}`)
  }
  if (fields.instructions?.trim()) parts.push(`Instructions: ${fields.instructions.trim()}`)
  return parts.filter(Boolean).join(' — ')
}

// --- Étapes -------------------------------------------------------------------

type Step = 1 | 2 | 3
const STEPS: { n: Step; label: string }[] = [
  { n: 1, label: 'Livraison' },
  { n: 2, label: 'Paiement' },
  { n: 3, label: 'Vérification' },
]
const step = ref<Step>(1)

function addressStepError(): string | null {
  if (selectedId.value === NEW_ADDRESS) return validateAddressForm(newAddressForm.value)
  const selected = addresses.value.find((a) => a.id === selectedId.value)
  if (!selected) return 'Choisis une adresse de livraison.'
  if (selected.delivery_type === 'pickup_point' && !selected.pickup_point_id) {
    return 'Cette adresse n’a pas de point de retrait valide — modifie-la ou choisis-en une autre.'
  }
  return null
}

function paymentStepError(): string | null {
  if (paymentMethod.value === 'wallet' && (!quote.value || walletShortfall.value > 0)) {
    return 'Solde NdjouriBank insuffisant pour cette commande.'
  }
  if (paymentMethod.value === 'online' && !payerPhone.value.trim()) {
    return 'Indique le numéro qui va payer (mobile money ou carte).'
  }
  return null
}

/** Revenir en arrière est toujours possible ; avancer valide chaque étape franchie. */
function goTo(target: Step) {
  if (target > step.value) {
    const checks: (() => string | null)[] = [addressStepError, paymentStepError]
    for (let s = step.value; s < target; s++) {
      const error = checks[s - 1]?.()
      if (error) {
        toast.error(error)
        step.value = s as Step
        return
      }
    }
  }
  step.value = target
}

function next() {
  if (step.value === 3) confirmOrder()
  else goTo((step.value + 1) as Step)
}

function back() {
  if (step.value > 1) step.value = (step.value - 1) as Step
  else router.back()
}

watch(step, () => {
  if (import.meta.client) window.scrollTo({ top: 0, behavior: 'smooth' })
})

const primaryLabel = computed(() => {
  if (step.value === 1) return 'Continuer vers le paiement'
  if (step.value === 2) return 'Vérifier ma commande'
  return paymentMethod.value === 'online'
    ? `Payer ${formatGnf(orderTotal.value)}`
    : `Confirmer · ${formatGnf(orderTotal.value)}`
})

// --- Récapitulatifs -----------------------------------------------------------

const itemCount = computed(() =>
  (cart.value?.vendors ?? []).reduce((n, g) => n + g.items.reduce((m, i) => m + i.quantity, 0), 0),
)

const addressSummary = computed(() => {
  if (selectedId.value === NEW_ADDRESS) {
    const f = newAddressForm.value
    return {
      label: f.label.trim() || 'Nouvelle adresse',
      zone: zoneText(f),
      pickup: f.delivery_type === 'pickup_point',
      recipient: f.recipient_name.trim() || null,
    }
  }
  const a = addresses.value.find((x) => x.id === selectedId.value)
  if (!a) return null
  return { label: a.label, zone: zoneText(a) || 'Zone non précisée', pickup: a.delivery_type === 'pickup_point', recipient: a.recipient_name }
})

const PAYMENT_OPTIONS: { value: PaymentMethod; title: string; text: string; icon: object; hue: number }[] = [
  {
    value: 'cash_on_delivery',
    title: 'Paiement à la livraison',
    text: 'En espèces, à la remise du colis',
    icon: PhMoney,
    hue: 150,
  },
  {
    value: 'online',
    title: 'Mobile money ou carte',
    text: 'Orange Money, MTN MoMo, carte bancaire…',
    icon: PhDeviceMobile,
    hue: 30,
  },
]

const paymentSummary = computed(() => {
  if (paymentMethod.value === 'wallet') return { title: 'Solde NdjouriBank', text: 'Débité à la confirmation' }
  const option = PAYMENT_OPTIONS.find((o) => o.value === paymentMethod.value)!
  return {
    title: option.title,
    text: paymentMethod.value === 'online' ? `Numéro qui paie : ${payerPhone.value.trim()}` : option.text,
  }
})

function rememberPayment() {
  try {
    if (paymentMethod.value !== 'wallet') localStorage.setItem(LAST_PAYMENT_KEY, paymentMethod.value)
  } catch {
    // Sans stockage, le choix n'est simplement pas mémorisé.
  }
}

async function confirmOrder() {
  const usingNew = selectedId.value === NEW_ADDRESS
  const error = addressStepError() ?? paymentStepError()
  if (error) {
    toast.error(error)
    goTo(addressStepError() ? 1 : 2)
    return
  }

  submitting.value = true
  try {
    let deliveryAddress: string
    let deliveryType: string
    let pickupPointId: string | null
    let latitude: number | null
    let longitude: number | null
    let deliveryZone: string
    let deliveryInstructions: string | null
    let recipientName: string | null
    let recipientPhone: string | null

    if (usingNew) {
      deliveryAddress = buildAddressText(newAddressForm.value, newAddressForm.value.delivery_type)
      deliveryType = newAddressForm.value.delivery_type
      pickupPointId = newAddressForm.value.pickup_point_id
      latitude = newAddressForm.value.latitude
      longitude = newAddressForm.value.longitude
      deliveryZone = zoneText(newAddressForm.value)
      deliveryInstructions = newAddressForm.value.instructions.trim() || null
      recipientName = newAddressForm.value.recipient_name.trim() || null
      recipientPhone = newAddressForm.value.recipient_phone.trim() || null
      if (saveNewAddress.value && newAddressForm.value.label.trim()) {
        await apiFetch('/addresses', {
          method: 'POST',
          body: {
            label: newAddressForm.value.label.trim(),
            delivery_type: newAddressForm.value.delivery_type,
            zone: newAddressForm.value.zone.trim(),
            pickup_point_id: newAddressForm.value.pickup_point_id ?? undefined,
            recipient_name: newAddressForm.value.recipient_name.trim() || undefined,
            recipient_phone: newAddressForm.value.recipient_phone.trim() || undefined,
            instructions: newAddressForm.value.instructions.trim() || undefined,
            latitude: newAddressForm.value.latitude,
            longitude: newAddressForm.value.longitude,
            is_default: newAddressForm.value.is_default,
          },
        })
      }
    } else {
      const selected = addresses.value.find((a) => a.id === selectedId.value)!
      deliveryAddress = buildAddressText(selected, selected.delivery_type)
      deliveryType = selected.delivery_type
      pickupPointId = selected.pickup_point_id
      latitude = selected.latitude
      longitude = selected.longitude
      deliveryZone = zoneText(selected)
      deliveryInstructions = selected.instructions
      recipientName = selected.recipient_name
      recipientPhone = selected.recipient_phone
    }

    const order = await apiFetch<OrderRead>('/orders/checkout', {
      method: 'POST',
      body: {
        delivery_address: deliveryAddress,
        delivery_type: deliveryType,
        pickup_point_id: pickupPointId ?? undefined,
        latitude: latitude ?? undefined,
        longitude: longitude ?? undefined,
        delivery_zone: deliveryZone || undefined,
        delivery_instructions: deliveryInstructions ?? undefined,
        recipient_name: recipientName ?? undefined,
        recipient_phone: recipientPhone ?? undefined,
        payment_method: paymentMethod.value,
        payer_phone: paymentMethod.value === 'online' ? payerPhone.value.trim() : undefined,
      },
    })
    cartStore.reset()
    rememberPayment()

    // Paiement en ligne : le panier est vidé et la commande existe déjà
    // (statut de paiement "pending"), mais l'argent n'a pas encore bougé —
    // direction le portail Djomy plutôt que la modale "commande confirmée",
    // qui suppose à tort que tout est réglé.
    if (order.payment_redirect_url) {
      window.location.href = order.payment_redirect_url
      return
    }
    confirmedOrder.value = order
  } catch (error) {
    toast.error(apiErrorMessage(error, 'Impossible de finaliser la commande.'))
  } finally {
    submitting.value = false
  }
}

function goToOrder() {
  if (confirmedOrder.value) router.push(`/commandes/${confirmedOrder.value.id}`)
}

function continueShopping() {
  router.push('/')
}
</script>

<template>
  <!-- Écran de succès : remplace toute la page une fois la commande passée. -->
  <div v-if="confirmedOrder" class="app-shell success">
    <div class="success__burst">
      <span class="success__ring" />
      <span class="success__check"><PhCheck :size="40" weight="bold" /></span>
    </div>
    <h1 class="success__title">Merci, c'est commandé !</h1>
    <p class="success__sub">
      Commande <strong>#{{ confirmedOrder.id.slice(0, 8).toUpperCase() }}</strong> ·
      {{ PAYMENT_METHOD_LABELS[confirmedOrder.payment_method].paid }}
    </p>

    <div v-if="confirmedOrder.sub_orders.length" class="success__card">
      <div class="success__card-title">Livraison prévue</div>
      <div v-for="sub in confirmedOrder.sub_orders" :key="sub.id" class="success__row">
        <span class="success__shop"><PhStorefront :size="15" /> {{ sub.shop_name }}</span>
        <strong v-if="sub.estimated_delivery_min && sub.estimated_delivery_max">
          {{ formatDeliveryEstimate(sub.estimated_delivery_min, sub.estimated_delivery_max) }}
        </strong>
      </div>
    </div>

    <ol class="success__next">
      <li>Le vendeur prépare votre colis.</li>
      <li>Un livreur l'apporte {{ addressSummary?.pickup ? 'au point de retrait' : 'à votre adresse' }}.</li>
      <li>Vous êtes notifié à chaque étape, et contacté avant la remise.</li>
    </ol>

    <div class="success__actions">
      <v-btn color="primary" block size="large" @click="goToOrder">Suivre ma commande</v-btn>
      <v-btn variant="text" block @click="continueShopping">Continuer mes achats</v-btn>
    </div>
  </div>

  <div v-else class="app-shell checkout-inner" style="padding-bottom: 110px">
    <div class="d-flex align-center pa-2 ga-2">
      <v-btn icon variant="text" :aria-label="step > 1 ? 'Étape précédente' : 'Retour'" @click="back">
        <PhArrowLeft :size="20" />
      </v-btn>
      <h1 class="text-h6 flex-grow-1">Commande</h1>
      <LayoutHomeLink />
    </div>

    <nav class="stepper px-4" aria-label="Étapes de la commande">
      <template v-for="(s, i) in STEPS" :key="s.n">
        <button
          type="button"
          class="stepper__step"
          :class="{ 'stepper__step--done': step > s.n, 'stepper__step--current': step === s.n }"
          :aria-current="step === s.n ? 'step' : undefined"
          @click="goTo(s.n)"
        >
          <span class="stepper__dot">
            <PhCheck v-if="step > s.n" :size="14" weight="bold" />
            <template v-else>{{ s.n }}</template>
          </span>
          <span class="stepper__label">{{ s.label }}</span>
        </button>
        <span v-if="i < STEPS.length - 1" class="stepper__bar" :class="{ 'stepper__bar--done': step > s.n }" />
      </template>
    </nav>

    <div class="px-4 checkout-page">
      <div class="checkout-form grid-card">
        <!-- 1. Livraison -->
        <section v-if="step === 1">
          <h2 class="step-title">Où livrer ?</h2>
          <div class="choice-list">
            <button
              v-for="a in addresses"
              :key="a.id"
              type="button"
              class="choice"
              :class="{ 'choice--selected': selectedId === a.id }"
              :aria-pressed="selectedId === a.id"
              @click="selectedId = a.id"
            >
              <span class="choice__icon" :style="{ '--hue': a.delivery_type === 'pickup_point' ? 215 : 150 }">
                <component :is="a.delivery_type === 'pickup_point' ? PhStorefront : PhHouse" :size="19" weight="duotone" />
              </span>
              <span class="choice__body">
                <span class="choice__title">
                  {{ a.label }}
                  <span v-if="a.is_default" class="choice__badge"><PhStar :size="10" weight="fill" /> Par défaut</span>
                </span>
                <span class="choice__text">
                  {{ a.delivery_type === 'pickup_point' ? 'Point de retrait' : 'Domicile' }} ·
                  {{ a.zone.trim() || (a.latitude != null ? 'Position GPS enregistrée' : 'Zone non précisée') }}
                </span>
              </span>
              <span class="choice__radio" />
            </button>
            <button
              type="button"
              class="choice choice--new"
              :class="{ 'choice--selected': selectedId === NEW_ADDRESS }"
              :aria-pressed="selectedId === NEW_ADDRESS"
              @click="selectedId = NEW_ADDRESS"
            >
              <span class="choice__icon" style="--hue: 220"><PhPlus :size="19" weight="bold" /></span>
              <span class="choice__body">
                <span class="choice__title">Nouvelle adresse</span>
                <span class="choice__text">À domicile ou dans un point de retrait</span>
              </span>
              <span class="choice__radio" />
            </button>
          </div>

          <div v-if="selectedId === NEW_ADDRESS" class="mt-4">
            <AddressForm v-model="newAddressForm" />
            <v-checkbox
              v-model="saveNewAddress"
              label="Enregistrer cette adresse pour mes prochains achats"
              density="compact"
              hide-details
            />
          </div>

          <p v-if="quote" class="step-hint">
            Livraison : <strong>{{ quote.delivery_total ? formatGnf(quote.delivery_total) : 'offerte' }}</strong>
            <template v-if="quote.vendors.length === 1">
              · {{ formatDeliveryEstimate(quote.vendors[0]!.estimated_delivery_min, quote.vendors[0]!.estimated_delivery_max) }}
            </template>
          </p>
        </section>

        <!-- 2. Paiement -->
        <section v-else-if="step === 2">
          <h2 class="step-title">Comment payer ?</h2>
          <div class="choice-list">
            <button
              v-for="option in PAYMENT_OPTIONS"
              :key="option.value"
              type="button"
              class="choice"
              :class="{ 'choice--selected': paymentMethod === option.value }"
              :aria-pressed="paymentMethod === option.value"
              @click="paymentMethod = option.value"
            >
              <span class="choice__icon" :style="{ '--hue': option.hue }">
                <component :is="option.icon" :size="19" weight="duotone" />
              </span>
              <span class="choice__body">
                <span class="choice__title">{{ option.title }}</span>
                <span class="choice__text">{{ option.text }}</span>
              </span>
              <span class="choice__radio" />
            </button>
            <button
              v-if="showWalletOption && buyerWallet"
              type="button"
              class="choice"
              :class="{ 'choice--selected': paymentMethod === 'wallet' }"
              :disabled="walletShortfall > 0 || !quote"
              :aria-pressed="paymentMethod === 'wallet'"
              @click="paymentMethod = 'wallet'"
            >
              <span class="choice__icon" style="--hue: 260"><PhWallet :size="19" weight="duotone" /></span>
              <span class="choice__body">
                <span class="choice__title">Solde NdjouriBank</span>
                <span class="choice__text">
                  Solde : {{ formatGnf(buyerWallet.balance) }}
                  <template v-if="quote && walletShortfall > 0"> · il manque {{ formatGnf(walletShortfall) }}</template>
                </span>
              </span>
              <span class="choice__radio" />
            </button>
          </div>

          <p v-if="showWalletOption && buyerWallet?.enabled && walletShortfall > 0 && quote" class="text-meta mt-2 mb-0">
            <NuxtLink to="/ndjouribank" class="wallet-topup-link">Recharger mon solde NdjouriBank</NuxtLink>
          </p>
          <p v-if="paymentMethod === 'wallet' && buyerWallet" class="step-hint">
            {{ formatGnf(orderTotal) }} seront débités à la confirmation. Nouveau solde :
            {{ formatGnf(buyerWallet.balance - orderTotal) }}.
          </p>
          <div v-if="paymentMethod === 'online'" class="mt-4">
            <v-text-field
              v-model="payerPhone"
              label="Numéro qui paie (mobile money ou carte)"
              placeholder="Ex. 622000000"
              inputmode="tel"
              hide-details="auto"
            />
            <p class="text-muted text-meta mt-1 mb-0">
              Après confirmation, vous serez redirigé vers le portail de paiement sécurisé pour valider.
            </p>
          </div>
          <p class="secure-note"><PhShieldCheck :size="15" weight="fill" /> Annulation remboursée tant que la commande n'est pas préparée.</p>
        </section>

        <!-- 3. Vérification -->
        <section v-else>
          <h2 class="step-title">Vérifiez votre commande</h2>

          <div class="review-block">
            <div class="review-block__head">
              <span>{{ addressSummary?.pickup ? 'Retrait au point' : 'Livraison à domicile' }}</span>
              <button type="button" class="review-block__edit" @click="goTo(1)">
                <PhPencilSimple :size="14" /> Modifier
              </button>
            </div>
            <div v-if="addressSummary" class="review-block__body">
              <strong>{{ addressSummary.label }}</strong>
              <span>{{ addressSummary.zone }}</span>
              <span v-if="addressSummary.recipient && !addressSummary.pickup">Pour : {{ addressSummary.recipient }}</span>
            </div>
          </div>

          <div class="review-block">
            <div class="review-block__head">
              <span>Paiement</span>
              <button type="button" class="review-block__edit" @click="goTo(2)">
                <PhPencilSimple :size="14" /> Modifier
              </button>
            </div>
            <div class="review-block__body">
              <strong>{{ paymentSummary.title }}</strong>
              <span>{{ paymentSummary.text }}</span>
            </div>
          </div>

          <div v-for="group in cart?.vendors ?? []" :key="group.vendor_id" class="review-block">
            <div class="review-block__head">
              <span><PhStorefront :size="14" /> {{ group.shop_name }}</span>
              <span v-if="deliveryEstimateFor(group.vendor_id)" class="review-block__eta">
                {{ deliveryEstimateFor(group.vendor_id) }}
              </span>
            </div>
            <div v-for="item in group.items" :key="item.id" class="line-item">
              <span class="line-item__thumb">
                <img v-if="item.product_image" :src="resolveImageUrl(item.product_image, apiBase, 160)" alt="" loading="lazy" />
                <PhImage v-else :size="18" />
              </span>
              <span class="line-item__body">
                <span class="line-item__name">{{ item.product_name }}</span>
                <span class="line-item__meta">
                  <template v-if="item.variant_label">{{ item.variant_label }} · </template>Qté {{ item.quantity }}
                </span>
              </span>
              <span class="line-item__price">{{ formatGnf(item.subtotal) }}</span>
            </div>
            <div class="line-fee">
              <span>Livraison</span>
              <span v-if="deliveryFeeFor(group.vendor_id) !== null">
                {{ deliveryFeeFor(group.vendor_id) ? formatGnf(deliveryFeeFor(group.vendor_id)!) : 'Offerte' }}
              </span>
              <span v-else>—</span>
            </div>
          </div>
        </section>
      </div>

      <!-- Récapitulatif toujours visible sur ordinateur. -->
      <aside v-if="cart" class="checkout-summary grid-card">
        <div class="checkout-summary__title">Récapitulatif</div>
        <div class="sum-line">
          <span>Articles ({{ itemCount }})</span>
          <span>{{ formatGnf(cart.total) }}</span>
        </div>
        <div class="sum-line">
          <span>Livraison</span>
          <span>{{ quote ? (quote.delivery_total ? formatGnf(quote.delivery_total) : 'Offerte') : '—' }}</span>
        </div>
        <div class="sum-line sum-line--total">
          <span>Total</span>
          <span>{{ formatGnf(orderTotal) }}</span>
        </div>
        <v-btn color="primary" block size="large" :loading="submitting" class="mt-4" @click="next">
          {{ primaryLabel }}
        </v-btn>
        <p v-if="!quote" class="text-muted text-meta mt-2 mb-0">Les frais de livraison s’affichent une fois l’adresse choisie.</p>
      </aside>
    </div>

    <!-- Téléphone : total + action principale ancrés en bas. -->
    <div class="checkout-bar checkout-bar--mobile-only">
      <div class="dock">
        <div class="dock__total">
          <span class="dock__amount">{{ formatGnf(orderTotal) }}</span>
          <span class="dock__meta">
            {{ itemCount }} article{{ itemCount > 1 ? 's' : '' }} ·
            {{ quote ? (quote.delivery_total ? `livraison ${formatGnf(quote.delivery_total)}` : 'livraison offerte') : 'hors livraison' }}
          </span>
        </div>
        <v-btn color="primary" size="large" class="dock__btn" :loading="submitting" @click="next">
          {{ step === 3 ? (paymentMethod === 'online' ? 'Payer' : 'Confirmer') : 'Continuer' }}
        </v-btn>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* --- Étapes --- */
.stepper {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 2px 0 14px;
}

.stepper__step {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0;
  border: 0;
  background: none;
  color: var(--color-neutral-500);
  cursor: pointer;
  flex-shrink: 0;
}

.stepper__dot {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: 2px solid var(--color-divider-strong);
  background: var(--color-neutral-900);
  font-size: 12.5px;
  font-weight: 800;
  transition: all 0.2s ease;
}

.stepper__label {
  font-size: 12.5px;
  font-weight: 700;
}

.stepper__step--current {
  color: var(--color-primary-300);
}

.stepper__step--current .stepper__dot {
  border-color: var(--color-primary);
  background: var(--color-primary);
  color: #fff;
  box-shadow: 0 0 0 4px var(--color-primary-100);
}

.stepper__step--done {
  color: var(--color-neutral-300);
}

.stepper__step--done .stepper__dot {
  border-color: var(--color-success);
  background: var(--color-success);
  color: #fff;
}

.stepper__bar {
  flex: 1;
  height: 2px;
  min-width: 12px;
  border-radius: 2px;
  background: var(--color-divider-strong);
  transition: background 0.2s ease;
}

.stepper__bar--done {
  background: var(--color-success);
}

@media (max-width: 380px) {
  .stepper__step:not(.stepper__step--current) .stepper__label {
    display: none;
  }
}

.step-title {
  font-family: var(--font-heading);
  font-size: 18px;
  font-weight: 800;
  margin: 0 0 14px;
}

.step-hint {
  margin: 14px 0 0;
  font-size: 13px;
  color: var(--color-neutral-400);
}

.step-hint strong {
  color: var(--color-neutral-200);
}

/* --- Cartes de choix (adresse, paiement) --- */
.choice-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.choice {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 12px;
  border: 1.5px solid var(--color-divider-strong);
  border-radius: var(--radius-md);
  background: var(--color-neutral-900);
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
}

.choice:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.choice--selected {
  border-color: var(--color-primary);
  background: color-mix(in srgb, var(--color-primary) 5%, var(--color-neutral-900));
  box-shadow: 0 0 0 3px var(--color-primary-100);
}

.choice--new {
  border-style: dashed;
}

.choice__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  border-radius: 12px;
  background: hsl(var(--hue) 70% var(--tint-bg));
  color: hsl(var(--hue) 60% var(--tint-fg));
}

.choice__body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.choice__title {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  font-weight: 700;
  font-size: 14.5px;
  color: var(--color-neutral-200);
}

.choice__badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 7px;
  border-radius: 999px;
  background: var(--color-primary-100);
  color: var(--color-primary-300);
  font-size: 10.5px;
  font-weight: 700;
}

.choice__text {
  font-size: 12.5px;
  color: var(--color-neutral-400);
  overflow: hidden;
  text-overflow: ellipsis;
}

.choice__radio {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  border-radius: 50%;
  border: 2px solid var(--color-divider-strong);
  transition: border 0.15s ease;
}

.choice--selected .choice__radio {
  border: 6px solid var(--color-primary);
}

.secure-note {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 16px 0 0;
  font-size: 12.5px;
  color: var(--color-success);
}

.wallet-topup-link {
  color: var(--color-primary);
  font-weight: 600;
}

/* --- Vérification --- */
.review-block {
  padding: 12px 0;
  border-top: 1px solid var(--color-divider);
}

.review-block:first-of-type {
  border-top: 0;
  padding-top: 0;
}

.review-block__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 11.5px;
  font-weight: 800;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: var(--color-neutral-500);
}

.review-block__head > span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.review-block__edit {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: 0;
  background: none;
  color: var(--color-primary-300);
  font-size: 12.5px;
  font-weight: 700;
  text-transform: none;
  letter-spacing: 0;
  cursor: pointer;
}

.review-block__eta {
  color: var(--color-success);
  text-transform: none;
  letter-spacing: 0;
  font-size: 12px;
}

.review-block__body {
  display: flex;
  flex-direction: column;
  font-size: 13px;
  color: var(--color-neutral-400);
}

.review-block__body strong {
  font-size: 14.5px;
  color: var(--color-neutral-200);
}

.line-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 0;
}

.line-item__thumb {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  flex-shrink: 0;
  overflow: hidden;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-divider);
  background: #fff;
  color: var(--color-neutral-500);
}

.line-item__thumb img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.line-item__body {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.line-item__name {
  font-size: 13.5px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.line-item__meta {
  font-size: 12px;
  color: var(--color-neutral-400);
}

.line-item__price {
  font-size: 13.5px;
  font-weight: 700;
  white-space: nowrap;
}

.line-fee {
  display: flex;
  justify-content: space-between;
  padding-top: 4px;
  font-size: 12.5px;
  color: var(--color-neutral-400);
}

/* --- Récapitulatif --- */
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
  font-size: 17px;
  font-weight: 800;
  color: var(--color-neutral-200);
}

.dock {
  display: flex;
  align-items: center;
  gap: 12px;
}

.dock__total {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.dock__amount {
  font-family: var(--font-heading);
  font-size: 18px;
  font-weight: 800;
  color: var(--color-neutral-200);
}

.dock__meta {
  font-size: 11.5px;
  color: var(--color-neutral-400);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dock__btn {
  flex-shrink: 0;
  min-width: 132px;
}

.checkout-summary {
  display: none;
}

@media (min-width: 960px) {
  .checkout-inner {
    max-width: 1120px;
    margin: 0 auto;
  }

  .stepper {
    max-width: 560px;
  }

  .checkout-page {
    display: grid;
    grid-template-columns: 1fr 340px;
    align-items: start;
    gap: 32px;
  }

  .checkout-form {
    padding: 24px 28px;
  }

  .checkout-summary {
    display: block;
    position: sticky;
    top: 16px;
    padding: 20px;
  }

  .checkout-bar--mobile-only {
    display: none;
  }
}

@media (max-width: 959px) {
  .checkout-form {
    padding: 16px;
  }
}

.checkout-summary__title {
  font-family: var(--font-heading);
  font-weight: 700;
  font-size: 15px;
  margin-bottom: 10px;
}

/* --- Succès --- */
.success {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 48px 20px 32px;
  text-align: center;
}

.success__burst {
  position: relative;
  width: 96px;
  height: 96px;
  margin-bottom: 20px;
}

.success__check {
  position: absolute;
  inset: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--color-success);
  color: #fff;
  animation: pop 0.45s cubic-bezier(0.2, 1.4, 0.4, 1) both;
}

.success__ring {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 3px solid var(--color-success);
  animation: ring 0.9s ease-out 0.15s both;
}

@keyframes pop {
  from {
    transform: scale(0.3);
    opacity: 0;
  }
  to {
    transform: scale(1);
    opacity: 1;
  }
}

@keyframes ring {
  from {
    transform: scale(0.7);
    opacity: 0.9;
  }
  to {
    transform: scale(1.35);
    opacity: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .success__check,
  .success__ring {
    animation: none;
  }
}

.success__title {
  font-family: var(--font-heading);
  font-size: 24px;
  font-weight: 800;
  margin: 0 0 6px;
}

.success__sub {
  font-size: 14px;
  color: var(--color-neutral-400);
  margin: 0 0 20px;
}

.success__card {
  width: 100%;
  max-width: 420px;
  padding: 14px 16px;
  border-radius: var(--radius-md);
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider);
  text-align: left;
}

.success__card-title {
  font-size: 11.5px;
  font-weight: 800;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: var(--color-neutral-500);
  margin-bottom: 6px;
}

.success__row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 0;
  font-size: 13.5px;
}

.success__row strong {
  color: var(--color-success);
}

.success__shop {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--color-neutral-300);
}

.success__next {
  width: 100%;
  max-width: 420px;
  margin: 18px 0 24px;
  padding-left: 20px;
  text-align: left;
  font-size: 13px;
  line-height: 1.7;
  color: var(--color-neutral-400);
}

.success__actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
  max-width: 420px;
}
</style>
