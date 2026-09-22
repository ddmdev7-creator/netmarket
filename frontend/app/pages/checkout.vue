<script setup lang="ts">
import { PhArrowLeft, PhCheckCircle, PhPlus, PhStar } from '@phosphor-icons/vue'
import type { AddressFormValues } from '~/components/address/AddressForm.vue'
import type { AddressRead, DeliveryQuoteRead, OrderRead } from '~/types/api'

definePageMeta({ middleware: 'auth', layout: 'blank' })

const cartStore = useCartStore()
const auth = useAuthStore()
const router = useRouter()
const { apiFetch } = useApi()
const toast = useToastStore()

await useAsyncData('checkout-cart', () => cartStore.fetchCart())

// Un aller-retour navigateur ("précédent") après confirmation d'une commande
// remonte sur cette page avec un panier déjà vidé côté serveur (voir
// confirmOrder ci-dessous, qui appelle cartStore.reset() sur succès) — sans
// ce garde-fou, l'acheteur se retrouverait sur un écran de paiement figé,
// vide de tout article, qu'il pourrait même tenter de soumettre à nouveau.
// Vérifié une seule fois ici (pas un watcher) : la modale de confirmation
// affichée juste après confirmOrder tourne sur cette même page avec le
// panier déjà réinitialisé, un watcher redirigerait alors immédiatement
// loin de cette modale.
if ((cartStore.cart?.vendors.length ?? 0) === 0) {
  await navigateTo('/panier')
}

const { data: addresses } = await useAsyncData('checkout-addresses', () => apiFetch<AddressRead[]>('/addresses'), {
  default: () => [],
})

// "new" est une valeur de sélection à part entière (comme les adresses
// enregistrées) plutôt qu'un simple booléen — évite un état incohérent où
// aucune option ne serait sélectionnée pendant le chargement.
const NEW_ADDRESS = 'new' as const
const selectedId = ref<string>(addresses.value[0]?.id ?? NEW_ADDRESS)

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

// "cash_on_delivery" par défaut — le paiement en ligne reste un choix actif,
// pas la valeur de repli si l'acheteur ne remplit rien.
const paymentMethod = ref<'cash_on_delivery' | 'online'>('cash_on_delivery')
const payerPhone = ref(auth.user?.phone ?? '')

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

async function confirmOrder() {
  const usingNew = selectedId.value === NEW_ADDRESS
  if (usingNew) {
    const error = validateAddressForm(newAddressForm.value)
    if (error) {
      toast.error(error)
      return
    }
  } else {
    // Défense en profondeur : une adresse enregistrée avant ce correctif a
    // pu être sauvée en mode "point de retrait" sans point réellement
    // choisi (voir validateAddressForm) — mieux vaut le dire clairement ici
    // que laisser l'API renvoyer un 409 générique.
    const selected = addresses.value.find((a) => a.id === selectedId.value)
    if (selected?.delivery_type === 'pickup_point' && !selected.pickup_point_id) {
      toast.error('Cette adresse n’a pas de point de retrait valide — modifie-la ou choisis-en une autre.')
      return
    }
  }

  if (paymentMethod.value === 'online' && !payerPhone.value.trim()) {
    toast.error('Indique le numéro qui va payer (mobile money ou carte).')
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
  <div class="app-shell checkout-inner" style="padding-bottom: 88px">
    <div class="d-flex align-center pa-2 ga-2">
      <v-btn icon variant="text" @click="router.back()">
        <PhArrowLeft :size="20" />
      </v-btn>
      <h1 class="text-h6">Commande et paiement</h1>
      <LayoutHomeLink />
    </div>

    <div class="px-4 checkout-page">
      <div class="checkout-form grid-card">
      <label class="field-label">Adresse de livraison</label>
      <v-radio-group v-model="selectedId" hide-details>
        <v-radio
          v-for="a in addresses"
          :key="a.id"
          :value="a.id"
          density="compact"
          color="primary"
          class="address-option"
          :class="{ 'address-option--selected': selectedId === a.id }"
        >
          <template #label>
            <div class="flex-grow-1">
              <div class="d-flex align-center ga-2">
                <span class="text-body" style="font-weight: 600">{{ a.label }}</span>
                <v-chip v-if="a.is_default" color="primary" size="x-small" variant="tonal">
                  <PhStar :size="10" weight="fill" class="mr-1" />
                  Par défaut
                </v-chip>
                <v-chip size="x-small" variant="tonal">
                  {{ a.delivery_type === 'pickup_point' ? 'Point de retrait' : 'Domicile' }}
                </v-chip>
              </div>
              <div class="text-muted text-meta">{{ a.zone }}</div>
            </div>
          </template>
        </v-radio>

        <v-radio
          :value="NEW_ADDRESS"
          density="compact"
          color="primary"
          class="address-option"
          :class="{ 'address-option--selected': selectedId === NEW_ADDRESS }"
        >
          <template #label>
            <div class="d-flex align-center ga-1 text-body" style="font-weight: 600">
              <PhPlus :size="15" />
              <span>Nouvelle adresse</span>
            </div>
          </template>
        </v-radio>
      </v-radio-group>

      <div v-if="selectedId === NEW_ADDRESS" class="mt-3 mb-2">
        <AddressForm v-model="newAddressForm" />
        <v-checkbox
          v-model="saveNewAddress"
          label="Enregistrer cette adresse pour mes prochains achats"
          density="compact"
          hide-details
          class="mb-2"
        />
      </div>

      <v-divider class="mb-4 mt-2" />

      <h3 class="section-title">Paiement</h3>
      <v-radio-group v-model="paymentMethod" hide-details class="mb-2">
        <v-radio label="Paiement à la livraison" value="cash_on_delivery" color="primary" />
        <v-radio label="Payer en ligne" value="online" color="primary" />
      </v-radio-group>
      <div v-if="paymentMethod === 'online'" class="mb-4">
        <v-text-field
          v-model="payerPhone"
          label="Numéro qui paie (mobile money ou carte)"
          placeholder="Ex. 622000000"
          hide-details="auto"
        />
        <p class="text-muted text-meta mt-1 mb-0">
          Tu seras redirigé vers le portail de paiement pour finaliser (Orange Money, MTN MoMo, carte…).
        </p>
      </div>

      <v-divider class="mb-4" />

      <h3 class="section-title">Récapitulatif</h3>
      <template v-if="cart">
        <div v-for="group in cart.vendors" :key="group.vendor_id" class="mb-3">
          <div class="recap-shop-label mb-1">{{ group.shop_name }}</div>
          <div v-for="item in group.items" :key="item.id" class="d-flex justify-space-between text-meta">
            <span
              >{{ item.product_name }}<span v-if="item.variant_label" class="text-muted"> ({{ item.variant_label }})</span> ×
              {{ item.quantity }}</span
            >
            <span>{{ formatGnf(item.subtotal) }}</span>
          </div>
          <div class="d-flex justify-space-between text-meta text-muted">
            <span>Livraison</span>
            <span v-if="deliveryFeeFor(group.vendor_id) !== null">
              {{ deliveryFeeFor(group.vendor_id) ? formatGnf(deliveryFeeFor(group.vendor_id)!) : 'Gratuite' }}
            </span>
            <span v-else>—</span>
          </div>
          <div v-if="deliveryEstimateFor(group.vendor_id)" class="d-flex justify-space-between text-meta text-muted">
            <span>Délai estimé</span>
            <span>{{ deliveryEstimateFor(group.vendor_id) }}</span>
          </div>
        </div>
        <v-divider class="mb-2" />
        <div class="d-flex justify-space-between text-lg checkout-total-inline">
          <span>Total</span>
          <span>{{ formatGnf(quote?.total ?? cart.total) }}</span>
        </div>
        <p v-if="!quote" class="text-muted text-meta mt-1 mb-0">Les frais de livraison s’affichent une fois l’adresse choisie.</p>
      </template>
      </div>

      <!-- Repris dans .checkout-total-inline ci-dessus sur mobile -- l'un des
           deux est toujours masqué par media query, jamais les deux à la
           fois (même pattern que .cart-summary dans panier.vue). -->
      <aside v-if="cart" class="checkout-summary grid-card">
        <div class="checkout-summary__title">Résumé</div>
        <div class="d-flex justify-space-between text-lg mb-4">
          <span>Total</span>
          <span>{{ formatGnf(quote?.total ?? cart.total) }}</span>
        </div>
        <v-btn color="primary" block size="large" :loading="submitting" @click="confirmOrder">
          Confirmer la commande
        </v-btn>
        <p v-if="!quote" class="text-muted text-meta mt-2 mb-0">Les frais de livraison s’affichent une fois l’adresse choisie.</p>
      </aside>
    </div>

    <div class="checkout-bar checkout-bar--mobile-only">
      <v-btn color="primary" block size="large" :loading="submitting" @click="confirmOrder">
        Confirmer la commande
      </v-btn>
    </div>

    <v-dialog :model-value="!!confirmedOrder" persistent max-width="340">
      <v-card v-if="confirmedOrder" class="pa-6 text-center">
        <PhCheckCircle :size="44" weight="fill" color="var(--color-success)" style="margin: 0 auto" />
        <div class="text-h6 mt-3">Commande confirmée</div>
        <div class="text-muted mt-2 text-meta">
          Commande #{{ confirmedOrder.id.slice(0, 8).toUpperCase() }} · Paiement à la livraison<br />
          Vous serez contacté avant la livraison.
        </div>
        <div v-if="confirmedOrder.sub_orders.length" class="text-left mt-4">
          <div
            v-for="sub in confirmedOrder.sub_orders"
            :key="sub.id"
            class="d-flex justify-space-between text-meta"
          >
            <span class="text-muted">{{ sub.shop_name }}</span>
            <strong v-if="sub.estimated_delivery_min && sub.estimated_delivery_max">
              {{ formatDeliveryEstimate(sub.estimated_delivery_min, sub.estimated_delivery_max) }}
            </strong>
          </div>
        </div>
        <div class="d-flex flex-column ga-2 mt-5">
          <v-btn color="primary" block @click="goToOrder">Voir ma commande</v-btn>
          <v-btn variant="outlined" block @click="continueShopping">Continuer mes achats</v-btn>
        </div>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.recap-shop-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--color-primary-300);
  opacity: 0.85;
}

.address-option {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 10px 8px;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-md);
  margin-bottom: 8px;
  cursor: pointer;
}

.address-option--selected {
  border-color: var(--color-primary);
}

/* Sur mobile, une seule colonne : .checkout-summary n'existe pas encore, le
   total reste inline dans le récapitulatif et le bouton vit dans la barre
   collante du bas (même pattern que panier.vue). */
.checkout-summary {
  display: none;
}

/* .app-shell plafonne à 720px par défaut (voir main.css) -- trop étroit
   pour un formulaire + récapitulatif côte à côte sur ordinateur. Même
   largeur que .cart-inner (panier.vue), ce checkout ayant une forme très
   proche (liste + résumé fixe). */
@media (min-width: 960px) {
  .checkout-inner {
    max-width: 1120px;
    margin: 0 auto;
  }

  .checkout-page {
    display: grid;
    grid-template-columns: 1fr 320px;
    align-items: start;
    gap: 32px;
  }

  .checkout-total-inline {
    /* Remplacé par .checkout-summary à cette largeur. */
    display: none;
  }

  /* .grid-card (main.css) fournit le fond/bordure/ombre, partagés avec
     .cart-list/.cart-summary (panier.vue) -- les deux colonnes forment une
     vraie paire de cartes détachées plutôt qu'une seule. */
  .checkout-form {
    padding: 24px 28px;
  }

  .checkout-summary {
    display: block;
    position: sticky;
    top: 16px;
    padding: 20px;
  }

  /* Redondant avec le bouton de .checkout-summary à cette largeur. */
  .checkout-bar--mobile-only {
    display: none;
  }
}

.checkout-summary__title {
  font-family: var(--font-heading);
  font-weight: 700;
  font-size: 15px;
  margin-bottom: 14px;
}
</style>
