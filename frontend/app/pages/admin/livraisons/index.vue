<script setup lang="ts">
/**
 * Suivi des livraisons en temps réel : chaque colis entre la confirmation
 * du vendeur et sa remise, plus les livraisons terminées aujourd'hui.
 *
 * « Temps réel » = rafraîchissement automatique toutes les REFRESH_MS (mis
 * en pause quand l'onglet est masqué, relancé dès qu'il revient) : le
 * backend ne pousse pas encore d'événements admin sur la WebSocket. Les
 * lignes dont le statut ou le livreur a changé depuis le dernier passage
 * clignotent brièvement pour que le changement se voie.
 *
 * Les alertes « immobile depuis » s'appuient sur SubOrder.updated_at, qui
 * bouge à chaque changement de statut/livreur/dispatch — pas sur la position
 * du livreur, qui n'est pas suivie en continu (voir backend
 * app/couriers/models.py).
 */
import {
  PhArrowRight,
  PhArrowsClockwise,
  PhClock,
  PhMagnifyingGlass,
  PhMotorcycle,
  PhUser,
  PhWarningCircle,
} from '@phosphor-icons/vue'
import type { DeliveryMonitorEntry, DeliveryMonitorRead } from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const REFRESH_MS = 15_000

const { apiFetch } = useApi()

const { data, pending, error, refresh } = await useAsyncData(
  'admin-delivery-monitor',
  () => apiFetch<DeliveryMonitorRead>('/admin/deliveries/monitor'),
  { getCachedData: () => undefined },
)

const view = ref<'list' | 'map'>('list')

// --- Étapes ------------------------------------------------------------------

type Stage = 'unassigned' | 'offered' | 'preparing' | 'in_transit' | 'at_pickup' | 'delivered'

const STAGES: { key: Stage; label: string; color: string }[] = [
  { key: 'unassigned', label: 'Sans livreur', color: '#d9534f' },
  { key: 'offered', label: 'Proposées', color: '#e0822e' },
  { key: 'preparing', label: 'En préparation', color: '#3d7bd9' },
  { key: 'in_transit', label: 'En route', color: '#7a5af5' },
  { key: 'at_pickup', label: 'Au point de retrait', color: '#c9a227' },
  { key: 'delivered', label: "Livrées aujourd'hui", color: '#2e9e5b' },
]
const stageMeta = Object.fromEntries(STAGES.map((s) => [s.key, s])) as Record<Stage, (typeof STAGES)[number]>

function stageOf(e: DeliveryMonitorEntry): Stage {
  if (e.status === 'delivered') return 'delivered'
  if (e.status === 'arrived_at_pickup_point') return 'at_pickup'
  if (e.status === 'shipped') return 'in_transit'
  if (e.courier_id) return 'preparing'
  return e.dispatch_offered_courier_id ? 'offered' : 'unassigned'
}

// Au-delà, un colis immobile dans son étape est signalé. Volontairement
// larges : ce sont des signaux d'enquête, pas des pénalités.
const STALE_AFTER_MIN: Record<Stage, number | null> = {
  unassigned: 30,
  offered: 20,
  preparing: 24 * 60,
  in_transit: 4 * 60,
  at_pickup: 3 * 24 * 60,
  delivered: null,
}

// --- Horloge -------------------------------------------------------------------

const now = ref(Date.now())
const todayIso = computed(() => {
  const d = new Date(now.value)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
})

function minutesSince(iso: string) {
  return Math.max(0, Math.floor((now.value - new Date(iso).getTime()) / 60_000))
}
function formatDuration(minutes: number) {
  if (minutes < 1) return "à l'instant"
  if (minutes < 60) return `${minutes} min`
  if (minutes < 24 * 60) return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, '0')}`
  return `${Math.floor(minutes / (24 * 60))} j`
}
function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
}
function shortId(id: string) {
  return `#GN-${id.slice(0, 5).toUpperCase()}`
}

// --- Lignes --------------------------------------------------------------------

interface Row {
  entry: DeliveryMonitorEntry
  stage: Stage
  idleMin: number
  late: boolean
  stale: boolean
  search: string
}

function normalize(text: string) {
  return text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().trim()
}

const rows = computed<Row[]>(() =>
  (data.value?.entries ?? []).map((entry) => {
    const stage = stageOf(entry)
    const idleMin = minutesSince(entry.updated_at)
    const threshold = STALE_AFTER_MIN[stage]
    return {
      entry,
      stage,
      idleMin,
      late: stage !== 'delivered' && !!entry.estimated_delivery_max && entry.estimated_delivery_max < todayIso.value,
      stale: threshold !== null && idleMin >= threshold,
      search: normalize(
        [
          shortId(entry.order_id),
          entry.shop_name,
          entry.vendor_zone,
          entry.delivery_zone,
          entry.delivery_address,
          entry.pickup_point_name,
          entry.buyer_name,
          entry.buyer_phone,
          entry.courier_name,
          entry.courier_phone,
          entry.dispatch_offered_courier_name,
        ]
          .filter(Boolean)
          .join(' '),
      ),
    }
  }),
)

const counts = computed(() => {
  const byStage = Object.fromEntries(STAGES.map((s) => [s.key, 0])) as Record<Stage, number>
  for (const row of rows.value) byStage[row.stage]++
  return {
    byStage,
    alerts: rows.value.filter((r) => r.late || r.stale).length,
    active: rows.value.filter((r) => r.stage !== 'delivered').length,
  }
})

const stageFilter = ref<Stage | 'alerts' | null>(null)
const search = ref('')

function toggleFilter(key: Stage | 'alerts') {
  stageFilter.value = stageFilter.value === key ? null : key
}

// Urgent d'abord (alertes), puis le plus longtemps immobile ; les livrées en dernier.
const visibleRows = computed(() => {
  const term = normalize(search.value)
  return rows.value
    .filter((r) => {
      if (stageFilter.value === 'alerts') return r.late || r.stale
      if (stageFilter.value) return r.stage === stageFilter.value
      return true
    })
    .filter((r) => !term || r.search.includes(term))
    .sort((a, b) => {
      const rank = (r: Row) => (r.stage === 'delivered' ? 2 : r.late || r.stale ? 0 : 1)
      if (rank(a) !== rank(b)) return rank(a) - rank(b)
      return a.stage === 'delivered' ? a.idleMin - b.idleMin : b.idleMin - a.idleMin
    })
})

function destinationLabel(e: DeliveryMonitorEntry) {
  if (e.delivery_type === 'pickup_point') return e.pickup_point_name ?? 'Point de retrait'
  return e.delivery_zone || e.delivery_address
}

// --- Rafraîchissement automatique --------------------------------------------

const autoRefresh = ref(true)
const lastUpdated = ref(Date.now())
const changedIds = ref(new Set<string>())
let previous = new Map<string, string>()

const signature = (e: DeliveryMonitorEntry) => `${e.status}|${e.courier_id}|${e.dispatch_offered_courier_id}`

watch(
  () => data.value,
  (value) => {
    if (!value) return
    lastUpdated.value = Date.now()
    const next = new Map(value.entries.map((e) => [e.sub_order_id, signature(e)]))
    // Pas de surbrillance au premier chargement : tout serait « nouveau ».
    if (previous.size) {
      changedIds.value = new Set([...next].filter(([id, sig]) => previous.get(id) !== sig).map(([id]) => id))
      if (changedIds.value.size) setTimeout(() => (changedIds.value = new Set()), 4000)
    }
    previous = next
  },
  { immediate: true },
)

const secondsSinceUpdate = computed(() => Math.max(0, Math.floor((now.value - lastUpdated.value) / 1000)))

let clock: ReturnType<typeof setInterval> | undefined
let poller: ReturnType<typeof setInterval> | undefined

function startPolling() {
  stopPolling()
  if (autoRefresh.value && !document.hidden) poller = setInterval(() => refresh(), REFRESH_MS)
}
function stopPolling() {
  if (poller) clearInterval(poller)
  poller = undefined
}
function onVisibility() {
  if (document.hidden) return stopPolling()
  if (autoRefresh.value) refresh()
  startPolling()
}

watch(autoRefresh, (on) => {
  if (on) refresh()
  startPolling()
})

onMounted(() => {
  clock = setInterval(() => (now.value = Date.now()), 1000)
  document.addEventListener('visibilitychange', onVisibility)
  startPolling()
})
onBeforeUnmount(() => {
  clearInterval(clock)
  stopPolling()
  document.removeEventListener('visibilitychange', onVisibility)
})
</script>

<template>
  <div class="dashboard-shell">
    <div class="monitor-header">
      <div>
        <h1 class="text-h6 mb-0">Suivi des livraisons</h1>
        <p class="text-muted monitor-header__sub">
          <span class="live-dot" :class="{ 'live-dot--on': autoRefresh && !error }" />
          <template v-if="error">Connexion perdue — nouvel essai au prochain rafraîchissement.</template>
          <template v-else-if="autoRefresh">En direct · mis à jour il y a {{ secondsSinceUpdate }} s</template>
          <template v-else>Rafraîchissement automatique en pause</template>
        </p>
      </div>
      <div class="d-flex align-center ga-2 flex-wrap">
        <v-switch v-model="autoRefresh" label="Auto" density="compact" hide-details color="primary" inset />
        <v-btn variant="tonal" size="small" :loading="pending" @click="refresh()">
          <PhArrowsClockwise :size="15" class="mr-1" />
          Actualiser
        </v-btn>
        <AdminViewToggle v-model="view" />
      </div>
    </div>

    <template v-if="view === 'list'">
      <div class="kpis mb-4">
        <button
          v-for="s in STAGES"
          :key="s.key"
          type="button"
          class="kpi"
          :class="{ 'kpi--active': stageFilter === s.key }"
          :aria-pressed="stageFilter === s.key"
          @click="toggleFilter(s.key)"
        >
          <span class="kpi__bar" :style="{ background: s.color }" />
          <span class="kpi__value">{{ counts.byStage[s.key] }}</span>
          <span class="kpi__label">{{ s.label }}</span>
        </button>
        <button
          type="button"
          class="kpi kpi--alert"
          :class="{ 'kpi--active': stageFilter === 'alerts' }"
          :aria-pressed="stageFilter === 'alerts'"
          @click="toggleFilter('alerts')"
        >
          <span class="kpi__bar" />
          <span class="kpi__value">{{ counts.alerts }}</span>
          <span class="kpi__label">À surveiller</span>
        </button>
      </div>

      <v-text-field
        v-model="search"
        placeholder="Rechercher une commande, boutique, livreur, client, zone…"
        density="compact"
        hide-details
        clearable
        class="mb-4"
      >
        <template #prepend-inner>
          <PhMagnifyingGlass :size="16" color="var(--color-neutral-500)" />
        </template>
      </v-text-field>

      <CommonEmptyState
        v-if="data && !counts.active && !counts.byStage.delivered"
        message="Aucune livraison en cours ni terminée aujourd'hui."
      />
      <CommonEmptyState v-else-if="data && !visibleRows.length" message="Aucune livraison ne correspond à ce filtre." />

      <TransitionGroup name="row" tag="div" class="rows">
        <NuxtLink
          v-for="row in visibleRows"
          :key="row.entry.sub_order_id"
          :to="`/admin/commandes/${row.entry.order_id}`"
          class="row"
          :class="{ 'row--changed': changedIds.has(row.entry.sub_order_id), 'row--done': row.stage === 'delivered' }"
          :style="{ '--stage-color': stageMeta[row.stage].color }"
        >
          <div class="row__top">
            <span class="row__id">{{ shortId(row.entry.order_id) }}</span>
            <span class="row__stage">{{ stageMeta[row.stage].label }}</span>
            <span v-if="row.late" class="row__flag"><PhWarningCircle :size="13" weight="fill" /> En retard</span>
            <span v-if="row.stale" class="row__flag">
              <PhClock :size="13" weight="fill" /> Immobile depuis {{ formatDuration(row.idleMin) }}
            </span>
            <span class="row__time">
              <template v-if="row.stage === 'delivered'">Livrée à {{ formatTime(row.entry.updated_at) }}</template>
              <template v-else>Dernier changement il y a {{ formatDuration(row.idleMin) }}</template>
            </span>
          </div>

          <div class="row__route">
            <span class="row__place">
              <strong>{{ row.entry.shop_name }}</strong>
              <span v-if="row.entry.vendor_zone" class="text-muted"> · {{ row.entry.vendor_zone }}</span>
            </span>
            <PhArrowRight :size="14" class="row__arrow" />
            <span class="row__place">
              <strong>{{ destinationLabel(row.entry) }}</strong>
              <span class="text-muted"> · {{ row.entry.delivery_type === 'pickup_point' ? 'point de retrait' : 'domicile' }}</span>
              <span v-if="row.entry.storage_location" class="text-muted"> · emplacement {{ row.entry.storage_location }}</span>
            </span>
          </div>

          <div class="row__people">
            <span class="row__person">
              <PhMotorcycle :size="15" />
              <template v-if="row.entry.courier_name">
                <span class="online-dot" :class="{ 'online-dot--on': row.entry.courier_is_online }" />
                {{ row.entry.courier_name }}<span v-if="row.entry.courier_phone" class="text-muted"> · {{ row.entry.courier_phone }}</span>
              </template>
              <span v-else-if="row.entry.dispatch_offered_courier_name" class="text-muted">
                Proposée à {{ row.entry.dispatch_offered_courier_name }}…
              </span>
              <span v-else class="row__missing">Aucun livreur</span>
            </span>
            <span class="row__person">
              <PhUser :size="15" />
              {{ row.entry.buyer_name ?? 'Client' }}<span v-if="row.entry.buyer_phone" class="text-muted"> · {{ row.entry.buyer_phone }}</span>
            </span>
            <span class="row__person text-muted">
              {{ formatGnf(row.entry.amount + row.entry.delivery_fee) }}
              · {{ row.entry.payment_method === 'cash_on_delivery' ? 'à encaisser' : 'payé en ligne' }}
              <template v-if="row.entry.estimated_delivery_min && row.entry.estimated_delivery_max && row.stage !== 'delivered'">
                · prévu {{ formatDeliveryEstimate(row.entry.estimated_delivery_min, row.entry.estimated_delivery_max) }}
              </template>
            </span>
          </div>
        </NuxtLink>
      </TransitionGroup>
    </template>

    <AdminCourierDeliveriesMap v-else />
  </div>
</template>

<style scoped>
.monitor-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}

.monitor-header__sub {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 4px 0 0;
  font-size: 12.5px;
}

.live-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--color-neutral-500);
}

.live-dot--on {
  background: var(--color-success);
  animation: pulse 1.6s ease-out infinite;
}

@keyframes pulse {
  0% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--color-success) 60%, transparent); }
  100% { box-shadow: 0 0 0 8px transparent; }
}

/* --- Compteurs ----------------------------------------------------------- */

.kpis {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 10px;
}

.kpi {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 12px 14px 12px 18px;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-md);
  background: var(--color-neutral-900);
  color: inherit;
  text-align: left;
  cursor: pointer;
  overflow: hidden;
}

.kpi:hover {
  border-color: var(--color-divider-strong);
}

.kpi--active {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 1px var(--color-primary);
}

.kpi__bar {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 5px;
}

.kpi--alert .kpi__bar {
  background: var(--color-error);
}

.kpi__value {
  font-family: var(--font-heading);
  font-size: 24px;
  font-weight: 700;
  line-height: 1.1;
}

.kpi__label {
  font-size: 12px;
  color: var(--color-neutral-400);
}

/* --- Lignes -------------------------------------------------------------- */

.rows {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.row {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 14px;
  border: 1px solid var(--color-divider);
  border-left: 5px solid var(--stage-color);
  border-radius: var(--radius-md);
  background: var(--color-neutral-900);
  color: inherit;
  text-decoration: none;
  transition: background-color 0.6s ease;
}

.row:hover {
  border-color: var(--color-divider-strong);
  border-left-color: var(--stage-color);
}

.row--done {
  opacity: 0.7;
}

.row--changed {
  background: color-mix(in srgb, var(--stage-color) 18%, var(--color-neutral-900));
}

.row__top {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px 10px;
  font-size: 12.5px;
}

.row__id {
  font-family: var(--font-heading);
  font-weight: 700;
}

.row__stage {
  padding: 1px 8px;
  border-radius: 999px;
  font-weight: 600;
  color: var(--stage-color);
  background: color-mix(in srgb, var(--stage-color) 14%, transparent);
}

.row__flag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 8px;
  border-radius: 999px;
  font-weight: 600;
  color: var(--color-error);
  background: color-mix(in srgb, var(--color-error) 12%, transparent);
}

.row__time {
  margin-left: auto;
  color: var(--color-neutral-400);
}

.row__route {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 8px;
  font-size: 14px;
}

.row__place {
  min-width: 0;
  overflow-wrap: anywhere;
}

.row__arrow {
  flex: none;
  color: var(--color-neutral-500);
}

.row__people {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 18px;
  font-size: 12.5px;
}

.row__person {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  overflow-wrap: anywhere;
}

.row__missing {
  color: var(--color-error);
  font-weight: 600;
}

.online-dot {
  width: 7px;
  height: 7px;
  flex: none;
  border-radius: 50%;
  background: var(--color-neutral-500);
}

.online-dot--on {
  background: var(--color-success);
}

.row-enter-from,
.row-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

.row-enter-active,
.row-leave-active {
  transition: all 0.25s ease;
}

.row-move {
  transition: transform 0.3s ease;
}

@media (max-width: 600px) {
  .row__time {
    margin-left: 0;
    width: 100%;
  }
}
</style>
