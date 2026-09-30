<script setup lang="ts">
import { PhArrowLeft, PhGift, PhMapPin, PhSparkle } from '@phosphor-icons/vue'
import type { VendorRead, VendorStatus, WalletRead } from '~/types/api'

definePageMeta({ middleware: 'vendor', layout: 'vendeur' })

const { apiFetch } = useApi()
const toast = useToastStore()
const { locating, locate } = useGeolocation()

// getCachedData: hydrateThenRefetch — see app/pages/vendeur/index.vue.
const { data: vendor } = await useAsyncData('vendor-me-settings', () => apiFetch<VendorRead>('/vendors/me'), {
  getCachedData: hydrateThenRefetch,
})

const shopName = ref('')
const zone = ref('')
const preparationDays = ref(1)
const latitude = ref<number | null>(null)
const longitude = ref<number | null>(null)
const offersPickup = ref(false)
const offerMin = ref(0)
// Plafonds facultatifs : champ vide = sans plafond (null côté API).
const offerMaxAmount = ref('')
const offerMaxKm = ref('')

function optionalPositive(value: string): number | null {
  const n = Number(String(value).replace(',', '.').trim())
  return String(value).trim() && Number.isFinite(n) && n > 0 ? n : null
}

// Solde vendeur : l'offre ne s'applique que s'il couvre la course (pas de
// solde négatif) — voir backend app/orders/pickup_offer.py.
const { data: wallets } = await useAsyncData('vendor-wallets-offer', () => apiFetch<WalletRead[]>('/wallets/mine'), {
  default: () => [],
})
const vendorWallet = computed(() => wallets.value.find((w) => w.kind === 'vendor') ?? null)
const offerCapacity = computed(() =>
  vendorWallet.value ? vendorWallet.value.balance.available - (vendorWallet.value.committed_offers ?? 0) : 0,
)
watch(
  vendor,
  (v) => {
    if (!v) return
    shopName.value = v.shop_name
    zone.value = v.zone ?? ''
    preparationDays.value = v.preparation_days
    latitude.value = v.latitude
    longitude.value = v.longitude
    offersPickup.value = v.offers_pickup_delivery
    offerMin.value = v.pickup_offer_min_amount
    offerMaxAmount.value = v.pickup_offer_max_amount != null ? String(v.pickup_offer_max_amount) : ''
    offerMaxKm.value = v.pickup_offer_max_km != null ? String(v.pickup_offer_max_km) : ''
  },
  { immediate: true },
)

const hasPosition = computed(() => latitude.value !== null && longitude.value !== null)
const positionLabel = computed(() =>
  hasPosition.value ? `${latitude.value!.toFixed(4)}, ${longitude.value!.toFixed(4)}` : '',
)

async function useCurrentPosition() {
  try {
    const position = await locate()
    latitude.value = position.latitude
    longitude.value = position.longitude
    toast.success('Position enregistrée.')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Impossible de récupérer ta position.')
  }
}

const statusMeta: Record<VendorStatus, { label: string; color: string }> = {
  pending: { label: 'En attente de validation', color: 'warning' },
  approved: { label: 'Approuvée', color: 'success' },
  rejected: { label: 'Rejetée', color: 'error' },
  suspended: { label: 'Suspendue', color: 'error' },
}

const submitting = ref(false)

async function submit() {
  if (shopName.value.trim().length < 2) {
    toast.error('Le nom de la boutique doit contenir au moins 2 caractères.')
    return
  }
  submitting.value = true
  try {
    vendor.value = await apiFetch<VendorRead>('/vendors/me', {
      method: 'PATCH',
      body: {
        shop_name: shopName.value.trim(),
        zone: zone.value.trim() || null,
        latitude: latitude.value,
        longitude: longitude.value,
        preparation_days: preparationDays.value,
        offers_pickup_delivery: offersPickup.value,
        pickup_offer_min_amount: Math.max(0, Math.round(Number(offerMin.value) || 0)),
        pickup_offer_max_amount: (() => {
          const cap = optionalPositive(offerMaxAmount.value)
          return cap === null ? null : Math.round(cap)
        })(),
        pickup_offer_max_km: optionalPositive(offerMaxKm.value),
      },
    })
    toast.success('Boutique mise à jour.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de sauvegarder ces réglages.'))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="dashboard-shell">
   <div class="form-panel">
    <h1 class="text-h6 mb-4">Réglages de la boutique</h1>

    <template v-if="vendor">
      <v-card class="pa-4 mb-4" variant="flat">
        <div class="d-flex align-center justify-space-between mb-4">
          <span class="text-muted" style="font-size: 12.5px">Statut</span>
          <v-chip :color="statusMeta[vendor.status].color" size="small" variant="tonal">
            {{ statusMeta[vendor.status].label }}
          </v-chip>
        </div>
        <div class="d-flex align-center justify-space-between mb-1">
          <span class="text-muted" style="font-size: 12.5px">Commission plateforme</span>
          <span style="font-size: 13px">{{ vendor.commission_rate }}%</span>
        </div>
      </v-card>

      <v-card class="pa-4 mb-4" variant="flat">
        <div class="section-title mb-3">Informations générales</div>
        <label class="field-label">Nom de la boutique</label>
        <v-text-field v-model="shopName" class="mb-2" />

        <label class="field-label">Zone</label>
        <v-text-field v-model="zone" placeholder="Ex: Kaloum" class="mb-2" />

        <label class="field-label">Délai de préparation habituel (jours)</label>
        <v-text-field
          v-model.number="preparationDays"
          type="number"
          min="0"
          max="14"
          class="mb-1"
        />
        <p class="text-muted mb-0" style="font-size: 11.5px">
          Utilisé pour l'estimation de livraison affichée aux acheteurs sur vos produits.
        </p>
      </v-card>

      <v-card class="pa-4 mb-4 offer-card" variant="flat">
        <div class="d-flex align-center justify-space-between ga-3">
          <div class="d-flex align-center ga-3">
            <span class="offer-card__icon"><PhGift :size="20" weight="fill" /></span>
            <div>
              <div class="section-title">Retrait offert</div>
              <div class="text-muted" style="font-size: 12px">Vous payez la livraison vers le point de retrait choisi par le client.</div>
            </div>
          </div>
          <v-switch v-model="offersPickup" color="primary" hide-details inset density="compact" class="flex-grow-0 flex-shrink-0" aria-label="Offrir le retrait" />
        </div>

        <template v-if="offersPickup">
          <label class="field-label mt-4">À partir d'un achat de (GNF)</label>
          <v-text-field v-model.number="offerMin" type="number" min="0" step="1000" placeholder="0 = dès le premier article" class="mb-1" />
          <p class="text-muted mb-3" style="font-size: 11.5px">
            Le client voit « Retrait offert » sur vos produits. Au moment de la commande, la livraison en point de retrait
            ne lui est pas facturée si son panier chez vous atteint ce montant.
          </p>

          <div class="offer-caps">
            <div>
              <label class="field-label">Je prends en charge jusqu'à (GNF)</label>
              <v-text-field v-model="offerMaxAmount" inputmode="numeric" placeholder="Vide = toute la course" suffix="GNF" hide-details />
            </div>
            <div>
              <label class="field-label">Jusqu'à une distance de</label>
              <v-text-field v-model="offerMaxKm" inputmode="decimal" placeholder="Vide = sans limite" suffix="km" hide-details />
            </div>
          </div>
          <p class="text-muted mb-3 mt-1" style="font-size: 11.5px">
            Au-delà du plafond, le client paie le reste de la course. Si le point de retrait est plus loin que la distance
            choisie (depuis votre boutique), l'offre ne s'applique pas.
          </p>
          <ul class="offer-rules">
            <li>La course est prélevée sur votre solde NdjouriBank à la livraison du colis. Rien si la commande est annulée.</li>
            <li>L'offre ne s'applique que si votre solde disponible couvre la course : sinon le client paie la livraison comme d'habitude.</li>
            <li>Les montants engagés sur des colis en route ne peuvent pas être retirés.</li>
          </ul>
          <div class="offer-balance" :class="{ 'is-low': offerCapacity <= 0 }">
            <span>Disponible pour offrir</span>
            <strong>{{ formatGnf(Math.max(0, offerCapacity)) }}</strong>
          </div>
          <p v-if="vendorWallet?.committed_offers" class="text-muted mt-1 mb-0" style="font-size: 11.5px">
            Dont {{ formatGnf(vendorWallet.committed_offers) }} déjà engagés sur des colis en cours.
          </p>
          <p v-if="offerCapacity <= 0" class="text-muted mt-1 mb-0" style="font-size: 11.5px">
            Solde insuffisant pour le moment : l'offre s'activera automatiquement dès que vos gains seront disponibles.
          </p>
        </template>
      </v-card>

      <v-card class="pa-4 mb-4" variant="flat">
        <div class="section-title mb-3">Position de la boutique</div>
        <p class="text-muted mb-2" style="font-size: 11.5px">
          Utilisée pour calculer les frais de livraison et proposer la livraison au livreur disponible le plus proche.
        </p>
        <v-btn color="primary" block :loading="locating" class="mb-2" @click="useCurrentPosition">
          <PhMapPin :size="17" class="mr-1" />
          {{ hasPosition ? 'Mettre à jour ma position actuelle' : 'Utiliser ma position actuelle' }}
        </v-btn>
        <p class="text-muted mb-2" style="font-size: 11.5px">Ou touche la carte pour placer le repère toi-même.</p>
        <CommonMapPicker v-model:latitude="latitude" v-model:longitude="longitude" class="mb-2" />
        <div v-if="hasPosition" class="d-flex align-center ga-1" style="font-size: 12px">
          <span class="text-muted">{{ positionLabel }}</span>
        </div>
        <v-alert v-else type="warning" variant="tonal" density="compact" class="mb-0">
          Position manquante : les frais de livraison de tes commandes sont facturés au tarif le plus élevé et tu ne
          peux pas rechercher automatiquement un livreur. Renseigne-la puis enregistre.
        </v-alert>
      </v-card>

      <v-btn color="primary" block size="large" class="mb-6" :loading="submitting" @click="submit">Enregistrer</v-btn>
    </template>

    <v-card variant="flat" class="pa-2">
      <NuxtLink to="/vendeur/abonnement" class="list-item">
        <PhSparkle :size="18" color="var(--color-neutral-400)" />
        <span>Abonnement et quotas</span>
      </NuxtLink>
      <v-divider />
      <NuxtLink to="/profil" class="list-item">
        <PhArrowLeft :size="18" color="var(--color-neutral-400)" />
        <span>Retour à l'espace acheteur</span>
      </NuxtLink>
    </v-card>
   </div>
  </div>
</template>

<style scoped>
.offer-card__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  border-radius: 12px;
  background: linear-gradient(135deg, hsl(150 70% 45%), hsl(170 70% 40%));
  color: #fff;
}

.offer-caps {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 10px 14px;
}

.offer-rules {
  margin: 0 0 12px;
  padding-left: 18px;
  font-size: 12px;
  color: var(--color-neutral-400);
}

.offer-rules li + li {
  margin-top: 4px;
}

.offer-balance {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  background: hsl(150 70% var(--tint-bg));
  color: hsl(150 55% var(--tint-fg));
  font-size: 13px;
  font-weight: 600;
}

.offer-balance.is-low {
  background: hsl(38 90% var(--tint-bg));
  color: hsl(30 75% var(--tint-fg));
}

.list-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 13px 0;
  font-size: 13.5px;
  text-decoration: none;
  color: inherit;
}
</style>
