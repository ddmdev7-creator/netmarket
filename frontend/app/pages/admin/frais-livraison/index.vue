<script setup lang="ts">
import { PhClock, PhPackage, PhPencilSimple, PhPlus, PhTrash } from '@phosphor-icons/vue'
import type { DeliveryFeeTierCreate, DeliveryFeeTierRead, DeliveryFeeTierUpdate } from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const { apiFetch } = useApi()
const toast = useToastStore()

const { data: tiers, pending, refresh } = await useAsyncData(
  'admin-delivery-fee-tiers',
  () => apiFetch<DeliveryFeeTierRead[]>('/admin/delivery-fee-tiers'),
  { default: () => [], getCachedData: () => undefined },
)

const hasCatchAll = computed(() => tiers.value.some((t) => t.max_km === null))

function tierRange(tier: DeliveryFeeTierRead, index: number): string {
  if (tier.max_km === null) return 'Au-delà, ou position inconnue'
  const previous = index > 0 ? tiers.value[index - 1]?.max_km : 0
  return `${previous} – ${tier.max_km} km`
}

function transitLabel(days: number): string {
  if (days === 0) return "Livré le jour même de l'expédition"
  return `+${days} jour${days > 1 ? 's' : ''} de trajet`
}

// --- Création / modification -------------------------------------------------

const dialogOpen = ref(false)
const editingId = ref<string | null>(null)
const form = ref<{ beyond: boolean; max_km: string; fee: string; transit_days: string; label: string }>({
  beyond: false,
  max_km: '',
  fee: '',
  transit_days: '1',
  label: '',
})
const saving = ref(false)

function openCreate() {
  editingId.value = null
  form.value = {
    beyond: !hasCatchAll.value && tiers.value.length > 0,
    max_km: '',
    fee: '',
    transit_days: '1',
    label: '',
  }
  dialogOpen.value = true
}

function openEdit(tier: DeliveryFeeTierRead) {
  editingId.value = tier.id
  form.value = {
    beyond: tier.max_km === null,
    max_km: tier.max_km === null ? '' : String(tier.max_km),
    fee: String(tier.fee),
    transit_days: String(tier.transit_days),
    label: tier.label ?? '',
  }
  dialogOpen.value = true
}

async function save() {
  const fee = Number(form.value.fee)
  const transitDays = Number(form.value.transit_days)
  const maxKm = form.value.beyond ? null : Number(form.value.max_km.replace(',', '.'))
  if (!Number.isInteger(fee) || fee < 0) {
    toast.error('Le tarif doit être un montant entier en GNF.')
    return
  }
  if (maxKm !== null && !(maxKm > 0)) {
    toast.error('La distance maximale doit être supérieure à 0.')
    return
  }
  if (!Number.isInteger(transitDays) || transitDays < 0) {
    toast.error('Le délai de trajet doit être un nombre de jours entier, positif ou nul.')
    return
  }
  saving.value = true
  try {
    const body: DeliveryFeeTierCreate | DeliveryFeeTierUpdate = {
      max_km: maxKm,
      fee,
      transit_days: transitDays,
      label: form.value.label.trim() || null,
    }
    if (editingId.value) {
      await apiFetch(`/admin/delivery-fee-tiers/${editingId.value}`, { method: 'PATCH', body })
    } else {
      await apiFetch('/admin/delivery-fee-tiers', { method: 'POST', body })
    }
    dialogOpen.value = false
    await refresh()
    toast.success('Palier enregistré.')
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'enregistrer ce palier."))
  } finally {
    saving.value = false
  }
}

// --- Suppression ------------------------------------------------------------

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
</script>

<template>
  <div class="dashboard-shell">
    <div class="fl-header">
      <div>
        <h1 class="text-h6">Frais de livraison</h1>
        <p class="text-muted fl-header__sub">
          {{ tiers.length }} palier{{ tiers.length > 1 ? 's' : '' }} de distance
        </p>
      </div>
      <v-btn color="primary" @click="openCreate">
        <PhPlus :size="16" class="mr-1" />
        Palier
      </v-btn>
    </div>

    <p class="text-muted fl-intro">
      Un palier fixe, pour une tranche de distance entre la boutique et l'adresse de livraison (ou le point de
      retrait), à la fois le <strong>tarif</strong> du colis et le <strong>délai de trajet</strong> ajouté à la
      préparation du vendeur. Le palier « au-delà » s'applique aussi quand une position GPS manque. Sans aucun
      palier, la livraison est gratuite et le délai retombe sur un jour de trajet par défaut.
    </p>

    <CommonEmptyState
      v-if="!pending && tiers.length === 0"
      message="Aucun palier : la livraison est gratuite, avec un délai de trajet par défaut."
      :icon="PhPackage"
    />

    <div v-if="tiers.length" class="fl-list">
      <div v-for="(tier, index) in tiers" :key="tier.id" class="fl-row" :class="{ 'fl-row--catchall': tier.max_km === null }">
        <div class="fl-row__range">
          <PhPackage :size="18" class="fl-row__icon" />
          <div>
            <div class="fl-row__km">{{ tierRange(tier, index) }}</div>
            <div v-if="tier.label" class="text-muted fl-row__label">{{ tier.label }}</div>
          </div>
        </div>

        <div class="fl-row__fee">{{ formatGnf(tier.fee) }}</div>

        <div class="fl-row__transit">
          <PhClock :size="15" />
          {{ transitLabel(tier.transit_days) }}
        </div>

        <div class="fl-row__actions">
          <v-btn icon variant="text" size="small" aria-label="Modifier" @click="openEdit(tier)">
            <PhPencilSimple :size="18" />
          </v-btn>
          <v-btn icon variant="text" size="small" color="error" aria-label="Supprimer" @click="tierToDelete = tier">
            <PhTrash :size="18" />
          </v-btn>
        </div>
      </div>
    </div>

    <v-dialog v-model="dialogOpen" max-width="380">
      <v-card class="pa-5">
        <div class="text-h6 mb-4">{{ editingId ? 'Modifier le palier' : 'Nouveau palier' }}</div>

        <v-switch v-model="form.beyond" label="Palier « au-delà »" color="primary" density="compact" hide-details />
        <v-text-field
          v-if="!form.beyond"
          v-model="form.max_km"
          label="Jusqu'à (km)"
          inputmode="decimal"
          class="mt-3"
          hide-details="auto"
        />

        <v-text-field v-model="form.fee" label="Tarif (GNF)" inputmode="numeric" class="mt-3" hide-details="auto" />

        <label class="field-label mt-3 d-block">Délai de trajet ajouté à la préparation</label>
        <v-text-field
          v-model="form.transit_days"
          inputmode="numeric"
          suffix="jour(s)"
          hide-details="auto"
        />
        <p class="text-muted fl-form-hint">
          Ex : 0 pour une livraison le jour même de l'expédition, 1 ou plus pour un trajet plus long.
        </p>

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

    <v-dialog :model-value="!!tierToDelete" max-width="360" @update:model-value="(v) => !v && (tierToDelete = null)">
      <v-card v-if="tierToDelete" class="pa-5">
        <div class="text-h6 mb-2">Supprimer ce palier ?</div>
        <p class="text-muted mb-4" style="font-size: 13px">
          {{ tierToDelete.max_km === null ? 'Palier « au-delà »' : `Jusqu'à ${tierToDelete.max_km} km` }} —
          {{ formatGnf(tierToDelete.fee) }}, {{ transitLabel(tierToDelete.transit_days).toLowerCase() }}. Les
          commandes déjà passées gardent leur tarif et leur délai figés ; les prochaines seront recalculées avec les
          paliers restants.
        </p>
        <div class="d-flex ga-2">
          <v-btn variant="outlined" class="flex-grow-1" @click="tierToDelete = null">Annuler</v-btn>
          <v-btn color="error" class="flex-grow-1" :loading="deleting" @click="confirmRemove">Supprimer</v-btn>
        </div>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.fl-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.fl-header__sub {
  margin: 2px 0 0;
  font-size: 12.5px;
}

.fl-intro {
  font-size: 12.5px;
  max-width: 680px;
  margin: 0 0 16px;
  line-height: 1.5;
}

.fl-list {
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

.fl-row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--color-divider);
  flex-wrap: wrap;
}

.fl-row:last-child {
  border-bottom: none;
}

.fl-row:hover {
  background: var(--color-neutral-800);
}

.fl-row--catchall {
  background: color-mix(in srgb, var(--color-warning, #e0822e) 5%, var(--color-neutral-900));
}

.fl-row__range {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 180px;
}

.fl-row__icon {
  color: var(--color-primary);
  flex-shrink: 0;
}

.fl-row__km {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-neutral-200);
}

.fl-row__label {
  font-size: 11.5px;
  margin-top: 1px;
}

.fl-row__fee {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--color-neutral-200);
  min-width: 110px;
}

.fl-row__transit {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12.5px;
  color: var(--color-neutral-400);
  min-width: 160px;
}

.fl-row__actions {
  display: flex;
  gap: 2px;
  margin-left: auto;
  flex-shrink: 0;
}

.fl-form-hint {
  font-size: 11.5px;
  margin: 4px 0 0;
}
</style>
