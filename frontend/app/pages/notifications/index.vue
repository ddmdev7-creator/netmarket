<script setup lang="ts">
import {
  PhArrowsClockwise,
  PhBell,
  PhBellSlash,
  PhCaretRight,
  PhCheckCircle,
  PhChecks,
  PhCrown,
  PhHeart,
  PhMotorcycle,
  PhPackage,
  PhShoppingCart,
  PhStorefront,
  PhTrash,
  PhTrendDown,
  PhUserCircle,
  PhWarningCircle,
  PhX,
  PhXCircle,
} from '@phosphor-icons/vue'
import type { Component } from 'vue'
import type { NotificationRead, NotificationType } from '~/types/api'

definePageMeta({ middleware: 'auth', layout: 'focus' })

const router = useRouter()
const auth = useAuthStore()
const notifications = useNotificationStore()

onMounted(() => {
  notifications.fetchInitial()
})

// --- Présentation par type ------------------------------------------------------

type Category = 'orders' | 'deliveries' | 'deals' | 'account'

interface TypeMeta {
  icon: Component
  hue: number
  category: Category
}

const TYPE_META: Record<NotificationType, TypeMeta> = {
  order_received: { icon: PhPackage, hue: 215, category: 'orders' },
  order_status_changed: { icon: PhArrowsClockwise, hue: 215, category: 'orders' },
  delivery_request: { icon: PhMotorcycle, hue: 25, category: 'deliveries' },
  delivery_request_accepted: { icon: PhCheckCircle, hue: 150, category: 'deliveries' },
  delivery_no_courier_found: { icon: PhWarningCircle, hue: 355, category: 'deliveries' },
  favorite_price_drop: { icon: PhTrendDown, hue: 150, category: 'deals' },
  favorite_back_in_stock: { icon: PhHeart, hue: 345, category: 'deals' },
  cart_reminder: { icon: PhShoppingCart, hue: 260, category: 'deals' },
  courier_verification_approved: { icon: PhCheckCircle, hue: 150, category: 'account' },
  courier_verification_rejected: { icon: PhXCircle, hue: 355, category: 'account' },
  pickup_application_invited: { icon: PhStorefront, hue: 200, category: 'account' },
  pickup_application_submitted: { icon: PhStorefront, hue: 200, category: 'account' },
  pickup_application_approved: { icon: PhCheckCircle, hue: 150, category: 'account' },
  pickup_application_changes_requested: { icon: PhWarningCircle, hue: 38, category: 'account' },
  pickup_application_rejected: { icon: PhXCircle, hue: 355, category: 'account' },
  subscription_reminder: { icon: PhCrown, hue: 38, category: 'account' },
  subscription_update: { icon: PhCrown, hue: 270, category: 'account' },
}
const FALLBACK: TypeMeta = { icon: PhBell, hue: 220, category: 'account' }
// Changement de statut : icône et teinte selon l'étape annoncée dans le titre.
const STATUS_META: { match: RegExp; icon: Component; hue: number }[] = [
  { match: /annul/i, icon: PhXCircle, hue: 355 },
  { match: /livr/i, icon: PhCheckCircle, hue: 150 },
  { match: /point de retrait/i, icon: PhStorefront, hue: 38 },
  { match: /exp[ée]di/i, icon: PhMotorcycle, hue: 200 },
  { match: /pr[ée]paration/i, icon: PhPackage, hue: 30 },
  { match: /confirm/i, icon: PhCheckCircle, hue: 215 },
]
function meta(n: NotificationRead): TypeMeta {
  const base = TYPE_META[n.type] ?? FALLBACK
  if (n.type !== 'order_status_changed') return base
  const hit = STATUS_META.find((m) => m.match.test(n.title))
  return hit ? { ...base, icon: hit.icon, hue: hit.hue } : base
}

const CATEGORY_LABELS: Record<Category, { label: string; icon: Component }> = {
  orders: { label: 'Commandes', icon: PhPackage },
  deliveries: { label: 'Livraisons', icon: PhMotorcycle },
  deals: { label: 'Favoris & panier', icon: PhHeart },
  account: { label: 'Compte', icon: PhUserCircle },
}

// --- Destination et libellé d'action ----------------------------------------------

function target(n: NotificationRead): { path: string; label: string } | null {
  if (n.product_id) return { path: `/produits/${n.product_id}`, label: 'Voir le produit' }
  if (n.type === 'cart_reminder') return { path: '/panier', label: 'Voir mon panier' }
  if (n.type.startsWith('subscription_')) return { path: '/vendeur/abonnement', label: 'Voir mon abonnement' }
  if (n.type.startsWith('pickup_application')) {
    return auth.user?.role === 'admin'
      ? { path: '/admin/candidatures', label: 'Voir les candidatures' }
      : { path: '/point-retrait/candidature', label: 'Voir ma candidature' }
  }
  if (n.type === 'delivery_request' || n.type.startsWith('courier_verification')) {
    return { path: '/livreur', label: 'Ouvrir mon espace livreur' }
  }
  if (!n.order_id) return null
  if (auth.user?.role === 'vendor') return { path: `/vendeur/commandes?highlight=${n.order_id}`, label: 'Voir la commande' }
  if (auth.user?.role === 'admin') return { path: `/admin/commandes/${n.order_id}`, label: 'Voir la commande' }
  return { path: `/commandes/${n.order_id}`, label: 'Suivre la commande' }
}

async function open(n: NotificationRead) {
  await notifications.markRead(n.id)
  const t = target(n)
  if (t) router.push(t.path)
}

// --- Filtres ------------------------------------------------------------------------

type Filter = 'all' | 'unread' | Category
const filter = ref<Filter>('all')

// Seules les catégories présentes pour ce compte sont proposées.
const categories = computed(() => {
  const present = new Set(notifications.items.map((n) => meta(n).category))
  return (Object.keys(CATEGORY_LABELS) as Category[]).filter((c) => present.has(c))
})

const filtered = computed(() =>
  notifications.items.filter((n) => {
    if (filter.value === 'unread') return !n.read_at
    if (filter.value === 'all') return true
    return meta(n).category === filter.value
  }),
)

// --- Regroupement par date ----------------------------------------------------------

const now = ref(Date.now())
let ticker: ReturnType<typeof setInterval> | undefined
onMounted(() => (ticker = setInterval(() => (now.value = Date.now()), 60_000)))
onBeforeUnmount(() => clearInterval(ticker))

function startOfDay(t: number) {
  const d = new Date(t)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

const groups = computed(() => {
  const today = startOfDay(now.value)
  const yesterday = today - 86_400_000
  const week = today - 6 * 86_400_000
  const buckets: { key: string; label: string; items: NotificationRead[] }[] = [
    { key: 'today', label: "Aujourd'hui", items: [] },
    { key: 'yesterday', label: 'Hier', items: [] },
    { key: 'week', label: 'Cette semaine', items: [] },
    { key: 'older', label: 'Plus ancien', items: [] },
  ]
  for (const n of filtered.value) {
    const t = Date.parse(n.created_at)
    const bucket = t >= today ? 0 : t >= yesterday ? 1 : t >= week ? 2 : 3
    buckets[bucket]!.items.push(n)
  }
  return buckets.filter((b) => b.items.length)
})

function relativeTime(iso: string) {
  const diff = Math.max(0, now.value - Date.parse(iso))
  const minutes = Math.floor(diff / 60_000)
  if (minutes < 1) return "À l'instant"
  if (minutes < 60) return `Il y a ${minutes} min`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `Il y a ${hours} h`
  return new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

const readCount = computed(() => notifications.items.filter((n) => n.read_at).length)
const confirmClear = ref(false)
async function clearRead() {
  confirmClear.value = false
  await notifications.clearRead()
}
</script>

<template>
  <div class="nt">
    <header class="nt__head">
      <div>
        <h1 class="nt__title">
          Notifications
          <span v-if="notifications.unreadCount" class="nt__count">{{ notifications.unreadCount }}</span>
        </h1>
        <p class="nt__sub">
          {{
            notifications.unreadCount
              ? `${notifications.unreadCount} non lue${notifications.unreadCount > 1 ? 's' : ''}`
              : 'Vous êtes à jour'
          }}
        </p>
      </div>
      <div class="nt__actions">
        <v-btn v-if="notifications.unreadCount" variant="tonal" color="primary" size="small" @click="notifications.markAllRead()">
          <PhChecks :size="16" class="mr-1" /> Tout marquer lu
        </v-btn>
        <v-btn v-if="readCount" variant="text" size="small" @click="confirmClear = true">
          <PhTrash :size="16" class="mr-1" /> Vider les lues
        </v-btn>
      </div>
    </header>

    <nav v-if="notifications.items.length" class="nt__filters" aria-label="Filtrer les notifications">
      <button type="button" class="nt-chip" :class="{ 'is-active': filter === 'all' }" @click="filter = 'all'">
        Toutes <span>{{ notifications.items.length }}</span>
      </button>
      <button type="button" class="nt-chip" :class="{ 'is-active': filter === 'unread' }" @click="filter = 'unread'">
        Non lues <span>{{ notifications.unreadCount }}</span>
      </button>
      <button
        v-for="c in categories"
        :key="c"
        type="button"
        class="nt-chip"
        :class="{ 'is-active': filter === c }"
        @click="filter = c"
      >
        <component :is="CATEGORY_LABELS[c].icon" :size="15" /> {{ CATEGORY_LABELS[c].label }}
      </button>
    </nav>

    <CommonEmptyState
      v-if="!notifications.items.length"
      title="Rien de neuf"
      message="Vous serez prévenu ici de l'avancement de vos commandes, de vos livraisons et des baisses de prix de vos favoris."
      :icon="PhBellSlash"
    />
    <CommonEmptyState
      v-else-if="!filtered.length"
      title="Aucune notification ici"
      :message="filter === 'unread' ? 'Toutes vos notifications sont lues.' : 'Rien dans cette catégorie pour le moment.'"
      :icon="PhCheckCircle"
      :hue="150"
    />

    <section v-for="group in groups" :key="group.key" class="nt__group">
      <h2 class="nt__group-title">{{ group.label }}</h2>
      <TransitionGroup tag="ul" name="nt-row" class="nt__list">
        <li v-for="n in group.items" :key="n.id" class="nt-row" :class="{ 'is-unread': !n.read_at }" :style="{ '--hue': meta(n).hue }">
          <button type="button" class="nt-row__main" @click="open(n)">
            <span class="nt-row__icon"><component :is="meta(n).icon" :size="20" weight="duotone" /></span>
            <span class="nt-row__body">
              <span class="nt-row__top">
                <span class="nt-row__title">{{ n.title }}</span>
                <span class="nt-row__time">{{ relativeTime(n.created_at) }}</span>
              </span>
              <span class="nt-row__text">{{ n.body }}</span>
              <span v-if="target(n)" class="nt-row__cta">{{ target(n)!.label }} <PhCaretRight :size="12" weight="bold" /></span>
            </span>
            <span v-if="!n.read_at" class="nt-row__dot" aria-label="Non lue" />
          </button>
          <button type="button" class="nt-row__delete" aria-label="Supprimer cette notification" @click="notifications.remove(n.id)">
            <PhX :size="15" />
          </button>
        </li>
      </TransitionGroup>
    </section>

    <v-dialog v-model="confirmClear" max-width="360">
      <v-card class="pa-5">
        <div class="text-subtitle-1 mb-2">Supprimer les notifications lues ?</div>
        <p class="text-muted mb-4" style="font-size: 13px">
          {{ readCount }} notification{{ readCount > 1 ? 's' : '' }} lue{{ readCount > 1 ? 's' : '' }} seront supprimées. Les non lues sont conservées.
        </p>
        <div class="d-flex ga-2">
          <v-btn variant="outlined" class="flex-grow-1" @click="confirmClear = false">Annuler</v-btn>
          <v-btn color="error" class="flex-grow-1" @click="clearRead">Supprimer</v-btn>
        </div>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.nt {
  max-width: 860px;
  margin: 0 auto;
  padding: 16px 12px 40px;
}

@media (min-width: 960px) {
  .nt {
    padding: 28px 24px 48px;
  }
}

.nt__head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 14px;
}

.nt__title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0;
  font-family: var(--font-heading);
  font-size: 24px;
  font-weight: 800;
}

.nt__count {
  min-width: 26px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--color-error);
  color: #fff;
  font-size: 13px;
  text-align: center;
}

.nt__sub {
  margin: 2px 0 0;
  font-size: 13px;
  color: var(--color-neutral-400);
}

.nt__actions {
  display: flex;
  gap: 6px;
}

.nt__filters {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  scrollbar-width: none;
  margin: 0 -12px 18px;
  padding: 2px 12px;
}

.nt__filters::-webkit-scrollbar {
  display: none;
}

.nt-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  height: 36px;
  padding: 0 14px;
  border: 1px solid var(--color-divider-strong);
  border-radius: 999px;
  background: var(--color-neutral-900);
  color: var(--color-neutral-300);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.nt-chip span {
  min-width: 20px;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--color-neutral-800);
  font-size: 11.5px;
  line-height: 20px;
  text-align: center;
}

.nt-chip.is-active {
  border-color: var(--color-primary);
  background: var(--color-primary);
  color: #fff;
}

.nt-chip.is-active span {
  background: rgb(255 255 255 / 22%);
}

.nt__group + .nt__group {
  margin-top: 18px;
}

.nt__group-title {
  margin: 0 0 8px 4px;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--color-neutral-500);
}

.nt__list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.nt-row {
  position: relative;
  display: flex;
  align-items: stretch;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-divider);
  background: var(--color-neutral-900);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
  transition: box-shadow 0.15s ease, border-color 0.15s ease;
}

.nt-row:hover {
  box-shadow: var(--shadow-md);
  border-color: hsl(var(--hue) 50% 60% / 0.5);
}

.nt-row.is-unread {
  background: color-mix(in srgb, hsl(var(--hue) 80% 55%) 6%, var(--color-neutral-900));
  border-color: hsl(var(--hue) 60% 55% / 0.35);
}

.nt-row.is-unread::before {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 4px;
  background: hsl(var(--hue) 70% 52%);
}

.nt-row__main {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  flex: 1;
  min-width: 0;
  padding: 14px 8px 14px 16px;
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.nt-row__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  flex-shrink: 0;
  border-radius: 13px;
  background: hsl(var(--hue) 70% var(--tint-bg));
  color: hsl(var(--hue) 60% var(--tint-fg));
}

.nt-row__body {
  display: flex;
  flex-direction: column;
  gap: 3px;
  flex: 1;
  min-width: 0;
}

.nt-row__top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.nt-row__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-neutral-200);
}

.nt-row.is-unread .nt-row__title {
  font-weight: 800;
}

.nt-row__time {
  flex-shrink: 0;
  font-size: 11.5px;
  color: var(--color-neutral-500);
}

.nt-row__text {
  font-size: 13px;
  line-height: 1.45;
  color: var(--color-neutral-400);
}

.nt-row__cta {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-top: 4px;
  font-size: 12.5px;
  font-weight: 700;
  color: hsl(var(--hue) 65% var(--tint-fg));
}

.nt-row__dot {
  width: 10px;
  height: 10px;
  flex-shrink: 0;
  margin-top: 6px;
  border-radius: 50%;
  background: hsl(var(--hue) 75% 52%);
  box-shadow: 0 0 0 3px hsl(var(--hue) 70% var(--tint-bg));
}

.nt-row__delete {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  width: 40px;
  padding-top: 14px;
  flex-shrink: 0;
  border: 0;
  background: none;
  color: var(--color-neutral-500);
  cursor: pointer;
  opacity: 0.6;
  transition: opacity 0.15s ease, color 0.15s ease;
}

.nt-row:hover .nt-row__delete {
  opacity: 1;
}

.nt-row__delete:hover {
  color: var(--color-error);
}

.nt-row-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.nt-row-leave-to {
  opacity: 0;
  transform: translateX(24px);
}
</style>
