<script setup lang="ts">
import type { VendorAdminUpdate, VendorRead, VendorStatus } from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const { apiFetch } = useApi()
const toast = useToastStore()

const tab = ref<VendorStatus>('pending')
const tabs: { value: VendorStatus; label: string }[] = [
  { value: 'pending', label: 'En attente' },
  { value: 'approved', label: 'Approuvées' },
  { value: 'rejected', label: 'Rejetées' },
  { value: 'suspended', label: 'Suspendues' },
]

const { data: vendors, pending, refresh } = await useAsyncData(
  'admin-vendors',
  () => apiFetch<VendorRead[]>('/admin/vendors', { query: { status: tab.value } }),
  { default: () => [], getCachedData: () => undefined },
)
watch(tab, () => refresh())

const statusMeta: Record<VendorStatus, { label: string; color: string }> = {
  pending: { label: 'En attente', color: 'warning' },
  approved: { label: 'Approuvée', color: 'success' },
  rejected: { label: 'Rejetée', color: 'error' },
  suspended: { label: 'Suspendue', color: 'error' },
}

// La liste courante ne montre que le statut de l'onglet actif : après une
// action on la retire localement plutôt que de la re-classer, pour ne pas
// devoir dupliquer la logique de filtrage côté client.
const updatingId = ref<string | null>(null)
const commissionDrafts = ref<Record<string, number>>({})

function commissionFor(vendor: VendorRead) {
  return commissionDrafts.value[vendor.id] ?? vendor.commission_rate
}

async function update(vendor: VendorRead, payload: VendorAdminUpdate) {
  updatingId.value = vendor.id
  try {
    await apiFetch<VendorRead>(`/admin/vendors/${vendor.id}`, { method: 'PATCH', body: payload })
    if (payload.status && payload.status !== tab.value) {
      vendors.value = vendors.value.filter((v) => v.id !== vendor.id)
    } else {
      await refresh()
    }
    toast.success('Boutique mise à jour.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de mettre à jour cette boutique.'))
  } finally {
    updatingId.value = null
  }
}
</script>

<template>
  <div class="admin-shell">
    <h1 class="text-h6 mb-4">Vendeurs</h1>

    <v-btn-toggle v-model="tab" mandatory density="comfortable" divided class="mb-4 flex-wrap">
      <v-btn v-for="t in tabs" :key="t.value" :value="t.value" size="small">{{ t.label }}</v-btn>
    </v-btn-toggle>

    <CommonEmptyState v-if="!pending && vendors.length === 0" message="Aucune boutique dans cette catégorie." />

    <v-card v-for="vendor in vendors" :key="vendor.id" class="mb-3 pa-3">
      <div class="d-flex justify-space-between align-center mb-1">
        <span style="font-weight: 600">{{ vendor.shop_name }}</span>
        <v-chip :color="statusMeta[vendor.status].color" size="small" variant="tonal">
          {{ statusMeta[vendor.status].label }}
        </v-chip>
      </div>
      <div v-if="vendor.zone" class="text-muted mb-3" style="font-size: 12.5px">{{ vendor.zone }}</div>

      <div class="d-flex align-center ga-2 mb-3">
        <v-text-field
          :model-value="commissionFor(vendor)"
          @update:model-value="(v) => (commissionDrafts[vendor.id] = Number(v))"
          type="number"
          label="Commission (%)"
          density="compact"
          variant="outlined"
          min="0"
          max="100"
          hide-details
          style="max-width: 140px"
        />
        <v-btn
          size="small"
          variant="outlined"
          :loading="updatingId === vendor.id"
          :disabled="commissionFor(vendor) === vendor.commission_rate"
          @click="update(vendor, { commission_rate: commissionFor(vendor) })"
        >
          Enregistrer
        </v-btn>
      </div>

      <div class="d-flex ga-2">
        <template v-if="vendor.status === 'pending'">
          <v-btn color="primary" size="small" class="flex-grow-1" :loading="updatingId === vendor.id" @click="update(vendor, { status: 'approved' })">
            Approuver
          </v-btn>
          <v-btn color="error" variant="outlined" size="small" class="flex-grow-1" :loading="updatingId === vendor.id" @click="update(vendor, { status: 'rejected' })">
            Rejeter
          </v-btn>
        </template>
        <v-btn v-else-if="vendor.status === 'approved'" color="error" variant="outlined" size="small" class="flex-grow-1" :loading="updatingId === vendor.id" @click="update(vendor, { status: 'suspended' })">
          Suspendre
        </v-btn>
        <v-btn v-else color="primary" size="small" class="flex-grow-1" :loading="updatingId === vendor.id" @click="update(vendor, { status: 'approved' })">
          Réactiver
        </v-btn>
      </div>
    </v-card>
  </div>
</template>
