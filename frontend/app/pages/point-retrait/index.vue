<script setup lang="ts">
/**
 * Espace du gestionnaire de point de retrait : colis attendus (déposés par
 * un livreur), colis en stock (à remettre aux clients) et historique des
 * remises. Toute réception et toute remise passent par le scan d'un QR —
 * celui du livreur au dépôt, celui du client au retrait (voir backend
 * app/orders/handoff.py) : aucun bouton manuel.
 */
import {
  PhClock,
  PhMagnifyingGlass,
  PhMapPinLine,
  PhMotorcycle,
  PhPhone,
  PhQrCode,
  PhStorefront,
  PhUser,
  PhWallet,
  PhWarning,
  PhPackage,
  PhArrowUUpLeft,
} from '@phosphor-icons/vue'
import type { TodoItem } from '~/components/common/TodoCards.vue'
import type { ParcelSize, PickupPointManagerSubOrderRead, PickupPointRead, WalletRead } from '~/types/api'

definePageMeta({ middleware: 'pickup-manager', layout: 'point-retrait' })

const { apiFetch } = useApi()
const toast = useToastStore()

const { data: deliveries, pending, refresh } = await useAsyncData(
  'pickup-manager-deliveries',
  () => apiFetch<PickupPointManagerSubOrderRead[]>('/orders/pickup-point-deliveries'),
  { default: () => [], getCachedData: hydrateThenRefetch },
)
const { data: point } = await useAsyncData(
  'pickup-manager-point',
  () => apiFetch<PickupPointRead>('/pickup-point-managers/me/point'),
  { getCachedData: hydrateThenRefetch },
)

// --- Temps réel : notifications en direct + relecture périodique ------------------

const notifications = useNotificationStore()
watch(
  () => notifications.items[0]?.id,
  (id, previous) => {
    if (id && id !== previous) refresh()
  },
)
watch(() => notifications.deliveriesTick, () => refresh())
let poller: ReturnType<typeof setInterval> | undefined
function onVisibility() {
  if (!document.hidden) refresh()
}
onMounted(() => {
  poller = setInterval(() => {
    if (!document.hidden) refresh()
  }, 30_000)
  document.addEventListener('visibilitychange', onVisibility)
})
onBeforeUnmount(() => {
  clearInterval(poller)
  document.removeEventListener('visibilitychange', onVisibility)
})

// --- Onglets et recherche ----------------------------------------------------------

type Tab = 'expected' | 'stock' | 'done'
const tab = ref<Tab>('stock')
const search = ref<string | null>('')
// Un colis au point depuis plus longtemps que ça est signalé.
const LONG_WAIT_DAYS = 3

function daysSince(iso: string) {
  return Math.floor((Date.now() - new Date(iso).getTime()) / (24 * 3600 * 1000))
}

const byTab = computed(() => ({
  expected: deliveries.value.filter((so) => so.status === 'shipped'),
  // Non retirés à temps (return_pending) : restent au point jusqu'au passage du livreur du retour.
  stock: deliveries.value
    .filter((so) => so.status === 'arrived_at_pickup_point' || so.status === 'return_pending')
    .sort((a, b) => a.updated_at.localeCompare(b.updated_at)),
  done: deliveries.value.filter((so) => ['delivered', 'returning', 'returned'].includes(so.status)).slice(0, 50),
}))
const toReturn = computed(() => byTab.value.stock.filter((so) => so.status === 'return_pending').length)
const longWaits = computed(() => byTab.value.stock.filter((so) => daysSince(so.updated_at) >= LONG_WAIT_DAYS).length)

// Au premier affichage : l'onglet qui a quelque chose à faire.
watch(
  byTab,
  (value) => {
    if (!value.stock.length && value.expected.length && tab.value === 'stock') tab.value = 'expected'
  },
  { immediate: true, once: true },
)

function normalize(value: string) {
  return value.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
}
// --- « À faire » -------------------------------------------------------------

type StockFocus = 'unstored' | 'late' | 'return'
const stockFocus = ref<StockFocus | null>(null)
const unstored = computed(() => byTab.value.stock.filter((so) => !so.storage_location).length)

const walletAvailable = ref(0)
onMounted(async () => {
  try {
    const wallets = await apiFetch<WalletRead[]>('/wallets/mine')
    walletAvailable.value = wallets.find((w) => w.kind === 'pickup_point')?.balance.available ?? 0
  } catch {
    walletAvailable.value = 0
  }
})

const todos = computed<TodoItem[]>(() => {
  const items: TodoItem[] = []
  const expected = byTab.value.expected.length
  if (toReturn.value)
    items.push({
      key: 'return',
      count: toReturn.value,
      title: toReturn.value > 1 ? 'colis à rendre' : 'colis à rendre',
      text: "Non retirés : scannez le QR du livreur du retour quand il passe. Le client peut encore venir d'ici là.",
      icon: PhArrowUUpLeft,
      hue: 30,
      urgent: true,
      active: tab.value === 'stock' && stockFocus.value === 'return',
    })
  if (longWaits.value)
    items.push({
      key: 'late',
      count: longWaits.value,
      title: longWaits.value > 1 ? 'clients à relancer' : 'client à relancer',
      text: `Colis au point depuis ${LONG_WAIT_DAYS} jours ou plus : appelez-les.`,
      icon: PhWarning,
      hue: 355,
      urgent: true,
      active: tab.value === 'stock' && stockFocus.value === 'late',
    })
  if (unstored.value)
    items.push({
      key: 'unstored',
      count: unstored.value,
      title: unstored.value > 1 ? 'colis à ranger' : 'colis à ranger',
      text: 'Notez leur emplacement pour les retrouver vite.',
      icon: PhMapPinLine,
      hue: 35,
      active: tab.value === 'stock' && stockFocus.value === 'unstored',
    })
  if (expected)
    items.push({
      key: 'expected',
      count: expected,
      title: expected > 1 ? 'colis en route vers vous' : 'colis en route vers vous',
      text: 'Scannez le code du livreur à son arrivée.',
      icon: PhMotorcycle,
      hue: 200,
      active: tab.value === 'expected',
    })
  if (walletAvailable.value > 0)
    items.push({
      key: 'wallet',
      countLabel: formatGnf(walletAvailable.value),
      title: 'disponibles',
      text: 'Vos gains peuvent être retirés.',
      icon: PhWallet,
      hue: 150,
      to: '/point-retrait/gains',
    })
  return items
})

function onTodo(key: string) {
  if (key === 'expected') {
    tab.value = 'expected'
    stockFocus.value = null
    return
  }
  const focus = key as StockFocus
  tab.value = 'stock'
  stockFocus.value = stockFocus.value === focus ? null : focus
}
watch(tab, (value) => {
  if (value !== 'stock') stockFocus.value = null
})

const visible = computed(() => {
  const term = normalize((search.value ?? '').trim())
  let list = byTab.value[tab.value]
  if (tab.value === 'stock' && stockFocus.value === 'unstored') list = list.filter((so) => !so.storage_location)
  if (tab.value === 'stock' && stockFocus.value === 'late') list = list.filter((so) => daysSince(so.updated_at) >= LONG_WAIT_DAYS)
  if (tab.value === 'stock' && stockFocus.value === 'return') list = list.filter((so) => so.status === 'return_pending')
  if (!term) return list
  const digits = term.replace(/\D/g, '')
  return list.filter((so) => {
    const haystack = normalize(
      [shortId(so.order_id), so.shop_name, so.storage_location ?? '', so.customer_name ?? '', so.courier_name ?? ''].join(' '),
    )
    const phones = `${so.customer_phone ?? ''} ${so.courier_phone ?? ''}`.replace(/\D/g, '')
    return haystack.includes(term) || (digits.length >= 3 && phones.includes(digits))
  })
})

const TABS: { key: Tab; label: string }[] = [
  { key: 'expected', label: 'Attendus' },
  { key: 'stock', label: 'En stock' },
  { key: 'done', label: 'Remis' },
]

// --- Emplacement de stockage ---------------------------------------------------------

const editingId = ref<string | null>(null)
const draftLocation = ref('')
const savingLocation = ref(false)

function editLocation(so: PickupPointManagerSubOrderRead) {
  editingId.value = so.id
  draftLocation.value = so.storage_location ?? ''
}

async function saveLocation(so: PickupPointManagerSubOrderRead) {
  savingLocation.value = true
  try {
    await apiFetch(`/orders/sub-orders/${so.id}/storage-location`, {
      method: 'PATCH',
      body: { storage_location: draftLocation.value.trim() || null },
    })
    editingId.value = null
    await refresh()
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'enregistrer l'emplacement."))
  } finally {
    savingLocation.value = false
  }
}

// --- Taille du colis : vérifiée à la réception, elle fixe la rémunération ------------

const sizingId = ref<string | null>(null)

async function setSize(so: PickupPointManagerSubOrderRead, size: ParcelSize) {
  if (size === so.parcel_size) return
  sizingId.value = so.id
  try {
    await apiFetch(`/orders/sub-orders/${so.id}/parcel-size`, { method: 'PATCH', body: { parcel_size: size } })
    await refresh()
    toast.success(`Taille corrigée : ${parcelSizeLabel(size)}.`)
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de corriger la taille.'))
  } finally {
    sizingId.value = null
  }
}

// --- Scan ------------------------------------------------------------------------------
// Un seul scanner : le serveur reconnaît le colis et l'étape (dépôt du
// livreur ou retrait du client) à partir du code.

const scannerOpen = ref(false)

async function handleDecode(code: string) {
  try {
    const updated = await apiFetch<{ id: string; order_id: string; status: string }>('/orders/sub-orders/confirm-delivery', {
      method: 'POST',
      body: { code },
    })
    await refresh()
    if (updated.status === 'delivered') {
      toast.success(`Colis ${shortId(updated.order_id)} remis au client.`)
      tab.value = 'done'
    } else if (updated.status === 'returning') {
      toast.success(`Colis ${shortId(updated.order_id)} remis au livreur du retour.`)
      tab.value = 'done'
    } else {
      toast.success(`Colis ${shortId(updated.order_id)} réceptionné — indiquez où vous le rangez.`)
      tab.value = 'stock'
      const received = deliveries.value.find((so) => so.id === updated.id)
      if (received) editLocation(received)
    }
  } catch (e) {
    toast.error(apiErrorMessage(e, 'QR code invalide ou expiré.'))
  }
}

function shortId(orderId: string) {
  return `#GN-${orderId.slice(0, 5).toUpperCase()}`
}
function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}
function itemsSummary(so: PickupPointManagerSubOrderRead) {
  const count = so.items.reduce((n, item) => n + item.quantity, 0)
  const names = so.items.slice(0, 2).map((i) => i.product_name).join(', ')
  return `${count} article${count > 1 ? 's' : ''} · ${names}${so.items.length > 2 ? '…' : ''}`
}
</script>

<template>
  <div class="px-4 pb-4 pm">
    <!-- Mon point -->
    <section class="pm-head">
      <div class="pm-head__info">
        <div class="pm-head__label"><PhStorefront :size="15" /> Mon point de retrait</div>
        <div class="pm-head__name">{{ point?.name ?? '…' }}</div>
        <div class="pm-head__meta">
          <span v-if="point?.opening_hours"><PhClock :size="13" /> {{ point.opening_hours }}</span>
          <NuxtLink to="/point-retrait/mon-point" class="pm-head__link">Gérer mon point</NuxtLink>
        </div>
      </div>
      <v-btn color="white" variant="flat" size="large" class="pm-head__scan" @click="scannerOpen = true">
        <PhQrCode :size="20" class="mr-1" /> Scanner
      </v-btn>
    </section>

    <section v-if="todos.length" class="mb-4" aria-label="À faire">
      <h2 class="pm-todo-title">À faire</h2>
      <CommonTodoCards :items="todos" @select="onTodo" />
      <button v-if="stockFocus" type="button" class="pm-todo-reset" @click="stockFocus = null">
        Afficher tout le stock
      </button>
    </section>

    <!-- Compteurs = onglets -->
    <div class="pm-tabs" role="tablist">
      <button
        v-for="t in TABS"
        :key="t.key"
        type="button"
        role="tab"
        class="pm-tab"
        :class="{ 'pm-tab--active': tab === t.key }"
        :aria-selected="tab === t.key"
        @click="tab = t.key"
      >
        <span class="pm-tab__count">{{ byTab[t.key].length }}</span>
        <span class="pm-tab__label">{{ t.label }}</span>
        <span v-if="t.key === 'stock' && longWaits" class="pm-tab__alert">{{ longWaits }} en attente +{{ LONG_WAIT_DAYS }} j</span>
      </button>
    </div>

    <v-text-field
      v-model="search"
      placeholder="Code, client, téléphone, boutique, emplacement…"
      density="compact"
      variant="outlined"
      hide-details
      clearable
      class="mb-3"
    >
      <template #prepend-inner><PhMagnifyingGlass :size="16" color="var(--color-neutral-500)" /></template>
    </v-text-field>

    <p class="pm-help">
      <template v-if="tab === 'expected'">Colis en route vers votre point : scannez le QR du livreur à son arrivée.</template>
      <template v-else-if="tab === 'stock'">Colis à remettre : scannez le QR présenté par le client. Les plus anciens d'abord.</template>
      <template v-else>Derniers colis remis aux clients.</template>
    </p>

    <v-skeleton-loader v-if="pending && !deliveries.length" type="list-item-three-line@2" />
    <CommonEmptyState
      v-else-if="!visible.length"
      :message="(search ?? '').trim() ? 'Aucun colis ne correspond à cette recherche.' : tab === 'expected' ? 'Aucun colis en route.' : tab === 'stock' ? 'Aucun colis en stock.' : 'Aucune remise pour le moment.'"
    />

    <div class="pm-list">
      <article v-for="so in visible" :key="so.id" class="parcel" :class="{ 'parcel--late': tab === 'stock' && daysSince(so.updated_at) >= LONG_WAIT_DAYS }">
        <header class="parcel__head">
          <span class="parcel__code">{{ shortId(so.order_id) }}</span>
          <span v-if="tab === 'stock'" class="parcel__age" :class="{ 'parcel__age--late': daysSince(so.updated_at) >= LONG_WAIT_DAYS }">
            <PhWarning v-if="daysSince(so.updated_at) >= LONG_WAIT_DAYS" :size="13" />
            {{ daysSince(so.updated_at) === 0 ? "Arrivé aujourd'hui" : `Au point depuis ${daysSince(so.updated_at)} j` }}
          </span>
          <span v-else class="text-muted text-fine">{{ formatDate(tab === 'done' ? so.updated_at : so.created_at) }}</span>
        </header>

        <div v-if="so.status === 'return_pending'" class="parcel__return">
          <PhArrowUUpLeft :size="15" />
          <span>
            Non retiré — à rendre au livreur du retour{{ so.courier_name ? ` (${so.courier_name})` : ', en cours de recherche par la boutique' }}.
            Le client peut encore le retirer d'ici là.
          </span>
        </div>
        <div v-else-if="tab === 'done' && so.status !== 'delivered'" class="parcel__return">
          <PhArrowUUpLeft :size="15" />
          <span>Rendu au livreur du retour</span>
        </div>

        <div class="parcel__items">{{ itemsSummary(so) }}</div>
        <div class="parcel__shop text-muted text-fine"><PhStorefront :size="12" /> {{ so.shop_name }}</div>

        <div v-if="so.customer_name || so.customer_phone" class="parcel__line">
          <PhUser :size="14" />
          <span>{{ so.customer_name ?? 'Client' }}</span>
          <a v-if="so.customer_phone && tab !== 'done'" :href="`tel:${so.customer_phone}`" class="parcel__tel"><PhPhone :size="12" /> {{ so.customer_phone }}</a>
        </div>
        <div v-if="tab === 'expected' && so.courier_name" class="parcel__line">
          <PhMotorcycle :size="14" />
          <span>{{ so.courier_name }}</span>
          <a v-if="so.courier_phone" :href="`tel:${so.courier_phone}`" class="parcel__tel"><PhPhone :size="12" /> {{ so.courier_phone }}</a>
        </div>

        <!-- Taille : corrigeable tant que le colis est au point -->
        <div class="parcel__size">
          <PhPackage :size="15" color="var(--color-primary)" />
          <span class="parcel__size-label">Colis {{ parcelSizeLabel(so.parcel_size) }}</span>
          <span v-if="so.parcel_size !== so.declared_parcel_size" class="parcel__size-fixed">corrigé (déclaré {{ so.declared_parcel_size }})</span>
          <v-menu v-if="tab === 'stock'" location="bottom end">
            <template #activator="{ props: menu }">
              <button type="button" class="parcel__edit" v-bind="menu" :disabled="sizingId === so.id">Corriger</button>
            </template>
            <v-list density="compact">
              <v-list-item v-for="size in PARCEL_SIZES" :key="size.value" :active="size.value === so.parcel_size" @click="setSize(so, size.value)">
                <v-list-item-title>{{ size.value }} · {{ size.label }}</v-list-item-title>
                <v-list-item-subtitle>{{ size.examples }}</v-list-item-subtitle>
              </v-list-item>
            </v-list>
          </v-menu>
        </div>

        <!-- Emplacement : en stock (et modifiable), ou à prévoir pour un colis attendu -->
        <div v-if="tab !== 'done'" class="parcel__storage">
          <PhMapPinLine :size="15" color="var(--color-primary)" />
          <template v-if="editingId === so.id">
            <v-text-field
              v-model="draftLocation"
              placeholder="Ex. Étagère B3"
              density="compact"
              variant="outlined"
              hide-details
              autofocus
              class="flex-grow-1"
              @keyup.enter="saveLocation(so)"
            />
            <v-btn size="small" color="primary" variant="tonal" :loading="savingLocation" @click="saveLocation(so)">OK</v-btn>
          </template>
          <template v-else>
            <span :class="so.storage_location ? 'parcel__storage-value' : 'text-muted'">
              {{ so.storage_location ?? 'Emplacement non renseigné' }}
            </span>
            <button type="button" class="parcel__edit" @click="editLocation(so)">Modifier</button>
          </template>
        </div>
      </article>
    </div>

    <button type="button" class="pm-fab" aria-label="Scanner un QR code" @click="scannerOpen = true">
      <PhQrCode :size="26" weight="bold" />
    </button>

    <VendorQrScannerDialog v-model="scannerOpen" @decode="handleDecode" />
  </div>
</template>

<style scoped>
.parcel__return {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  border-radius: var(--radius-md);
  background: hsl(30 90% var(--tint-bg-soft, 17%));
  color: hsl(30 70% var(--tint-fg));
  font-size: 12.5px;
  line-height: 1.4;
}

.parcel__return svg {
  flex-shrink: 0;
  margin-top: 1px;
}

.parcel__size {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 13px;
}

.parcel__size-label {
  font-weight: 600;
}

.parcel__size-fixed {
  padding: 1px 8px;
  border-radius: 999px;
  background: hsl(38 90% var(--tint-bg));
  color: hsl(30 75% var(--tint-fg));
  font-size: 11px;
  font-weight: 700;
}

.parcel__size .parcel__edit {
  margin-left: auto;
}

.pm {
  max-width: 820px;
  margin: 0 auto;
}

.pm-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 12px 0 14px;
  padding: 16px;
  border-radius: var(--radius-lg);
  color: #fff;
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-800) 100%);
  box-shadow: var(--shadow-md);
}

.pm-head__label {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  opacity: 0.85;
}

.pm-head__name {
  font-family: var(--font-heading);
  font-size: 20px;
  font-weight: 800;
  line-height: 1.2;
}

.pm-head__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 4px;
  font-size: 12.5px;
  opacity: 0.9;
}

.pm-head__meta span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.pm-head__link {
  color: #fff;
  font-weight: 700;
}

.pm-head__scan {
  flex: none;
  color: var(--color-primary) !important;
  font-weight: 800;
}

.pm-tabs {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin-bottom: 12px;
}

.pm-tab {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding: 10px 12px;
  text-align: left;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-md);
  background: var(--color-neutral-900);
  cursor: pointer;
}

.pm-tab--active {
  border-color: var(--color-primary);
  box-shadow: inset 0 0 0 1px var(--color-primary);
}

.pm-tab__count {
  font-family: var(--font-heading);
  font-size: 22px;
  font-weight: 800;
  color: var(--color-neutral-200);
  font-variant-numeric: tabular-nums;
}

.pm-tab__label {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--color-neutral-400);
}

.pm-tab__alert {
  margin-top: 2px;
  font-size: 11px;
  font-weight: 700;
  color: var(--color-accent);
}

.pm-help {
  margin: 0 0 10px;
  font-size: 12.5px;
  color: var(--color-neutral-400);
}

.pm-list {
  /* Place pour le bouton de scan flottant sous la dernière carte. */
  padding-bottom: 72px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 340px), 1fr));
  gap: 10px;
}

.parcel {
  padding: 12px 14px;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-md);
  background: var(--color-neutral-900);
}

.parcel--late {
  border-color: var(--color-accent);
}

.parcel__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.parcel__code {
  font-family: var(--font-heading);
  font-weight: 800;
  color: var(--color-neutral-200);
}

.parcel__age {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 11.5px;
  font-weight: 700;
  color: var(--color-neutral-400);
}

.parcel__age--late {
  color: var(--color-accent);
}

.parcel__items {
  font-size: 13px;
  color: var(--color-neutral-300);
}

.parcel__shop {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 6px;
}

.parcel__line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 3px 0;
  font-size: 13px;
  color: var(--color-neutral-300);
}

.parcel__tel {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  color: var(--color-primary);
  font-weight: 600;
  text-decoration: none;
}

.parcel__storage {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--color-divider);
  font-size: 13px;
}

.parcel__storage-value {
  font-weight: 800;
  color: var(--color-neutral-200);
}

.parcel__edit {
  margin-left: auto;
  border: none;
  background: none;
  font-size: 12px;
  font-weight: 700;
  color: var(--color-primary);
  cursor: pointer;
}

.pm-fab {
  position: fixed;
  right: 18px;
  bottom: calc(86px + env(safe-area-inset-bottom, 0px));
  width: 58px;
  height: 58px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  color: #fff;
  background: var(--color-primary);
  box-shadow: var(--shadow-md);
  cursor: pointer;
  z-index: 6;
}

.pm-todo-title {
  font-family: var(--font-heading);
  font-size: 16px;
  font-weight: 800;
  margin: 0 0 8px;
}

.pm-todo-reset {
  margin-top: 8px;
  border: 0;
  background: none;
  padding: 0;
  color: var(--color-primary-300);
  font-size: 12.5px;
  font-weight: 700;
  cursor: pointer;
}
</style>
