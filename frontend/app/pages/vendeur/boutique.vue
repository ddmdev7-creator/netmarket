<script setup lang="ts">
import { PhArrowLeft, PhMapPin, PhSparkle } from '@phosphor-icons/vue'
import type { VendorRead, VendorStatus } from '~/types/api'

definePageMeta({ middleware: 'vendor', layout: 'vendeur' })

const { apiFetch } = useApi()
const toast = useToastStore()
const { locating, locate } = useGeolocation()

// getCachedData: () => undefined — see app/pages/vendeur/index.vue.
const { data: vendor } = await useAsyncData('vendor-me-settings', () => apiFetch<VendorRead>('/vendors/me'), {
  getCachedData: () => undefined,
})

const shopName = ref('')
const zone = ref('')
const preparationDays = ref(1)
const latitude = ref<number | null>(null)
const longitude = ref<number | null>(null)
watch(
  vendor,
  (v) => {
    if (!v) return
    shopName.value = v.shop_name
    zone.value = v.zone ?? ''
    preparationDays.value = v.preparation_days
    latitude.value = v.latitude
    longitude.value = v.longitude
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

      <v-card class="pa-4 mb-4" variant="flat">
        <div class="section-title mb-3">Position de la boutique</div>
        <p class="text-muted mb-2" style="font-size: 11.5px">
          Utilisée pour proposer la livraison au livreur disponible le plus proche.
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
          Sans position, tu ne pourras pas rechercher automatiquement un livreur.
        </v-alert>
      </v-card>

      <v-btn color="primary" block size="large" class="mb-6" :loading="submitting" @click="submit">Enregistrer</v-btn>
    </template>

    <v-card variant="flat" class="pa-2">
      <NuxtLink to="/vendeur/abonnement" class="list-item">
        <PhSparkle :size="18" color="var(--color-neutral-400)" />
        <span>Abonnement premium</span>
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
