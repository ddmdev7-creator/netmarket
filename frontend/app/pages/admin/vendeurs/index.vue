<script setup lang="ts">
import { PhEnvelope, PhPhone, PhStorefront, PhUser } from '@phosphor-icons/vue'
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

const search = ref('')
const visibleVendors = computed(() => {
  const query = search.value.trim().toLowerCase()
  if (!query) return vendors.value
  return vendors.value.filter((v) =>
    [v.shop_name, v.owner_full_name, v.owner_phone, v.owner_email]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
      .includes(query),
  )
})

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
  <div class="dashboard-shell">
    <h1 class="text-h6 mb-4">Vendeurs</h1>

    <v-btn-toggle v-model="tab" mandatory density="comfortable" divided class="mb-3 flex-wrap">
      <v-btn v-for="t in tabs" :key="t.value" :value="t.value" size="small">{{ t.label }}</v-btn>
    </v-btn-toggle>

    <v-text-field
      v-model="search"
      placeholder="Rechercher par boutique, nom, téléphone ou email…"
      density="compact"
      variant="outlined"
      hide-details
      clearable
      class="mb-4"
    />

    <CommonEmptyState v-if="!pending && vendors.length === 0" message="Aucune boutique dans cette catégorie." />
    <CommonEmptyState
      v-else-if="!pending && visibleVendors.length === 0"
      message="Aucune boutique ne correspond à cette recherche."
    />

    <div class="vendors-grid">
      <v-card v-for="vendor in visibleVendors" :key="vendor.id" class="vendor-card pa-3">
        <div class="d-flex justify-space-between align-start mb-1 ga-2">
          <div class="d-flex align-center ga-2">
            <div class="vendor-card__icon">
              <PhStorefront :size="16" />
            </div>
            <span class="vendor-card__name">{{ vendor.shop_name }}</span>
          </div>
          <v-chip :color="statusMeta[vendor.status].color" size="small" variant="tonal">
            {{ statusMeta[vendor.status].label }}
          </v-chip>
        </div>
        <div v-if="vendor.zone" class="text-muted mb-2 text-meta" style="padding-left: 32px">{{ vendor.zone }}</div>

        <div class="owner-block mb-3">
          <div class="owner-block__title">Compte lié</div>
          <div v-if="vendor.owner_full_name" class="d-flex align-center ga-2 text-meta">
            <PhUser :size="13" color="var(--color-neutral-500)" />
            <span>{{ vendor.owner_full_name }}</span>
          </div>
          <div class="d-flex align-center ga-2 text-meta mt-1">
            <PhPhone :size="13" color="var(--color-neutral-500)" />
            <span>{{ vendor.owner_phone ?? '—' }}</span>
          </div>
          <div v-if="vendor.owner_email" class="d-flex align-center ga-2 text-meta mt-1">
            <PhEnvelope :size="13" color="var(--color-neutral-500)" />
            <span class="owner-block__email">{{ vendor.owner_email }}</span>
          </div>
        </div>

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

        <div class="d-flex ga-2 mt-auto">
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
  </div>
</template>

<style scoped>
/* Comme .sub-order-grid (pages/vendeur/commandes) : une colonne sur mobile,
   puis une grille dès que l'écran a la place — une carte vendeur porte plus
   d'infos qu'une carte commande (compte lié, commission...), donc plafonnée
   à 3 colonnes plutôt que 4 pour rester lisible sur un très grand écran. */
.vendors-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 14px;
  align-items: stretch;
}

@media (min-width: 600px) {
  .vendors-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (min-width: 960px) {
  .vendors-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

.vendor-card {
  display: flex;
  flex-direction: column;
}

.vendor-card__icon {
  width: 26px;
  height: 26px;
  flex: none;
  border-radius: var(--radius-sm);
  background: var(--color-primary-800);
  color: var(--color-primary-100);
  display: flex;
  align-items: center;
  justify-content: center;
}

.vendor-card__name {
  font-weight: 700;
  font-size: 14px;
}

/* Sépare visuellement le compte utilisateur (qui se connecte) des
   informations propres à la boutique — fond légèrement teinté plutôt qu'un
   simple v-divider, pour que ce bloc se repère d'un coup d'œil sur une
   grille de plusieurs cartes. */
.owner-block {
  background: var(--color-neutral-800);
  border-radius: var(--radius-sm);
  padding: 8px 10px;
}

.owner-block__title {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-neutral-500);
  margin-bottom: 5px;
}

.owner-block__email {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
