<script setup lang="ts">
import { PhArrowLeft, PhCheckCircle, PhPlus, PhStar } from '@phosphor-icons/vue'
import type { AddressFormValues } from '~/components/address/AddressForm.vue'
import type { AddressRead, OrderRead } from '~/types/api'

definePageMeta({ middleware: 'auth', layout: 'blank' })

const cartStore = useCartStore()
const router = useRouter()
const { apiFetch } = useApi()
const toast = useToastStore()

await useAsyncData('checkout-cart', () => cartStore.fetchCart())

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

const cart = computed(() => cartStore.cart)

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

  submitting.value = true
  try {
    let deliveryAddress: string
    let deliveryType: string
    let pickupPointId: string | null
    let deliveryZone: string
    let deliveryInstructions: string | null
    let recipientName: string | null
    let recipientPhone: string | null

    if (usingNew) {
      deliveryAddress = buildAddressText(newAddressForm.value, newAddressForm.value.delivery_type)
      deliveryType = newAddressForm.value.delivery_type
      pickupPointId = newAddressForm.value.pickup_point_id
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
      deliveryZone = zoneText(selected)
      deliveryInstructions = selected.instructions
      recipientName = selected.recipient_name
      recipientPhone = selected.recipient_phone
    }

    confirmedOrder.value = await apiFetch<OrderRead>('/orders/checkout', {
      method: 'POST',
      body: {
        delivery_address: deliveryAddress,
        delivery_type: deliveryType,
        pickup_point_id: pickupPointId ?? undefined,
        delivery_zone: deliveryZone || undefined,
        delivery_instructions: deliveryInstructions ?? undefined,
        recipient_name: recipientName ?? undefined,
        recipient_phone: recipientPhone ?? undefined,
        payment_method: 'cash_on_delivery',
      },
    })
    cartStore.reset()
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
  <div class="app-shell" style="padding-bottom: 88px">
    <div class="d-flex align-center pa-2 ga-2">
      <v-btn icon variant="text" @click="router.back()">
        <PhArrowLeft :size="20" />
      </v-btn>
      <h1 class="text-h6">Commande et paiement</h1>
      <LayoutHomeLink />
    </div>

    <div class="px-4">
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
      <v-radio-group model-value="cod" hide-details class="mb-4">
        <v-radio label="Paiement à la livraison" value="cod" color="primary" />
        <v-radio value="nimbapay" disabled>
          <template #label>
            <span class="text-muted">NimbaPay</span>
            <v-chip size="x-small" variant="tonal" class="ml-2">Bientôt disponible</v-chip>
          </template>
        </v-radio>
      </v-radio-group>

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
        </div>
        <v-divider class="mb-2" />
        <div class="d-flex justify-space-between text-lg">
          <span>Total</span>
          <span>{{ formatGnf(cart.total) }}</span>
        </div>
      </template>
    </div>

    <div class="checkout-bar">
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
</style>
