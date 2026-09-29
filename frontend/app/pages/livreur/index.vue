<script setup lang="ts">
import {
  PhCheckCircle,
  PhHouse,
  PhMagnifyingGlass,
  PhPower,
  PhQrCode,
  PhStorefront,
  PhWallet,
  PhWarehouse,
} from '@phosphor-icons/vue'
import type { TodoItem } from '~/components/common/TodoCards.vue'
import type { CourierDetailRead, CourierSubOrderRead, WalletRead } from '~/types/api'

definePageMeta({ middleware: 'courier', layout: 'livreur' })

const { apiFetch } = useApi()
const toast = useToastStore()
const { locating, locate } = useGeolocation()

const { data: deliveries, pending, refresh } = await useAsyncData(
  'courier-deliveries',
  () => apiFetch<CourierSubOrderRead[]>('/orders/courier-deliveries'),
  { default: () => [], getCachedData: hydrateThenRefetch },
)

// Temps réel : toute notification reçue pendant que la page est ouverte
// (nouvelle affectation, statut d'une livraison…) relit la liste — la
// demande de livraison acceptée depuis la fenêtre la rafraîchit aussi
// (refreshNuxtData('courier-deliveries') dans DeliveryRequestModal).
const notifications = useNotificationStore()
watch(
  () => notifications.items[0]?.id,
  (id, previous) => {
    if (id && id !== previous) refresh()
  },
)
// Signal silencieux du serveur à chaque changement sur un de ses colis
// (affectation, expédition, dépôt au point, annulation…).
watch(() => notifications.deliveriesTick, () => refresh())
// Filet de sécurité si la connexion temps réel est coupée : relecture
// périodique et au retour sur l'onglet.
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

const { data: myCourier } = await useAsyncData(
  'courier-me-availability',
  () => apiFetch<CourierDetailRead>('/couriers/me'),
  { getCachedData: hydrateThenRefetch },
)
const isOnline = ref(false)
const togglingAvailability = ref(false)
watch(myCourier, (c) => { if (c) isOnline.value = c.is_online }, { immediate: true })

async function toggleAvailability(value: boolean) {
  togglingAvailability.value = true
  try {
    let position: { latitude: number; longitude: number } | null = null
    if (value) {
      try {
        position = await locate()
      } catch (e) {
        // Erreur de géolocalisation (message déjà en français, voir
        // useGeolocation) — distincte d'une erreur API, pas de fallback
        // générique à appliquer ici.
        toast.error(e instanceof Error ? e.message : 'Impossible de récupérer ta position.')
        isOnline.value = false
        return
      }
    }

    const updated = await apiFetch<CourierDetailRead>('/couriers/me/availability', {
      method: 'PATCH',
      body: value ? { is_online: true, latitude: position!.latitude, longitude: position!.longitude } : { is_online: false },
    })
    isOnline.value = updated.is_online
    if (value) toast.success('Tu es maintenant disponible pour recevoir des livraisons.')
  } catch (e) {
    isOnline.value = !value // repli visuel : l'appel a échoué, le switch ne doit pas rester sur la valeur non confirmée
    toast.error(apiErrorMessage(e, 'Impossible de mettre à jour ta disponibilité.'))
  } finally {
    togglingAvailability.value = false
  }
}

const scannerOpen = ref(false)

// La remise au client se confirme uniquement par scan de son QR (aucun
// bouton manuel — voir backend update_sub_order_status).
async function handleDecode(code: string) {
  try {
    const updated = await apiFetch<CourierSubOrderRead>('/orders/sub-orders/confirm-delivery', {
      method: 'POST',
      body: { code },
    })
    await refresh()
    toast.success(`Livraison confirmée — ${shortId(updated.order_id)}.`)
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

// Résumé d'une ligne plutôt que le détail de chaque article (nom + variante
// + quantité) : utile pour vérifier le colis au retrait, pas pour un simple
// coup d'œil sur la carte -- les deux ou trois premiers noms suffisent à
// reconnaître la commande.
function itemsSummary(so: CourierSubOrderRead): string {
  const names = so.items.map((i) => i.product_name)
  if (names.length <= 2) return names.join(', ')
  return `${names.slice(0, 2).join(', ')} +${names.length - 2}`
}

// La liste (toute l'historique assigné à ce livreur, jamais paginée côté
// API) devenait vite un long défilement une fois quelques dizaines de
// livraisons terminées accumulées — séparées en deux onglets comme
// commandes/index.vue (acheteur), "À livrer" reste court et concentré sur
// ce qui demande une action.
const tab = ref<'ongoing' | 'done'>('ongoing')
const ongoing = computed(() => deliveries.value.filter((so) => !['delivered', 'cancelled'].includes(so.status)))
const done = computed(() => deliveries.value.filter((so) => ['delivered', 'cancelled'].includes(so.status)))

// --- « À faire » -------------------------------------------------------------

// Étape d'une livraison en cours, vue du livreur.
type Stage = 'collect' | 'home' | 'point'
function stageOf(so: CourierSubOrderRead): Stage {
  if (so.status !== 'shipped') return 'collect'
  return so.delivery_type === 'pickup_point' ? 'point' : 'home'
}
const stageFilter = ref<Stage | null>(null)
const stageCounts = computed(() => {
  const counts: Record<Stage, number> = { collect: 0, home: 0, point: 0 }
  for (const so of ongoing.value) counts[stageOf(so)]++
  return counts
})

const walletAvailable = ref(0)
onMounted(async () => {
  try {
    const wallets = await apiFetch<WalletRead[]>('/wallets/mine')
    walletAvailable.value = wallets.find((w) => w.kind === 'courier')?.balance.available ?? 0
  } catch {
    walletAvailable.value = 0
  }
})

const todos = computed<TodoItem[]>(() => {
  const items: TodoItem[] = []
  if (myCourier.value?.status === 'approved' && !isOnline.value) {
    items.push({
      key: 'offline',
      title: 'Vous êtes hors ligne',
      text: 'Passez disponible pour recevoir de nouvelles courses.',
      icon: PhPower,
      hue: 355,
      urgent: true,
    })
  }
  const c = stageCounts.value
  const plural = (n: number, one: string, many: string) => (n > 1 ? many : one)
  if (c.collect)
    items.push({
      key: 'collect',
      count: c.collect,
      title: plural(c.collect, 'colis à récupérer', 'colis à récupérer'),
      text: 'En boutique : le vendeur vous le remet.',
      icon: PhStorefront,
      hue: 35,
      active: stageFilter.value === 'collect',
    })
  if (c.home)
    items.push({
      key: 'home',
      count: c.home,
      title: plural(c.home, 'livraison chez le client', 'livraisons chez les clients'),
      text: 'Scannez le QR du client à la remise.',
      icon: PhHouse,
      hue: 200,
      urgent: true,
      active: stageFilter.value === 'home',
    })
  if (c.point)
    items.push({
      key: 'point',
      count: c.point,
      title: plural(c.point, 'dépôt en point de retrait', 'dépôts en point de retrait'),
      text: 'Le gestionnaire scanne votre code de dépôt.',
      icon: PhWarehouse,
      hue: 270,
      active: stageFilter.value === 'point',
    })
  if (walletAvailable.value > 0)
    items.push({
      key: 'wallet',
      countLabel: formatGnf(walletAvailable.value),
      title: 'disponibles',
      text: 'Vos gains peuvent être retirés.',
      icon: PhWallet,
      hue: 150,
      to: '/livreur/gains',
    })
  return items
})

function onTodo(key: string) {
  if (key === 'offline') {
    toggleAvailability(true)
    return
  }
  const stage = key as Stage
  tab.value = 'ongoing'
  stageFilter.value = stageFilter.value === stage ? null : stage
}

// --- Partage de position en direct --------------------------------------------

// Tant que le livreur est en ligne avec au moins un colis en route et que cette
// page est ouverte, sa position est envoyée (au plus toutes les 15 s, ou dès
// qu'il a bougé d'environ 30 m) et relayée aux acheteurs concernés.
const shippedCount = computed(() => ongoing.value.filter((so) => so.status === 'shipped').length)
const sharing = computed(() => isOnline.value && shippedCount.value > 0)
const shareError = ref<string | null>(null)
const lastSentAt = ref<number | null>(null)
let watchId: number | null = null
let lastSent: { lat: number; lng: number; t: number } | null = null
const MIN_INTERVAL_MS = 15_000
const MIN_MOVE_KM = 0.03

function movedKm(a: { lat: number; lng: number }, b: { lat: number; lng: number }) {
  const rad = Math.PI / 180
  const x = (b.lng - a.lng) * rad * Math.cos(((a.lat + b.lat) / 2) * rad)
  const y = (b.lat - a.lat) * rad
  return Math.sqrt(x * x + y * y) * 6371
}

async function sendPosition(lat: number, lng: number) {
  const now = Date.now()
  if (lastSent && now - lastSent.t < MIN_INTERVAL_MS && movedKm(lastSent, { lat, lng }) < MIN_MOVE_KM) return
  lastSent = { lat, lng, t: now }
  try {
    await apiFetch('/couriers/me/position', { method: 'POST', body: { latitude: lat, longitude: lng } })
    lastSentAt.value = now
    shareError.value = null
  } catch {
    lastSent = null
  }
}

function startSharing() {
  if (watchId !== null || !('geolocation' in navigator)) return
  watchId = navigator.geolocation.watchPosition(
    (pos) => sendPosition(pos.coords.latitude, pos.coords.longitude),
    (err) => {
      shareError.value =
        err.code === err.PERMISSION_DENIED
          ? 'Localisation refusée : vos clients ne peuvent pas suivre leur colis.'
          : 'Position introuvable pour le moment.'
    },
    { enableHighAccuracy: true, maximumAge: 10_000, timeout: 20_000 },
  )
}

function stopSharing() {
  if (watchId !== null) navigator.geolocation.clearWatch(watchId)
  watchId = null
  lastSent = null
}

watch(sharing, (on) => (on ? startSharing() : stopSharing()))
onMounted(() => {
  if (sharing.value) startSharing()
})
onBeforeUnmount(stopSharing)

const search = ref('')
const visible = computed(() => {
  let list = tab.value === 'ongoing' ? ongoing.value : done.value
  if (tab.value === 'ongoing' && stageFilter.value) list = list.filter((so) => stageOf(so) === stageFilter.value)
  const query = search.value.trim().toLowerCase()
  if (!query) return list
  return list.filter((so) =>
    [shortId(so.order_id), so.shop_name, so.delivery_address, so.recipient_name ?? '']
      .join(' ')
      .toLowerCase()
      .includes(query),
  )
})
</script>

<template>
  <!-- Pas de .app-shell ici : layouts/livreur.vue en fournit déjà un (avec
       app-shell--catalog, voir ce fichier) -- un deuxième wrapper imbriqué
       ici replafonnerait à 720px, annulant l'élargissement du bandeau du
       haut. .livreur-inner recentre LE CONTENU sur une largeur confortable
       (même motif que .cart-inner, panier.vue) : les livraisons deviennent
       une vraie grille de cartes (auto-fill) plutôt qu'un unique bloc où
       tout s'empile dans un long défilement continu. -->
  <div class="livreur-inner" style="padding-bottom: 76px">
    <div class="px-4 pt-3">
      <section class="lv-hero" :class="{ 'lv-hero--online': isOnline }">
        <div class="lv-hero__main">
          <div class="d-flex align-center ga-2 flex-wrap">
            <h1 class="lv-hero__title">Mes livraisons</h1>
            <span v-if="myCourier?.status === 'approved'" class="lv-hero__chip">
              <PhCheckCircle :size="12" weight="fill" /> Approuvé
            </span>
          </div>
          <div class="lv-hero__stats">
            <span><strong>{{ ongoing.length }}</strong> à livrer</span>
            <span><strong>{{ done.length }}</strong> terminée{{ done.length > 1 ? 's' : '' }}</span>
          </div>
        </div>
        <button
          type="button"
          class="lv-toggle"
          :class="{ 'lv-toggle--on': isOnline }"
          :disabled="togglingAvailability || locating"
          :aria-pressed="isOnline"
          @click="toggleAvailability(!isOnline)"
        >
          <span class="lv-toggle__dot" />
          <span class="lv-toggle__text">
            <strong>{{ togglingAvailability || locating ? 'Un instant…' : isOnline ? 'En ligne' : 'Hors ligne' }}</strong>
            <small>{{ isOnline ? 'Toucher pour faire une pause' : 'Toucher pour recevoir des courses' }}</small>
          </span>
        </button>
      </section>

      <v-alert v-if="myCourier && myCourier.status !== 'approved'" type="warning" variant="tonal" density="compact" class="mb-3">
        <template v-if="myCourier.status === 'pending'">Ton profil est en cours de vérification par un administrateur.</template>
        <template v-else-if="myCourier.status === 'rejected'">Ton profil a été rejeté{{ myCourier.admin_note ? ` — ${myCourier.admin_note}` : '' }}.</template>
        <template v-else>Ton compte est suspendu.</template>
      </v-alert>

      <div v-if="sharing" class="share-banner" :class="{ 'share-banner--error': shareError }" role="status">
        <span class="share-banner__dot" />
        <span>
          <template v-if="shareError">{{ shareError }}</template>
          <template v-else>
            Position partagée en direct avec {{ shippedCount > 1 ? `${shippedCount} clients` : 'votre client' }}
            — gardez cette page ouverte pendant la course.
          </template>
        </span>
      </div>

      <section v-if="todos.length" class="mb-4" aria-label="À faire">
        <h2 class="todo-title">À faire</h2>
        <CommonTodoCards :items="todos" @select="onTodo" />
        <button v-if="stageFilter" type="button" class="stage-reset" @click="stageFilter = null">
          Afficher toutes les livraisons en cours
        </button>
      </section>

      <template v-if="!pending && deliveries.length > 0">
        <v-btn-toggle v-model="tab" mandatory density="comfortable" divided class="mb-3">
          <v-btn value="ongoing">À livrer ({{ ongoing.length }})</v-btn>
          <v-btn value="done">Terminées ({{ done.length }})</v-btn>
        </v-btn-toggle>

        <v-text-field
          v-model="search"
          placeholder="Rechercher par commande, boutique, adresse…"
          density="compact"
          variant="solo-filled"
          hide-details
          clearable
          class="livreur-search mb-4"
        >
          <template #prepend-inner>
            <PhMagnifyingGlass :size="16" color="var(--color-neutral-500)" />
          </template>
        </v-text-field>
      </template>

      <CommonEmptyState v-if="!pending && deliveries.length === 0" message="Aucune livraison assignée pour le moment." />
      <CommonEmptyState
        v-else-if="!pending && visible.length === 0"
        :message="tab === 'ongoing' ? 'Aucune livraison à livrer pour le moment.' : 'Aucune livraison ne correspond à cette recherche.'"
      />
    </div>

    <!-- À livrer : une carte par livraison, détail complet -- c'est ce qui
         demande une action. -->
    <div v-if="tab === 'ongoing'" class="px-4 deliveries-grid">
      <div v-for="so in visible" :key="so.id" class="delivery-card grid-card">
        <div class="d-flex justify-space-between align-center mb-2">
          <span class="delivery-card__code">{{ shortId(so.order_id) }}</span>
          <StatusBadge :status="so.status" />
        </div>
        <div class="mb-2">
          <span class="delivery-card__shop">{{ so.shop_name }}</span>
          <span class="delivery-card__date"> · {{ formatDate(so.created_at) }}</span>
        </div>

        <p v-if="stageOf(so) === 'collect'" class="delivery-card__next">
          <PhStorefront :size="14" /> À récupérer chez {{ so.shop_name }}
        </p>
        <div class="delivery-card__items mb-3">
          {{ so.items.length }} article{{ so.items.length > 1 ? 's' : '' }}
          <span class="delivery-card__items-list"> — {{ itemsSummary(so) }}</span>
        </div>

        <OrderDeliveryDetails
          class="mb-3"
          :zone="so.delivery_zone"
          :address="so.delivery_address"
          :instructions="so.delivery_instructions"
          :delivery-type="so.delivery_type"
          :recipient-name="so.recipient_name"
          :recipient-phone="so.recipient_phone"
          :pickup-point-contacts="so.pickup_point_contacts"
          :show-empty-manager-note="false"
        />

        <template v-if="so.status === 'shipped' && so.delivery_type === 'pickup_point'">
          <div v-if="so.dropoff_handoff_ready" class="qr-block mb-2">
            <div class="qr-block__label">
              <PhQrCode :size="15" weight="bold" />
              Code de dépôt — à faire scanner par le point
            </div>
            <OrderDeliveryQrCode :sub-order-id="so.id" />
          </div>
        </template>

        <div v-else-if="so.status === 'shipped'" class="d-flex ga-2">
          <v-btn color="primary" size="small" class="flex-grow-1" @click="scannerOpen = true">
            <PhQrCode :size="16" class="mr-1" />
            Scanner le QR du client
          </v-btn>
        </div>
      </div>
    </div>

    <!-- Terminées : cartes compactes, rien n'y est plus actionnable --
         inutile de réafficher l'adresse/les instructions complètes pour un
         historique. -->
    <div v-else class="px-4 deliveries-grid deliveries-grid--compact">
      <div v-for="so in visible" :key="so.id" class="delivery-card delivery-card--compact grid-card">
        <div class="d-flex justify-space-between align-center">
          <span class="delivery-card__code">{{ shortId(so.order_id) }}</span>
          <StatusBadge :status="so.status" />
        </div>
        <div class="mt-1">
          <span class="delivery-card__shop delivery-card__shop--compact">{{ so.shop_name }}</span>
          <span class="delivery-card__date"> · {{ formatDate(so.created_at) }} · {{ so.items.length }} article{{ so.items.length > 1 ? 's' : '' }}</span>
        </div>
      </div>
    </div>

    <VendorQrScannerDialog v-model="scannerOpen" @decode="handleDecode" />
  </div>
</template>

<style scoped>
.lv-hero {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 16px;
  padding: 18px 20px;
  border-radius: var(--radius-lg);
  background: linear-gradient(125deg, hsl(222 30% 28%), hsl(222 35% 18%));
  color: #fff;
  box-shadow: var(--shadow-md);
  transition: background 0.3s ease;
}

.lv-hero--online {
  background: linear-gradient(125deg, hsl(152 62% 36%), hsl(175 70% 28%));
}

.lv-hero__title {
  margin: 0;
  font-family: var(--font-heading);
  font-size: 20px;
  font-weight: 800;
  white-space: nowrap;
}

.lv-hero__chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgb(255 255 255 / 0.18);
  font-size: 11.5px;
  font-weight: 700;
}

.lv-hero__stats {
  display: flex;
  gap: 16px;
  margin-top: 6px;
  font-size: 13px;
  opacity: 0.9;
}

.lv-hero__stats strong {
  font-size: 16px;
  font-weight: 800;
}

.lv-toggle {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px 10px 12px;
  border: 0;
  border-radius: 999px;
  background: rgb(255 255 255 / 0.14);
  color: #fff;
  text-align: left;
  cursor: pointer;
  transition: background 0.2s ease;
}

.lv-toggle:hover {
  background: rgb(255 255 255 / 0.22);
}

.lv-toggle:disabled {
  opacity: 0.7;
  cursor: progress;
}

.lv-toggle__dot {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  border-radius: 50%;
  background: hsl(0 0% 70%);
  box-shadow: 0 0 0 4px rgb(255 255 255 / 0.15);
}

.lv-toggle--on .lv-toggle__dot {
  background: hsl(140 90% 60%);
  box-shadow: 0 0 0 4px rgb(120 255 170 / 0.3);
  animation: lv-pulse 1.8s ease-in-out infinite;
}

@keyframes lv-pulse {
  50% {
    box-shadow: 0 0 0 7px rgb(120 255 170 / 0.12);
  }
}

@media (prefers-reduced-motion: reduce) {
  .lv-toggle--on .lv-toggle__dot {
    animation: none;
  }
}

.lv-toggle__text {
  display: flex;
  flex-direction: column;
  line-height: 1.2;
}

.lv-toggle__text strong {
  font-size: 14px;
  font-weight: 800;
}

.lv-toggle__text small {
  font-size: 11.5px;
  opacity: 0.85;
}

/* .app-shell plafonne à 720px par défaut (voir main.css) -- trop étroit
   pour que la grille de cartes ci-dessous profite de plusieurs colonnes sur
   grand écran. Même largeur que .cart-inner (panier.vue). */
@media (min-width: 960px) {
  .livreur-inner {
    max-width: 1120px;
    margin: 0 auto;
  }
}

.deliveries-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 14px;
}

@media (min-width: 960px) {
  .deliveries-grid {
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 20px;
  }

  /* Cartes "Terminées" plus denses (pas de bouton/QR à loger) -- profitent
     d'une colonne plus étroite pour en montrer davantage à la fois. */
  .deliveries-grid--compact {
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 12px;
  }
}

.delivery-card {
  padding: 16px;
}

.delivery-card--compact {
  padding: 12px 14px;
}

/* Échelle de taille propre à cette page (plus généreuse que le reste de
   l'app) -- un livreur lit souvent son téléphone en extérieur, en plein
   soleil ou en mouvement : mieux vaut un texte trop grand que trop petit.
   Chaque rôle (numéro de commande / boutique / date / articles) a aussi sa
   propre couleur plutôt qu'un bloc de texte uniforme, pour repérer
   l'information voulue d'un coup d'œil. */
.delivery-card__code {
  font-family: var(--font-heading);
  font-weight: 700;
  font-size: 16px;
  letter-spacing: 0.01em;
  color: var(--color-primary-300);
}

.delivery-card__shop {
  font-family: var(--font-heading);
  font-weight: 700;
  font-size: 15px;
  color: var(--color-accent);
}

.delivery-card__shop--compact {
  font-size: 13.5px;
}

.delivery-card__date {
  font-size: 13px;
  color: var(--color-neutral-400);
}

.delivery-card__items {
  font-family: var(--font-heading);
  font-weight: 700;
  font-size: 15px;
  color: var(--color-success);
}

.delivery-card__items-list {
  font-family: var(--font-body);
  font-weight: 400;
  color: var(--color-neutral-400);
}

@media (min-width: 960px) {
  .delivery-card__code {
    font-size: 19px;
  }

  .delivery-card__shop {
    font-size: 17px;
  }

  .delivery-card__shop--compact {
    font-size: 14.5px;
  }

  .delivery-card__date {
    font-size: 14.5px;
  }

  .delivery-card__items {
    font-size: 17px;
  }

  .delivery-card__items-list {
    font-size: 14.5px;
  }
}

/* Boîte mise en valeur pour le code de dépôt (point de retrait) : c'est la
   seule action qui compte une fois le colis expédié dans ce cas -- un
   encart distinct plutôt qu'un QR nu, pour qu'il saute aux yeux dans la
   carte. */
.qr-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 14px;
  background: color-mix(in srgb, var(--color-primary) 7%, transparent);
  border: 1px solid var(--color-primary-800);
  border-radius: var(--radius-lg);
}

.qr-block__label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: var(--font-heading);
  font-weight: 700;
  font-size: 12.5px;
  text-align: center;
  color: var(--color-primary-300);
}

/* Le champ de recherche en variant="solo-filled" (voir template) se
   détache déjà du fond gris par son propre remplissage -- ce léger relief
   en plus le distingue mieux encore d'une simple ligne de texte. */
.livreur-search :deep(.v-field) {
  box-shadow: var(--shadow-sm);
}

.todo-title {
  font-family: var(--font-heading);
  font-size: 16px;
  font-weight: 800;
  margin: 8px 0 8px;
}

.stage-reset {
  margin-top: 8px;
  border: 0;
  background: none;
  padding: 0;
  color: var(--color-primary-300);
  font-size: 12.5px;
  font-weight: 700;
  cursor: pointer;
}

.delivery-card__next {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 8px;
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  background: hsl(35 85% var(--tint-bg));
  color: hsl(30 70% var(--tint-fg));
  font-size: 12.5px;
  font-weight: 700;
}

.share-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 8px 0 12px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  background: hsl(150 70% var(--tint-bg-soft));
  color: hsl(150 55% var(--tint-fg));
  font-size: 12.5px;
  font-weight: 600;
}

.share-banner--error {
  background: hsl(355 80% var(--tint-bg-soft));
  color: hsl(355 65% var(--tint-fg));
}

.share-banner__dot {
  width: 10px;
  height: 10px;
  flex-shrink: 0;
  border-radius: 50%;
  background: currentColor;
  animation: share-pulse 1.6s ease-in-out infinite;
}

@keyframes share-pulse {
  50% {
    opacity: 0.3;
    transform: scale(0.8);
  }
}
</style>
