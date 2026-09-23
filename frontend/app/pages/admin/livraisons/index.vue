<script setup lang="ts">
/**
 * Suivi des livraisons en temps réel : chaque colis entre la confirmation
 * du vendeur et sa remise, plus les livraisons terminées aujourd'hui.
 *
 * « Temps réel » = rafraîchissement automatique toutes les REFRESH_MS (mis
 * en pause quand l'onglet est masqué, relancé dès qu'il revient) : le
 * backend ne pousse pas encore d'événements admin sur la WebSocket. Les
 * cartes dont le statut ou le livreur a changé depuis le dernier passage
 * s'illuminent brièvement ; celles en route « respirent » en continu, comme
 * leurs repères sur la vue Carte (voir CourierDeliveriesMap.vue).
 *
 * Les alertes « immobile depuis » s'appuient sur SubOrder.updated_at, qui
 * bouge à chaque changement de statut/livreur/dispatch — pas sur la position
 * du livreur, qui n'est pas suivie en continu (voir backend
 * app/couriers/models.py).
 */
import {
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

      <TransitionGroup name="card" tag="div" class="cards">
        <NuxtLink
          v-for="row in visibleRows"
          :key="row.entry.sub_order_id"
          :to="`/admin/commandes/${row.entry.order_id}`"
          class="card"
          :class="{
            'card--changed': changedIds.has(row.entry.sub_order_id),
            'card--done': row.stage === 'delivered',
            'card--live': row.stage === 'in_transit',
          }"
          :style="{ '--stage-color': stageMeta[row.stage].color }"
        >
          <div class="card__top">
            <span class="card__id">{{ shortId(row.entry.order_id) }}</span>
            <span class="card__stage">
              <span v-if="row.stage === 'in_transit'" class="card__live-dot" aria-hidden="true" />
              {{ stageMeta[row.stage].label }}
            </span>
          </div>

          <div v-if="row.late || row.stale" class="card__flags">
            <span v-if="row.late" class="card__flag"><PhWarningCircle :size="13" weight="fill" /> En retard</span>
            <span v-if="row.stale" class="card__flag">
              <PhClock :size="13" weight="fill" /> Immobile depuis {{ formatDuration(row.idleMin) }}
            </span>
          </div>

          <div class="card__route">
            <div class="card__place">
              <span class="card__place-dot" />
              <div>
                <strong>{{ row.entry.shop_name }}</strong>
                <div v-if="row.entry.vendor_zone" class="text-muted">{{ row.entry.vendor_zone }}</div>
              </div>
            </div>
            <div class="card__place">
              <span class="card__place-dot card__place-dot--end" />
              <div>
                <strong>{{ destinationLabel(row.entry) }}</strong>
                <div class="text-muted">
                  {{ row.entry.delivery_type === 'pickup_point' ? 'Point de retrait' : 'Domicile' }}
                  <span v-if="row.entry.storage_location"> · emplacement {{ row.entry.storage_location }}</span>
                </div>
              </div>
            </div>
          </div>

          <div class="card__people">
            <span class="card__person">
              <PhMotorcycle :size="15" class="flex-none" />
              <template v-if="row.entry.courier_name">
                <span class="online-dot" :class="{ 'online-dot--on': row.entry.courier_is_online }" />
                <span>{{ row.entry.courier_name }}<span v-if="row.entry.courier_phone" class="text-muted"> · {{ row.entry.courier_phone }}</span></span>
              </template>
              <span v-else-if="row.entry.dispatch_offered_courier_name" class="text-muted">
                Proposée à {{ row.entry.dispatch_offered_courier_name }}…
              </span>
              <span v-else class="card__missing">Aucun livreur</span>
            </span>
            <span class="card__person">
              <PhUser :size="15" class="flex-none" />
              <span>{{ row.entry.buyer_name ?? 'Client' }}<span v-if="row.entry.buyer_phone" class="text-muted"> · {{ row.entry.buyer_phone }}</span></span>
            </span>
          </div>

          <div class="card__foot">
            <span>
              <strong>{{ formatGnf(row.entry.amount + row.entry.delivery_fee) }}</strong>
              <span class="text-muted"> · {{ row.entry.payment_method === 'cash_on_delivery' ? 'à encaisser' : `payé · ${PAYMENT_METHOD_LABELS[row.entry.payment_method].short}` }}</span>
            </span>
            <span class="text-muted">
              <template v-if="row.stage === 'delivered'">Livrée à {{ formatTime(row.entry.updated_at) }}</template>
              <template v-else>Il y a {{ formatDuration(row.idleMin) }}</template>
            </span>
          </div>
          <div
            v-if="row.entry.estimated_delivery_min && row.entry.estimated_delivery_max && row.stage !== 'delivered'"
            class="card__eta text-muted"
          >
            Prévu {{ formatDeliveryEstimate(row.entry.estimated_delivery_min, row.entry.estimated_delivery_max) }}
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

/* --- Cartes -------------------------------------------------------------- */

/* 4 cartes par ligne sur grand écran, puis 3, 2, 1. */
.cards {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

@media (max-width: 1400px) {
  .cards { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}

@media (max-width: 1000px) {
  .cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 600px) {
  .cards { grid-template-columns: minmax(0, 1fr); }
}

.card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid var(--color-divider);
  border-top: 4px solid var(--stage-color);
  border-radius: var(--radius-md);
  background: var(--color-neutral-900);
  color: inherit;
  text-decoration: none;
  transition: background-color 0.6s ease, border-color 0.15s ease;
}

.card:hover {
  border-color: var(--color-divider-strong);
  border-top-color: var(--stage-color);
}

.card--done {
  opacity: 0.7;
}

.card--changed {
  background: color-mix(in srgb, var(--stage-color) 18%, var(--color-neutral-900));
}

/* Livraison en route : halo qui respire doucement autour de la carte. */
.card--live {
  animation: live-glow 2.4s ease-in-out infinite;
}

@keyframes live-glow {
  0%,
  100% {
    box-shadow: 0 0 0 0 color-mix(in srgb, var(--stage-color) 0%, transparent);
    border-color: var(--color-divider);
  }
  50% {
    box-shadow: 0 0 0 4px color-mix(in srgb, var(--stage-color) 28%, transparent),
      0 0 18px 2px color-mix(in srgb, var(--stage-color) 30%, transparent);
    border-color: color-mix(in srgb, var(--stage-color) 60%, transparent);
  }
}

.card__live-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--stage-color);
  animation: live-dot 1.2s ease-in-out infinite;
}

@keyframes live-dot {
  0%,
  100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.35; transform: scale(0.7); }
}

.card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12.5px;
}

.card__id {
  font-family: var(--font-heading);
  font-weight: 700;
}

.card__stage {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 1px 9px;
  border-radius: 999px;
  font-weight: 600;
  color: var(--stage-color);
  background: color-mix(in srgb, var(--stage-color) 14%, transparent);
  white-space: nowrap;
}

.card__flags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.card__flag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-error);
  background: color-mix(in srgb, var(--color-error) 12%, transparent);
}

.card__route {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 13px;
}

/* Trait vertical entre départ et arrivée. */
.card__route::before {
  content: '';
  position: absolute;
  left: 4px;
  top: 12px;
  bottom: 22px;
  border-left: 2px dotted var(--color-divider-strong);
}

.card__place {
  display: flex;
  gap: 10px;
  min-width: 0;
  overflow-wrap: anywhere;
}

.card__place .text-muted {
  font-size: 12px;
}

.card__place-dot {
  position: relative;
  flex: none;
  width: 10px;
  height: 10px;
  margin-top: 4px;
  border-radius: 50%;
  border: 2px solid var(--stage-color);
  background: var(--color-neutral-900);
}

.card__place-dot--end {
  background: var(--stage-color);
}

.card__people {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-top: 8px;
  border-top: 1px solid var(--color-divider);
  font-size: 12.5px;
}

.card__person {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  overflow-wrap: anywhere;
}

.card__missing {
  color: var(--color-error);
  font-weight: 600;
}

.card__foot {
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 4px 10px;
  margin-top: auto;
  font-size: 12.5px;
}

.card__eta {
  font-size: 12px;
  margin-top: -6px;
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

.card-enter-from,
.card-leave-to {
  opacity: 0;
  transform: scale(0.97);
}

.card-enter-active,
.card-leave-active {
  transition: all 0.25s ease;
}

.card-move {
  transition: transform 0.3s ease;
}

@media (prefers-reduced-motion: reduce) {
  .card--live,
  .card__live-dot,
  .live-dot--on {
    animation: none;
  }
}
</style>
