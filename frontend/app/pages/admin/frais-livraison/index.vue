<script setup lang="ts">
import { PhPencilSimple, PhPlus, PhTrash } from '@phosphor-icons/vue'
import type { DeliveryFeeTierRead } from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const { apiFetch } = useApi()
const toast = useToastStore()

const { data: tiers, pending, refresh } = await useAsyncData(
  'admin-delivery-fee-tiers',
  () => apiFetch<DeliveryFeeTierRead[]>('/admin/delivery-fee-tiers'),
  { default: () => [], getCachedData: () => undefined },
)

const hasCatchAll = computed(() => tiers.value.some((t) => t.max_km === null))

// Un seul formulaire pour créer et modifier : editingId === null = création.
const dialogOpen = ref(false)
const editingId = ref<string | null>(null)
const form = ref<{ beyond: boolean; max_km: string; fee: string; label: string }>({
  beyond: false,
  max_km: '',
  fee: '',
  label: '',
})
const saving = ref(false)

function openCreate() {
  editingId.value = null
  form.value = { beyond: !hasCatchAll.value && tiers.value.length > 0, max_km: '', fee: '', label: '' }
  dialogOpen.value = true
}

function openEdit(tier: DeliveryFeeTierRead) {
  editingId.value = tier.id
  form.value = {
    beyond: tier.max_km === null,
    max_km: tier.max_km === null ? '' : String(tier.max_km),
    fee: String(tier.fee),
    label: tier.label ?? '',
  }
  dialogOpen.value = true
}

async function save() {
  const fee = Number(form.value.fee)
  const maxKm = form.value.beyond ? null : Number(form.value.max_km.replace(',', '.'))
  if (!Number.isInteger(fee) || fee < 0) {
    toast.error('Le tarif doit être un montant entier en GNF.')
    return
  }
  if (maxKm !== null && !(maxKm > 0)) {
    toast.error('La distance maximale doit être supérieure à 0.')
    return
  }
  saving.value = true
  try {
    const body = { max_km: maxKm, fee, label: form.value.label.trim() || null }
    if (editingId.value) {
      await apiFetch(`/admin/delivery-fee-tiers/${editingId.value}`, { method: 'PATCH', body })
    } else {
      await apiFetch('/admin/delivery-fee-tiers', { method: 'POST', body })
    }
    dialogOpen.value = false
    await refresh()
    toast.success('Palier enregistré.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible d’enregistrer ce palier.'))
  } finally {
    saving.value = false
  }
}

const tierToDelete = ref<DeliveryFeeTierRead | null>(null)
const deleting = ref(false)

async function confirmRemove() {
  const tier = tierToDelete.value
  if (!tier) return
  deleting.value = true
  try {
    await apiFetch(`/admin/delivery-fee-tiers/${tier.id}`, { method: 'DELETE' })
    tierToDelete.value = null
    await refresh()
    toast.success('Palier supprimé.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de supprimer ce palier.'))
  } finally {
    deleting.value = false
  }
}

function tierLabel(tier: DeliveryFeeTierRead, index: number): string {
  if (tier.max_km === null) return 'Au-delà, ou position inconnue'
  const previous = index > 0 ? tiers.value[index - 1]?.max_km : 0
  return `${previous} – ${tier.max_km} km`
}
</script>

<template>
  <div class="dashboard-shell">
    <div class="d-flex justify-space-between align-center mb-2">
      <h1 class="text-h6">Frais de livraison</h1>
      <v-btn color="primary" size="small" @click="openCreate">
        <PhPlus :size="16" class="mr-1" />
        Palier
      </v-btn>
    </div>
    <p class="text-muted mb-4" style="font-size: 12.5px">
      Tarif par colis (un colis par vendeur), selon la distance entre la boutique et l’adresse de livraison ou le point
      de retrait. Le palier « au-delà » s’applique aussi quand une position GPS manque. Sans aucun palier, la
      livraison est gratuite.
    </p>

    <CommonEmptyState v-if="!pending && tiers.length === 0" message="Aucun palier : la livraison est gratuite." />

    <v-card v-for="(tier, index) in tiers" :key="tier.id" class="mb-2 pa-3">
      <div class="d-flex justify-space-between align-center">
        <div>
          <div style="font-weight: 600">{{ tierLabel(tier, index) }}</div>
          <div v-if="tier.label" class="text-muted" style="font-size: 12.5px">{{ tier.label }}</div>
          <div class="text-muted" style="font-size: 12.5px">{{ formatGnf(tier.fee) }}</div>
        </div>
        <div class="d-flex ga-1">
          <v-btn icon variant="text" size="small" aria-label="Modifier" @click="openEdit(tier)">
            <PhPencilSimple :size="18" />
          </v-btn>
          <v-btn icon variant="text" size="small" color="error" aria-label="Supprimer" @click="tierToDelete = tier">
            <PhTrash :size="18" />
          </v-btn>
        </div>
      </div>
    </v-card>

    <v-dialog v-model="dialogOpen" max-width="360">
      <v-card class="pa-4">
        <div class="text-h6 mb-3">{{ editingId ? 'Modifier le palier' : 'Nouveau palier' }}</div>
        <v-switch v-model="form.beyond" label="Palier « au-delà »" color="primary" density="compact" hide-details />
        <v-text-field
          v-if="!form.beyond"
          v-model="form.max_km"
          label="Jusqu’à (km)"
          inputmode="decimal"
          class="mt-3"
          hide-details="auto"
        />
        <v-text-field v-model="form.fee" label="Tarif (GNF)" inputmode="numeric" class="mt-3" hide-details="auto" />
        <v-text-field
          v-model="form.label"
          label="Zone couverte (optionnel)"
          placeholder="Ex. Grand Conakry — Coyah, Dubréka"
          maxlength="100"
          class="mt-3"
          hide-details="auto"
        />
        <div class="d-flex ga-2 mt-4">
          <v-btn variant="outlined" class="flex-grow-1" @click="dialogOpen = false">Annuler</v-btn>
          <v-btn color="primary" class="flex-grow-1" :loading="saving" @click="save">Enregistrer</v-btn>
        </div>
      </v-card>
    </v-dialog>

    <v-dialog :model-value="!!tierToDelete" max-width="340" @update:model-value="tierToDelete = null">
      <v-card v-if="tierToDelete" class="pa-4">
        <div class="text-h6 mb-2">Supprimer ce palier ?</div>
        <p class="text-muted mb-4" style="font-size: 13px">
          {{ tierToDelete.max_km === null ? 'Palier « au-delà »' : `Jusqu’à ${tierToDelete.max_km} km` }} —
          {{ formatGnf(tierToDelete.fee) }}. Les commandes déjà passées gardent leurs frais ; les prochaines seront
          recalculées avec les paliers restants.
        </p>
        <div class="d-flex ga-2">
          <v-btn variant="outlined" class="flex-grow-1" @click="tierToDelete = null">Annuler</v-btn>
          <v-btn color="error" class="flex-grow-1" :loading="deleting" @click="confirmRemove">Supprimer</v-btn>
        </div>
      </v-card>
    </v-dialog>
  </div>
</template>
