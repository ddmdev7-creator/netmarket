<script setup lang="ts">
import {
  PhCalendarBlank,
  PhEnvelopeSimple,
  PhHash,
  PhIdentificationCard,
  PhMagnifyingGlass,
  PhMapPin,
  PhPhone,
  PhSparkle,
  PhStorefront,
} from '@phosphor-icons/vue'
import type { AdminSubscriptionRead, SubscriptionStatus } from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const { apiFetch } = useApi()
const toast = useToastStore()

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

async function act(subscription: AdminSubscriptionRead, action: 'confirm' | 'cancel') {
  updatingId.value = subscription.id
  try {
    await apiFetch(`/admin/subscriptions/${subscription.id}/${action}`, { method: 'POST' })
    subscriptions.value = subscriptions.value.filter((s) => s.id !== subscription.id)
    toast.success(action === 'confirm' ? 'Abonnement confirmé.' : 'Abonnement annulé.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de mettre à jour cet abonnement.'))
  } finally {
    updatingId.value = null
  }
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
      <span v-if="subscriptions.length" class="pf-tag pf-tag--primary">
        {{ subscriptions.length }} abonnement{{ subscriptions.length > 1 ? 's' : '' }} · {{ formatGnf(revenue) }}
      </span>
    </div>

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
      :message="tab === 'pending' ? 'Les demandes d’abonnement Premium des vendeurs apparaîtront ici. Consultez l’onglet Actifs pour les abonnements en cours.' : 'Aucun abonnement dans cette catégorie.'"
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
          <span class="pf-tag" :class="`pf-tag--${statusMeta[s.status].tone}`">{{ statusMeta[s.status].label }}</span>
        </header>

        <div class="sub-card__plan">
          <span><PhSparkle :size="15" weight="fill" /> {{ s.plan.name }}</span>
          <strong>{{ formatGnf(s.plan.price_gnf) }}</strong>
          <small>{{ s.plan.duration_days }} jours</small>
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
              <span v-if="daysLeft(s) !== null" class="sub-card__left" :class="{ 'is-soon': (daysLeft(s) ?? 99) <= 7 }">
                {{ daysLeft(s) }} j restants
              </span>
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
          <v-btn v-else-if="s.status === 'active'" color="error" variant="outlined" size="small" :loading="updatingId === s.id" @click="act(s, 'cancel')">
            Annuler l'abonnement
          </v-btn>
        </div>
      </article>
    </div>
  </div>
</template>

<style scoped>
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
