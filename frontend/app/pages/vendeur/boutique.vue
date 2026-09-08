<script setup lang="ts">
import { PhArrowLeft, PhSparkle } from '@phosphor-icons/vue'
import type { VendorRead, VendorStatus } from '~/types/api'

definePageMeta({ middleware: 'vendor', layout: 'vendeur' })

const { apiFetch } = useApi()
const toast = useToastStore()

// getCachedData: () => undefined — see app/pages/vendeur/index.vue.
const { data: vendor } = await useAsyncData('vendor-me-settings', () => apiFetch<VendorRead>('/vendors/me'), {
  getCachedData: () => undefined,
})

const shopName = ref('')
const zone = ref('')
const preparationDays = ref(1)
watch(
  vendor,
  (v) => {
    if (!v) return
    shopName.value = v.shop_name
    zone.value = v.zone ?? ''
    preparationDays.value = v.preparation_days
  },
  { immediate: true },
)

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
  <div class="app-shell pa-4" style="padding-bottom: 76px">
    <h1 class="text-h6 mb-4">Réglages de la boutique</h1>

    <template v-if="vendor">
      <div class="d-flex align-center justify-space-between mb-4">
        <span class="text-muted" style="font-size: 12.5px">Statut</span>
        <v-chip :color="statusMeta[vendor.status].color" size="small" variant="tonal">
          {{ statusMeta[vendor.status].label }}
        </v-chip>
      </div>
      <div class="d-flex align-center justify-space-between mb-5">
        <span class="text-muted" style="font-size: 12.5px">Commission plateforme</span>
        <span style="font-size: 13px">{{ vendor.commission_rate }}%</span>
      </div>

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
      <p class="text-muted mb-4" style="font-size: 11.5px">
        Utilisé pour l'estimation de livraison affichée aux acheteurs sur vos produits.
      </p>

      <v-btn color="primary" block size="large" class="mb-6" :loading="submitting" @click="submit">Enregistrer</v-btn>
    </template>

    <v-divider class="mb-2" />
    <NuxtLink to="/vendeur/abonnement" class="list-item">
      <PhSparkle :size="18" color="var(--color-neutral-400)" />
      <span>Abonnement premium</span>
    </NuxtLink>
    <NuxtLink to="/profil" class="list-item">
      <PhArrowLeft :size="18" color="var(--color-neutral-400)" />
      <span>Retour à l'espace acheteur</span>
    </NuxtLink>
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
