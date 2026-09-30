<script setup lang="ts">
import { PhClock, PhHouse, PhMapPin, PhPackage, PhPencilSimple, PhPercent, PhPlus, PhStorefront, PhTable, PhTrash } from '@phosphor-icons/vue'
import type {
  DeliveryFeeTierCreate,
  DeliveryFeeTierRead,
  DeliveryFeeTierUpdate,
  DeliveryPricingSettings,
  DeliveryTierKind,
} from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const { apiFetch } = useApi()
const toast = useToastStore()

const { data: allTiers, pending, refresh } = await useAsyncData(
  'admin-delivery-fee-tiers',
  () => apiFetch<DeliveryFeeTierRead[]>('/admin/delivery-fee-tiers'),
  { default: () => [], getCachedData: hydrateThenRefetch },
)

// Deux grilles : domicile, et (facultative) point de retrait.
const kind = ref<DeliveryTierKind>('home')
const homeTiers = computed(() => allTiers.value.filter((t) => (t.kind ?? 'home') === 'home'))
const pickupTiers = computed(() => allTiers.value.filter((t) => t.kind === 'pickup'))
const tiers = computed(() => (kind.value === 'home' ? homeTiers.value : pickupTiers.value))

const hasCatchAll = computed(() => tiers.value.some((t) => t.max_km === null))
const hasDefault = computed(() => tiers.value.some((t) => t.is_default))

// --- Tarif en point de retrait -------------------------------------------------

const { data: pricing } = await useAsyncData(
  'admin-delivery-pricing',
  () => apiFetch<DeliveryPricingSettings>('/admin/delivery-fee-tiers/settings'),
  { getCachedData: hydrateThenRefetch },
)
const pricingForm = ref<{ mode: 'percent' | 'grid'; percent: string }>({ mode: 'percent', percent: '100' })
watch(
  pricing,
  (value) => {
    if (value) pricingForm.value = { mode: value.pickup_pricing_mode, percent: String(value.pickup_fee_percent) }
  },
  { immediate: true },
)
const pricingDirty = computed(
  () =>
    !!pricing.value &&
    (pricingForm.value.mode !== pricing.value.pickup_pricing_mode ||
      Number(pricingForm.value.percent) !== pricing.value.pickup_fee_percent),
)
const percentValue = computed(() => {
  const n = Number(pricingForm.value.percent)
  return Number.isFinite(n) ? n : 100
})
// Le pourcentage reste le repli de la grille dédiée tant qu'elle est vide.
const percentApplies = computed(() => pricingForm.value.mode === 'percent' || pickupTiers.value.length === 0)

function pickupFromHome(fee: number): number {
  return Math.round((fee * percentValue.value) / 100 / 100) * 100
}

const savingPricing = ref(false)
async function savePricing() {
  const percent = Number(pricingForm.value.percent)
  if (!Number.isInteger(percent) || percent < 0 || percent > 300) {
    toast.error('Le pourcentage doit être un entier entre 0 et 300.')
    return
  }
  savingPricing.value = true
  try {
    pricing.value = await apiFetch<DeliveryPricingSettings>('/admin/delivery-fee-tiers/settings', {
      method: 'PATCH',
      body: { pickup_pricing_mode: pricingForm.value.mode, pickup_fee_percent: percent },
    })
    toast.success('Tarif en point de retrait enregistré.')
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'enregistrer ce réglage."))
  } finally {
    savingPricing.value = false
  }
}

// Palier « par défaut » : tarif appliqué quand l'acheteur n'a pas pu donner sa
// position GPS (sinon c'est le palier « au-delà »).
const settingDefault = ref<string | null>(null)
async function toggleDefault(tier: DeliveryFeeTierRead) {
  settingDefault.value = tier.id
  try {
    await apiFetch(`/admin/delivery-fee-tiers/${tier.id}`, { method: 'PATCH', body: { is_default: !tier.is_default } })
    await refresh()
    toast.success(tier.is_default ? 'Le palier « au-delà » s’applique de nouveau sans position GPS.' : 'Tarif par défaut enregistré.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de modifier ce palier.'))
  } finally {
    settingDefault.value = null
  }
}

function tierRange(tier: DeliveryFeeTierRead, index: number): string {
  if (tier.max_km === null) return hasDefault.value ? 'Au-delà' : 'Au-delà, ou position inconnue'
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
  const tierKind = kind.value
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
      ...(editingId.value ? {} : { kind: tierKind }),
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
          {{ homeTiers.length }} palier{{ homeTiers.length > 1 ? 's' : '' }} à domicile ·
          {{ pricing?.pickup_pricing_mode === 'grid' && pickupTiers.length ? `${pickupTiers.length} en point de retrait` : `point de retrait à ${pricing?.pickup_fee_percent ?? 100} %` }}
        </p>
      </div>
      <v-btn v-if="kind === 'home' || pricingForm.mode === 'grid'" color="primary" @click="openCreate">
        <PhPlus :size="16" class="mr-1" />
        Palier
      </v-btn>
    </div>

    <div class="fl-tabs" role="tablist">
      <button type="button" role="tab" class="fl-tab" :class="{ 'fl-tab--on': kind === 'home' }" :aria-selected="kind === 'home'" @click="kind = 'home'">
        <PhHouse :size="16" /> À domicile
      </button>
      <button type="button" role="tab" class="fl-tab" :class="{ 'fl-tab--on': kind === 'pickup' }" :aria-selected="kind === 'pickup'" @click="kind = 'pickup'">
        <PhStorefront :size="16" /> Point de retrait
      </button>
    </div>

    <template v-if="kind === 'home'">
      <p class="text-muted fl-intro">
        Un palier fixe, pour une tranche de distance entre la boutique et l'adresse de livraison, à la fois le
        <strong>tarif</strong> du colis et le <strong>délai de trajet</strong> ajouté à la préparation du vendeur.
        Quand l'acheteur n'a pas pu donner sa position GPS, c'est le palier marqué <strong>« par défaut »</strong> qui
        s'applique (à défaut, le palier « au-delà »). Sans aucun palier, la livraison est gratuite et le délai retombe
        sur un jour de trajet par défaut.
      </p>
    </template>

    <template v-else>
      <p class="text-muted fl-intro">
        Un colis déposé en point de retrait est regroupé avec d'autres : il peut coûter moins cher qu'à domicile.
        Choisis comment le calculer. La distance est celle entre la boutique et le point choisi.
      </p>

      <div class="fl-modes">
        <label class="fl-mode" :class="{ 'fl-mode--on': pricingForm.mode === 'percent' }">
          <input v-model="pricingForm.mode" type="radio" value="percent" class="fl-mode__radio" />
          <span class="fl-mode__icon"><PhPercent :size="18" /></span>
          <span class="fl-mode__body">
            <span class="fl-mode__title">Pourcentage du tarif domicile</span>
            <span class="fl-mode__text">Même grille qu'à domicile, ajustée d'un pourcentage. Simple à tenir à jour.</span>
          </span>
        </label>
        <label class="fl-mode" :class="{ 'fl-mode--on': pricingForm.mode === 'grid' }">
          <input v-model="pricingForm.mode" type="radio" value="grid" class="fl-mode__radio" />
          <span class="fl-mode__icon"><PhTable :size="18" /></span>
          <span class="fl-mode__body">
            <span class="fl-mode__title">Grille dédiée</span>
            <span class="fl-mode__text">Tes propres paliers de distance pour les points de retrait. Tant qu'elle est vide, le pourcentage s'applique.</span>
          </span>
        </label>
      </div>

      <div class="fl-percent">
        <div class="fl-percent__field">
          <label class="field-label">{{ pricingForm.mode === 'grid' ? 'Pourcentage de repli' : 'Pourcentage du tarif domicile' }}</label>
          <v-text-field v-model="pricingForm.percent" inputmode="numeric" suffix="%" density="compact" hide-details="auto" style="max-width: 140px" />
          <p class="text-muted fl-form-hint">100 % = même prix qu'à domicile · 0 % = gratuit pour l'acheteur.</p>
        </div>
        <div v-if="percentApplies && homeTiers.length" class="fl-preview">
          <div class="fl-preview__head">Aperçu</div>
          <div v-for="(tier, index) in homeTiers" :key="tier.id" class="fl-preview__row">
            <span>{{ tier.max_km === null ? 'Au-delà' : `${index > 0 ? homeTiers[index - 1]?.max_km : 0} – ${tier.max_km} km` }}</span>
            <span class="text-muted"><s v-if="percentValue !== 100">{{ formatGnf(tier.fee) }}</s></span>
            <strong>{{ formatGnf(pickupFromHome(tier.fee)) }}</strong>
          </div>
        </div>
      </div>

      <div class="d-flex justify-end mb-5">
        <v-btn color="primary" :disabled="!pricingDirty" :loading="savingPricing" @click="savePricing">Enregistrer le réglage</v-btn>
      </div>
    </template>

    <template v-if="kind === 'home' || pricingForm.mode === 'grid'">
    <CommonEmptyState
      v-if="!pending && tiers.length === 0"
      :message="kind === 'home' ? 'Aucun palier : la livraison est gratuite, avec un délai de trajet par défaut.' : 'Grille vide : le pourcentage ci-dessus s’applique. Ajoute un palier pour la remplacer.'"
      :icon="PhPackage"
    />

    <div v-if="tiers.length" class="fl-list">
      <div v-for="(tier, index) in tiers" :key="tier.id" class="fl-row" :class="{ 'fl-row--catchall': tier.max_km === null }">
        <div class="fl-row__range">
          <PhPackage :size="18" class="fl-row__icon" />
          <div>
            <div class="fl-row__km">{{ tierRange(tier, index) }}</div>
            <div v-if="tier.label" class="text-muted fl-row__label">{{ tier.label }}</div>
            <span v-if="tier.is_default" class="fl-default"><PhMapPin :size="12" weight="fill" /> Par défaut sans GPS</span>
          </div>
        </div>

        <div class="fl-row__fee">{{ formatGnf(tier.fee) }}</div>

        <div class="fl-row__transit">
          <PhClock :size="15" />
          {{ transitLabel(tier.transit_days) }}
        </div>

        <div class="fl-row__actions">
          <v-btn
            icon
            variant="text"
            size="small"
            :color="tier.is_default ? 'success' : undefined"
            :loading="settingDefault === tier.id"
            :title="tier.is_default ? 'Retirer le tarif par défaut' : 'Appliquer ce tarif quand la position GPS est inconnue'"
            :aria-label="tier.is_default ? 'Retirer le tarif par défaut' : 'Définir comme tarif par défaut sans GPS'"
            @click="toggleDefault(tier)"
          >
            <PhMapPin :size="18" :weight="tier.is_default ? 'fill' : 'regular'" />
          </v-btn>
          <v-btn icon variant="text" size="small" aria-label="Modifier" @click="openEdit(tier)">
            <PhPencilSimple :size="18" />
          </v-btn>
          <v-btn icon variant="text" size="small" color="error" aria-label="Supprimer" @click="tierToDelete = tier">
            <PhTrash :size="18" />
          </v-btn>
        </div>
      </div>
    </div>
    </template>

    <v-dialog v-model="dialogOpen" max-width="380">
      <v-card class="pa-5">
        <div class="text-h6 mb-1">{{ editingId ? 'Modifier le palier' : 'Nouveau palier' }}</div>
        <p class="text-muted fl-form-hint mb-4">{{ kind === 'home' ? 'Grille à domicile' : 'Grille des points de retrait' }}</p>

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
.fl-tabs {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  margin-bottom: 14px;
  border-radius: 12px;
  background: var(--color-neutral-800);
}

.fl-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border: none;
  border-radius: 9px;
  background: none;
  color: var(--color-neutral-400);
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
}

.fl-tab--on {
  background: var(--color-neutral-900);
  color: var(--color-primary);
  box-shadow: var(--shadow-sm);
}

.fl-modes {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 10px;
  max-width: 820px;
  margin-bottom: 14px;
}

.fl-mode {
  position: relative;
  display: flex;
  gap: 12px;
  padding: 14px;
  border-radius: var(--radius-lg);
  border: 1.5px solid var(--color-divider);
  background: var(--color-neutral-900);
  cursor: pointer;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.fl-mode--on {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-primary) 14%, transparent);
}

.fl-mode__radio {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.fl-mode__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  border-radius: 10px;
  background: var(--color-primary-100);
  color: var(--color-primary);
}

.fl-mode__body {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.fl-mode__title {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-neutral-100);
}

.fl-mode__text {
  font-size: 12.5px;
  line-height: 1.45;
  color: var(--color-neutral-400);
}

.fl-percent {
  display: flex;
  flex-wrap: wrap;
  gap: 16px 32px;
  align-items: flex-start;
  max-width: 820px;
  margin-bottom: 12px;
}

.fl-percent__field {
  flex: 1 1 220px;
}

.fl-preview {
  flex: 1 1 300px;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-divider);
  background: var(--color-neutral-900);
  font-size: 13px;
}

.fl-preview__head {
  margin-bottom: 6px;
  font-size: 11.5px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-neutral-500);
}

.fl-preview__row {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 12px;
  padding: 4px 0;
}

.fl-default {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  background: hsl(150 70% var(--tint-bg));
  color: hsl(150 55% var(--tint-fg));
  font-size: 11.5px;
  font-weight: 700;
}

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
