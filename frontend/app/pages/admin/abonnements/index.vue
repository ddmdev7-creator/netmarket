<script setup lang="ts">
import {
  PhCalendarBlank,
  PhCrown,
  PhEnvelopeSimple,
  PhGear,
  PhGift,
  PhListBullets,
  PhPackage,
  PhHash,
  PhIdentificationCard,
  PhMagnifyingGlass,
  PhMapPin,
  PhPhone,
  PhSparkle,
  PhStorefront,
} from '@phosphor-icons/vue'
import type { AdminSubscriptionRead, SubscriptionPlanRead, SubscriptionStatus, VendorRead } from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const { apiFetch } = useApi()
const toast = useToastStore()

// Trois vues : les abonnements, les formules (quotas), les réglages (essai auto, grâce).
const view = ref<'list' | 'plans' | 'settings'>('list')
const tab = ref<SubscriptionStatus>('pending')
const tabs: { value: SubscriptionStatus; label: string }[] = [
  { value: 'pending', label: 'En attente' },
  { value: 'active', label: 'Actifs' },
  { value: 'expired', label: 'Expirés' },
  { value: 'cancelled', label: 'Annulés' },
]

const { data: subscriptions, pending, refresh } = await useAsyncData(
  'admin-subscriptions',
  () => apiFetch<AdminSubscriptionRead[]>('/admin/subscriptions', { query: { status: tab.value } }),
  { default: () => [], getCachedData: hydrateThenRefetch },
)
watch(tab, () => refresh())

const statusMeta: Record<SubscriptionStatus, { label: string; tone: string }> = {
  pending: { label: 'En attente', tone: 'warning' },
  active: { label: 'Actif', tone: 'success' },
  expired: { label: 'Expiré', tone: 'error' },
  cancelled: { label: 'Annulé', tone: 'error' },
}

const search = ref<string | null>('')
function normalize(v: string) {
  return v.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
}
const visible = computed(() => {
  const term = normalize((search.value ?? '').trim())
  if (!term) return subscriptions.value
  return subscriptions.value.filter((s) =>
    normalize([s.shop_name, s.owner_full_name ?? '', s.owner_phone ?? '', s.owner_email ?? '', s.payment_reference ?? '', s.plan.name].join(' ')).includes(term),
  )
})

// Recette du lot affiché (utile sur l'onglet « Actifs »).
const revenue = computed(() => subscriptions.value.reduce((sum, s) => sum + s.plan.price_gnf, 0))

// Même logique que admin/vendeurs : la liste courante ne montre que l'onglet
// actif, donc après une action on la retire localement plutôt que de la
// re-classer.
const updatingId = ref<string | null>(null)

async function act(subscription: AdminSubscriptionRead, action: 'confirm' | 'cancel', body?: object) {
  updatingId.value = subscription.id
  try {
    await apiFetch(`/admin/subscriptions/${subscription.id}/${action}`, { method: 'POST', body })
    subscriptions.value = subscriptions.value.filter((s) => s.id !== subscription.id)
    toast.success(action === 'confirm' ? 'Abonnement confirmé.' : 'Abonnement annulé.')
    return true
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de mettre à jour cet abonnement.'))
    return false
  } finally {
    updatingId.value = null
  }
}

// --- Actions sur un abonnement actif ------------------------------------------------

const { data: allPlans } = await useAsyncData(
  'admin-subscription-plans',
  () => apiFetch<SubscriptionPlanRead[]>('/admin/subscription-plans'),
  { default: () => [], getCachedData: hydrateThenRefetch },
)
const sellablePlans = computed(() => allPlans.value.filter((p) => !p.is_free))

type Dialog = { kind: 'extend' | 'plan' | 'end'; sub: AdminSubscriptionRead } | null
const dialog = ref<Dialog>(null)
const extendDays = ref('30')
const newPlanId = ref<string | null>(null)
const endReason = ref('')
const dialogBusy = ref(false)

function openDialog(kind: 'extend' | 'plan' | 'end', sub: AdminSubscriptionRead) {
  extendDays.value = '30'
  newPlanId.value = sub.plan.id
  endReason.value = ''
  dialog.value = { kind, sub }
}

async function submitDialog() {
  const d = dialog.value
  if (!d) return
  dialogBusy.value = true
  try {
    if (d.kind === 'end') {
      if (await act(d.sub, 'cancel', { reason: endReason.value.trim() || null })) dialog.value = null
      return
    }
    const updated =
      d.kind === 'extend'
        ? await apiFetch<AdminSubscriptionRead>(`/admin/subscriptions/${d.sub.id}/extend`, {
            method: 'POST',
            body: { days: Math.round(Number(extendDays.value)) },
          })
        : await apiFetch<AdminSubscriptionRead>(`/admin/subscriptions/${d.sub.id}/change-plan`, {
            method: 'POST',
            body: { plan_id: newPlanId.value },
          })
    Object.assign(d.sub, { expires_at: updated.expires_at, plan: updated.plan })
    toast.success(d.kind === 'extend' ? 'Abonnement prolongé.' : 'Formule modifiée.')
    dialog.value = null
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de mettre à jour cet abonnement.'))
  } finally {
    dialogBusy.value = false
  }
}

// --- Offrir un essai -----------------------------------------------------------------

const trialOpen = ref(false)
const trialForm = ref({ vendor_id: null as string | null, plan_id: null as string | null, days: '14' })
const { data: vendors, execute: loadVendors } = useAsyncData(
  'admin-trial-vendors',
  () => apiFetch<VendorRead[]>('/admin/vendors', { query: { status: 'approved' } }),
  { default: () => [], immediate: false },
)
function openTrial() {
  trialForm.value = { vendor_id: null, plan_id: sellablePlans.value[0]?.id ?? null, days: '14' }
  trialOpen.value = true
  if (!vendors.value.length) loadVendors()
}
const grantingTrial = ref(false)
async function grantTrial() {
  const f = trialForm.value
  if (!f.vendor_id || !f.plan_id) {
    toast.error('Choisissez une boutique et une formule.')
    return
  }
  grantingTrial.value = true
  try {
    await apiFetch('/admin/subscriptions/trials', {
      method: 'POST',
      body: { vendor_id: f.vendor_id, plan_id: f.plan_id, days: Math.round(Number(f.days)) },
    })
    trialOpen.value = false
    toast.success('Essai offert — le vendeur est prévenu.')
    if (tab.value === 'active') await refresh()
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'offrir cet essai."))
  } finally {
    grantingTrial.value = false
  }
}

function periodPercent(s: AdminSubscriptionRead): number | null {
  if (s.status !== 'active' || !s.started_at || !s.expires_at) return null
  const start = new Date(s.started_at).getTime()
  const end = new Date(s.expires_at).getTime()
  return Math.min(100, Math.max(0, ((Date.now() - start) / (end - start)) * 100))
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'
}

function daysLeft(s: AdminSubscriptionRead) {
  if (s.status !== 'active' || !s.expires_at) return null
  return Math.max(0, Math.ceil((new Date(s.expires_at).getTime() - Date.now()) / 86_400_000))
}

function initials(s: AdminSubscriptionRead) {
  return s.shop_name.split(/\s+/).filter(Boolean).map((w) => w[0]).join('').slice(0, 2).toUpperCase() || 'B'
}
</script>

<template>
  <div class="dashboard-shell">
    <div class="d-flex justify-space-between align-center flex-wrap ga-2 mb-4">
      <h1 class="text-h6 mb-0">Abonnements vendeurs</h1>
      <div class="d-flex align-center ga-2 flex-wrap">
        <span v-if="view === 'list' && subscriptions.length" class="pf-tag pf-tag--primary">
          {{ subscriptions.length }} abonnement{{ subscriptions.length > 1 ? 's' : '' }} · {{ formatGnf(revenue) }}
        </span>
        <v-btn color="primary" variant="tonal" @click="openTrial"><PhGift :size="16" class="mr-1" /> Offrir un essai</v-btn>
      </div>
    </div>

    <div class="view-tabs mb-4" role="tablist">
      <button type="button" class="view-tab" :class="{ 'view-tab--on': view === 'list' }" @click="view = 'list'">
        <PhListBullets :size="16" /> Abonnements
      </button>
      <button type="button" class="view-tab" :class="{ 'view-tab--on': view === 'plans' }" @click="view = 'plans'">
        <PhCrown :size="16" /> Formules
      </button>
      <button type="button" class="view-tab" :class="{ 'view-tab--on': view === 'settings' }" @click="view = 'settings'">
        <PhGear :size="16" /> Réglages
      </button>
    </div>

    <AdminSubscriptionPlansPanel v-if="view === 'plans'" />
    <AdminSubscriptionSettingsPanel v-else-if="view === 'settings'" />

    <template v-else>
    <div class="sub-toolbar mb-4">
      <v-btn-toggle v-model="tab" mandatory density="comfortable" divided class="flex-wrap">
        <v-btn v-for="t in tabs" :key="t.value" :value="t.value" size="small">{{ t.label }}</v-btn>
      </v-btn-toggle>
      <v-text-field
        v-if="subscriptions.length"
        v-model="search"
        placeholder="Boutique, vendeur, téléphone, référence…"
        density="compact"
        variant="outlined"
        hide-details
        clearable
        class="sub-search"
      >
        <template #prepend-inner><PhMagnifyingGlass :size="16" color="var(--color-neutral-500)" /></template>
      </v-text-field>
    </div>

    <CommonEmptyState
      v-if="!pending && subscriptions.length === 0"
      :icon="PhSparkle"
      :hue="260"
      :title="tab === 'pending' ? 'Aucune demande en attente' : 'Aucun abonnement'"
      :message="tab === 'pending' ? 'Les demandes d’abonnement des vendeurs apparaîtront ici. Consultez l’onglet Actifs pour les abonnements en cours.' : 'Aucun abonnement dans cette catégorie.'"
    />
    <CommonEmptyState v-else-if="!pending && !visible.length" message="Aucun abonnement ne correspond à cette recherche." />

    <div class="sub-grid">
      <article v-for="s in visible" :key="s.id" class="sub-card">
        <header class="sub-card__head">
          <span class="sub-card__logo">{{ initials(s) }}</span>
          <div class="sub-card__shop">
            <strong><PhStorefront :size="14" /> {{ s.shop_name || 'Boutique' }}</strong>
            <small v-if="s.vendor_zone"><PhMapPin :size="12" /> {{ s.vendor_zone }}</small>
          </div>
          <span v-if="s.is_trial" class="pf-tag trial-tag"><PhGift :size="12" weight="fill" /> Essai</span>
          <span class="pf-tag" :class="`pf-tag--${statusMeta[s.status].tone}`">{{ statusMeta[s.status].label }}</span>
        </header>

        <div class="sub-card__plan">
          <span><PhSparkle :size="15" weight="fill" /> {{ s.plan.name }}</span>
          <strong>{{ s.is_trial ? 'Offert' : formatGnf(s.plan.price_gnf) }}</strong>
          <small>{{ s.plan.duration_days }} jours</small>
        </div>

        <div v-if="periodPercent(s) !== null" class="sub-card__time">
          <div class="sub-card__bar" :class="{ 'is-soon': (daysLeft(s) ?? 99) <= 7 }"><span :style="{ width: `${periodPercent(s)}%` }" /></div>
          <div class="sub-card__quota">
            <span><PhPackage :size="13" /> {{ s.products_used }}{{ s.plan.max_products !== null ? ` / ${s.plan.max_products}` : '' }} produits en vente</span>
            <span>{{ daysLeft(s) }} j restants</span>
          </div>
        </div>

        <dl class="pf-kv sub-card__kv">
          <dt>Vendeur</dt>
          <dd>
            <NuxtLink v-if="s.owner_user_id" :to="`/admin/utilisateurs/${s.owner_user_id}`">{{ s.owner_full_name ?? s.owner_phone ?? '—' }}</NuxtLink>
            <template v-else>—</template>
          </dd>
          <template v-if="s.owner_phone">
            <dt><PhPhone :size="13" /> Téléphone</dt>
            <dd><a :href="`tel:${s.owner_phone}`">{{ s.owner_phone }}</a></dd>
          </template>
          <template v-if="s.owner_email">
            <dt><PhEnvelopeSimple :size="13" /> E-mail</dt>
            <dd>{{ s.owner_email }}</dd>
          </template>
          <dt><PhCalendarBlank :size="13" /> Demandé le</dt>
          <dd>{{ formatDate(s.created_at) }}</dd>
          <template v-if="s.started_at">
            <dt>Période</dt>
            <dd>
              {{ formatDate(s.started_at) }} → {{ formatDate(s.expires_at) }}
            </dd>
          </template>
          <dt><PhHash :size="13" /> Référence</dt>
          <dd class="sub-card__ref">{{ s.payment_reference ?? 'Aucune' }}</dd>
        </dl>

        <div class="sub-card__actions">
          <v-btn v-if="s.owner_user_id" :to="`/admin/utilisateurs/${s.owner_user_id}`" variant="tonal" color="primary" size="small">
            <PhIdentificationCard :size="15" class="mr-1" /> Fiche vendeur
          </v-btn>
          <template v-if="s.status === 'pending'">
            <v-btn color="primary" size="small" class="flex-grow-1" :loading="updatingId === s.id" @click="act(s, 'confirm')">Confirmer le paiement</v-btn>
            <v-btn color="error" variant="outlined" size="small" :loading="updatingId === s.id" @click="act(s, 'cancel')">Annuler</v-btn>
          </template>
          <template v-else-if="s.status === 'active'">
            <v-btn variant="outlined" size="small" @click="openDialog('extend', s)">Prolonger</v-btn>
            <v-btn variant="outlined" size="small" @click="openDialog('plan', s)">Changer de formule</v-btn>
            <v-btn color="error" variant="text" size="small" :loading="updatingId === s.id" @click="openDialog('end', s)">Mettre fin</v-btn>
          </template>
        </div>
      </article>
    </div>
    </template>

    <v-dialog :model-value="!!dialog" max-width="420" @update:model-value="(v) => !v && (dialog = null)">
      <v-card v-if="dialog" class="pa-5">
        <div class="text-h6 mb-1">
          {{ dialog.kind === 'extend' ? 'Prolonger' : dialog.kind === 'plan' ? 'Changer de formule' : "Mettre fin à l'abonnement" }}
        </div>
        <p class="text-muted mb-4" style="font-size: 13px">{{ dialog.sub.shop_name }} · {{ dialog.sub.plan.name }} jusqu'au {{ formatDate(dialog.sub.expires_at) }}</p>
        <v-text-field v-if="dialog.kind === 'extend'" v-model="extendDays" label="Jours offerts en plus" suffix="jours" inputmode="numeric" hide-details />
        <v-select v-else-if="dialog.kind === 'plan'" v-model="newPlanId" :items="sellablePlans" item-title="name" item-value="id" label="Nouvelle formule" hide-details />
        <template v-else>
          <v-alert type="warning" variant="tonal" density="compact" class="mb-3" style="font-size: 13px">
            Effet immédiat, sans remboursement. Le vendeur repasse à la formule Gratuit et est prévenu.
          </v-alert>
          <v-text-field v-model="endReason" label="Motif (communiqué au vendeur)" maxlength="300" hide-details />
        </template>
        <div class="d-flex ga-2 mt-4">
          <v-btn variant="outlined" class="flex-grow-1" @click="dialog = null">Annuler</v-btn>
          <v-btn :color="dialog.kind === 'end' ? 'error' : 'primary'" class="flex-grow-1" :loading="dialogBusy" @click="submitDialog">Confirmer</v-btn>
        </div>
      </v-card>
    </v-dialog>

    <v-dialog v-model="trialOpen" max-width="440">
      <v-card class="pa-5">
        <div class="text-h6 mb-1">Offrir un essai gratuit</div>
        <p class="text-muted mb-4" style="font-size: 13px">Une fois par formule et par boutique, sans engagement. Le vendeur est prévenu.</p>
        <v-autocomplete
          v-model="trialForm.vendor_id"
          :items="vendors"
          item-title="shop_name"
          item-value="id"
          label="Boutique"
          class="mb-3"
          hide-details
        />
        <div class="d-flex ga-3">
          <v-select v-model="trialForm.plan_id" :items="sellablePlans" item-title="name" item-value="id" label="Formule" hide-details class="flex-grow-1" />
          <v-text-field v-model="trialForm.days" label="Durée" suffix="jours" inputmode="numeric" hide-details style="max-width: 130px" />
        </div>
        <div class="d-flex ga-2 mt-4">
          <v-btn variant="outlined" class="flex-grow-1" @click="trialOpen = false">Annuler</v-btn>
          <v-btn color="primary" class="flex-grow-1" :loading="grantingTrial" @click="grantTrial">Offrir</v-btn>
        </div>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.view-tabs {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  border-radius: 12px;
  background: var(--color-neutral-800);
}

.view-tab {
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

.view-tab--on {
  background: var(--color-neutral-900);
  color: var(--color-primary);
  box-shadow: var(--shadow-sm);
}

.trial-tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  background: hsl(270 70% var(--tint-bg));
  color: hsl(270 60% var(--tint-fg));
}

.sub-card__time {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sub-card__bar {
  height: 8px;
  border-radius: 999px;
  background: var(--color-neutral-800);
  overflow: hidden;
}

.sub-card__bar span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: hsl(150 55% 45%);
}

.sub-card__bar.is-soon span {
  background: hsl(30 85% 50%);
}

.sub-card__quota {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  color: var(--color-neutral-400);
}

.sub-card__quota span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.sub-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}

.sub-search {
  flex: 1 1 240px;
  max-width: 420px;
}

.sub-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 14px;
}

@media (max-width: 420px) {
  .sub-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

.sub-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-divider);
  background: var(--color-neutral-900);
  box-shadow: var(--shadow-sm);
}

.sub-card__head {
  display: flex;
  align-items: center;
  gap: 12px;
}

.sub-card__logo {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  border-radius: 14px;
  background: linear-gradient(135deg, hsl(150 65% 45%), hsl(190 70% 45%));
  color: #fff;
  font-weight: 800;
}

.sub-card__shop {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.sub-card__shop strong,
.sub-card__shop small {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.sub-card__shop small {
  color: var(--color-neutral-400);
}

.sub-card__plan {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 4px 10px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  background: linear-gradient(120deg, hsl(260 80% var(--tint-bg)), transparent);
}

.sub-card__plan span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex: 1 1 auto;
  white-space: nowrap;
  font-weight: 700;
  color: hsl(260 60% var(--tint-fg));
}

.sub-card__plan strong {
  font-family: var(--font-heading);
  font-size: 17px;
  font-variant-numeric: tabular-nums;
}

.sub-card__plan small {
  color: var(--color-neutral-400);
}

.sub-card__kv {
  font-size: 13px;
}

.sub-card__ref {
  font-family: ui-monospace, monospace;
  font-size: 12px;
}

.sub-card__left {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 8px;
  border-radius: 999px;
  background: hsl(150 70% var(--tint-bg));
  color: hsl(150 55% var(--tint-fg));
  font-size: 11.5px;
}

.sub-card__left.is-soon {
  background: hsl(38 90% var(--tint-bg));
  color: hsl(30 75% var(--tint-fg));
}

.sub-card__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: auto;
}
</style>
