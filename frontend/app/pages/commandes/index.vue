<script setup lang="ts">
import {
  PhArrowRight,
  PhFunnelSimple,
  PhImage,
  PhMagnifyingGlass,
  PhPackage,
  PhStar,
  PhStorefront,
  PhTruck,
  PhWarningCircle,
  PhX,
} from '@phosphor-icons/vue'
import type { OrderRead, OrderStatus, ReviewableProductRead, ReviewRead } from '~/types/api'

definePageMeta({ middleware: 'auth' })

const { apiFetch } = useApi()
const apiBase = useApiBase()
const route = useRoute()
const router = useRouter()

// Pas plus de 4 vignettes par commande — au-delà, "+N" : la carte reste un
// aperçu, le détail est à un clic (commandes/[id].vue).
const MAX_THUMBS = 4

const { data: orders, pending, error } = await useAsyncData('my-orders', () => apiFetch<OrderRead[]>('/orders'), {
  default: () => [],
})

// --- Produits à noter ---------------------------------------------------------
// Chaque produit reçu et pas encore noté — une étoile cliquée ouvre le
// formulaire avec cette note pré-sélectionnée.

const reviewable = useReviewableProducts()
const reviewTarget = ref<ReviewableProductRead | null>(null)
const reviewInitialRating = ref(0)
const reviewOpen = computed({
  get: () => reviewTarget.value !== null,
  set: (v: boolean) => {
    if (!v) reviewTarget.value = null
  },
})
function rateProduct(product: ReviewableProductRead, rating: number) {
  reviewInitialRating.value = rating
  reviewTarget.value = product
}
function onProductReviewed(review: ReviewRead) {
  reviewable.applyReview(review)
}

// --- Filtres -------------------------------------------------------------------
// Synchronisés avec l'URL (?q=…&statut=…&periode=…&tri=…) : un retour
// arrière depuis le détail d'une commande retrouve la même vue.

type StatusFilter = 'all' | 'ongoing' | 'pickup' | 'delivered' | 'cancelled'
type Period = 'all' | '30d' | '90d' | 'year'
type Sort = 'recent' | 'oldest' | 'amount_desc' | 'amount_asc'

const STATUS_FILTERS: { value: StatusFilter; label: string; match: (s: OrderStatus) => boolean }[] = [
  { value: 'all', label: 'Toutes', match: () => true },
  { value: 'ongoing', label: 'En cours', match: (s) => ['pending', 'confirmed', 'preparing', 'shipped'].includes(s) },
  { value: 'pickup', label: 'À récupérer', match: (s) => s === 'arrived_at_pickup_point' },
  { value: 'delivered', label: 'Livrées', match: (s) => s === 'delivered' },
  { value: 'cancelled', label: 'Annulées', match: (s) => s === 'cancelled' },
]
const PERIODS: { value: Period; title: string }[] = [
  { value: 'all', title: 'Toutes les dates' },
  { value: '30d', title: '30 derniers jours' },
  { value: '90d', title: '3 derniers mois' },
  { value: 'year', title: 'Cette année' },
]
const SORTS: { value: Sort; title: string }[] = [
  { value: 'recent', title: 'Plus récentes' },
  { value: 'oldest', title: 'Plus anciennes' },
  { value: 'amount_desc', title: 'Montant décroissant' },
  { value: 'amount_asc', title: 'Montant croissant' },
]

function queryValue<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  const value = route.query[key]
  return typeof value === 'string' && (allowed as readonly string[]).includes(value) ? (value as T) : fallback
}

const search = ref(typeof route.query.q === 'string' ? route.query.q : '')
const status = ref<StatusFilter>(queryValue('statut', STATUS_FILTERS.map((f) => f.value), 'all'))
const period = ref<Period>(queryValue('periode', PERIODS.map((p) => p.value), 'all'))
const sort = ref<Sort>(queryValue('tri', SORTS.map((s) => s.value), 'recent'))

watch([search, status, period, sort], () => {
  router.replace({
    query: {
      ...(search.value.trim() ? { q: search.value.trim() } : {}),
      ...(status.value !== 'all' ? { statut: status.value } : {}),
      ...(period.value !== 'all' ? { periode: period.value } : {}),
      ...(sort.value !== 'recent' ? { tri: sort.value } : {}),
    },
  })
})

const hasActiveFilters = computed(
  () => !!search.value.trim() || status.value !== 'all' || period.value !== 'all' || sort.value !== 'recent',
)
function resetFilters() {
  search.value = ''
  status.value = 'all'
  period.value = 'all'
  sort.value = 'recent'
}

function normalize(text: string) {
  return text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().trim()
}

function periodStart(p: Period): number | null {
  const now = new Date()
  if (p === '30d') return now.getTime() - 30 * 86_400_000
  if (p === '90d') return now.getTime() - 90 * 86_400_000
  if (p === 'year') return new Date(now.getFullYear(), 0, 1).getTime()
  return null
}

// Recherche : numéro de commande (avec ou sans « #GN- »), produit, variante, boutique.
const searchIndex = computed(
  () =>
    new Map(
      orders.value.map((o) => [
        o.id,
        normalize(
          [
            shortId(o.id),
            o.id.slice(0, 5),
            ...o.sub_orders.map((so) => so.shop_name),
            ...orderItems(o).flatMap((i) => [i.product_name, i.variant_label ?? '']),
          ].join(' '),
        ),
      ]),
    ),
)

// Compteurs par statut, calculés sur les autres filtres (recherche + période)
// pour que les pastilles disent combien de résultats chaque onglet donnerait.
const baseFiltered = computed(() => {
  const term = normalize(search.value).replace(/^#?gn-/, '')
  const since = periodStart(period.value)
  return orders.value.filter(
    (o) =>
      (!term || searchIndex.value.get(o.id)!.includes(term)) &&
      (since === null || new Date(o.created_at).getTime() >= since),
  )
})

const statusCounts = computed(
  () =>
    Object.fromEntries(
      STATUS_FILTERS.map((f) => [f.value, baseFiltered.value.filter((o) => f.match(o.status)).length]),
    ) as Record<StatusFilter, number>,
)

const visible = computed(() => {
  const matcher = STATUS_FILTERS.find((f) => f.value === status.value)!.match
  const list = baseFiltered.value.filter((o) => matcher(o.status))
  const byDate = (o: OrderRead) => new Date(o.created_at).getTime()
  const sorters: Record<Sort, (a: OrderRead, b: OrderRead) => number> = {
    recent: (a, b) => byDate(b) - byDate(a),
    oldest: (a, b) => byDate(a) - byDate(b),
    amount_desc: (a, b) => b.total - a.total,
    amount_asc: (a, b) => a.total - b.total,
  }
  return [...list].sort(sorters[sort.value])
})

// --- Présentation --------------------------------------------------------------

function orderItems(order: OrderRead) {
  return order.sub_orders.flatMap((so) => so.items)
}

// Un seul délai pour toute la commande (aperçu — voir commandes/[id].vue
// pour le délai par boutique) : la fourchette la plus large parmi les
// sous-commandes pas encore livrées/annulées.
function orderDeliveryEstimate(order: OrderRead): string | null {
  const open = order.sub_orders.filter(
    (so) => so.estimated_delivery_min && so.estimated_delivery_max && !['delivered', 'cancelled'].includes(so.status),
  )
  if (open.length === 0) return null
  const min = open.map((so) => so.estimated_delivery_min!).sort()[0]!
  const max = open.map((so) => so.estimated_delivery_max!).sort().at(-1)!
  return formatDeliveryEstimate(min, max)
}

function itemCount(order: OrderRead) {
  return order.sub_orders.reduce((sum, so) => sum + so.items.reduce((s, i) => s + i.quantity, 0), 0)
}
function orderTitle(order: OrderRead) {
  const items = orderItems(order)
  if (!items.length) return 'Commande'
  return items.length > 1 ? `${items[0]!.product_name} et ${items.length - 1} autre${items.length > 2 ? 's' : ''}` : items[0]!.product_name
}
function shopsLabel(order: OrderRead) {
  const names = [...new Set(order.sub_orders.map((so) => so.shop_name))]
  return names.length > 2 ? `${names.slice(0, 2).join(', ')} +${names.length - 2}` : names.join(', ')
}
function shortId(id: string) {
  return `#GN-${id.slice(0, 5).toUpperCase()}`
}
function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' })
}

// Liseré haut de carte, même code couleur que StatusBadge.
const statusAccent: Record<OrderStatus, string> = {
  pending: 'var(--color-neutral-500)',
  confirmed: 'var(--color-primary)',
  preparing: 'var(--color-primary)',
  shipped: 'rgb(var(--v-theme-info))',
  arrived_at_pickup_point: 'rgb(var(--v-theme-warning))',
  delivered: 'rgb(var(--v-theme-success))',
  cancelled: 'rgb(var(--v-theme-error))',
}
</script>

<template>
  <div class="orders-page">
    <header class="orders-head">
      <div>
        <h1 class="orders-head__title">Mes commandes</h1>
        <p class="orders-head__sub">
          {{ orders.length }} commande{{ orders.length > 1 ? 's' : '' }} au total
        </p>
      </div>
    </header>

    <!-- Produits reçus pas encore notés -->
    <section v-if="reviewable.toReview.value.length" class="to-review" aria-labelledby="to-review-title">
      <div class="to-review__head">
        <h2 id="to-review-title" class="to-review__title">
          <PhStar :size="18" weight="fill" color="var(--color-accent)" />
          Produits à noter
          <span class="to-review__count">{{ reviewable.toReview.value.length }}</span>
        </h2>
        <p class="to-review__sub">Votre avis aide les autres acheteurs et met en avant les bons produits.</p>
      </div>
      <div class="to-review__list">
        <div v-for="p in reviewable.toReview.value" :key="p.product_id" class="to-review__item">
          <NuxtLink :to="`/produits/${p.product_id}`" class="to-review__thumb">
            <img v-if="p.product_image" :src="resolveImageUrl(p.product_image, apiBase)" :alt="p.product_name" loading="lazy" />
            <PhImage v-else :size="20" weight="light" color="var(--color-neutral-500)" />
          </NuxtLink>
          <div class="to-review__info">
            <div class="to-review__name">{{ p.product_name }}</div>
            <div class="to-review__date">Reçu le {{ formatDate(p.delivered_at) }}</div>
            <div class="to-review__stars">
              <button
                v-for="n in 5"
                :key="n"
                type="button"
                class="to-review__star"
                :aria-label="`Donner ${n} étoile${n > 1 ? 's' : ''} à ${p.product_name}`"
                @click="rateProduct(p, n)"
              >
                <PhStar :size="20" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>

    <ProductReviewForm
      v-if="reviewTarget"
      v-model="reviewOpen"
      :product-id="reviewTarget.product_id"
      :product-name="reviewTarget.product_name"
      :product-image="reviewTarget.product_image"
      :initial-rating="reviewInitialRating"
      @submitted="onProductReviewed"
    />

    <!-- Barre de recherche et filtres -->
    <section class="toolbar" aria-label="Rechercher et filtrer">
      <div class="toolbar__row">
        <v-text-field
          v-model="search"
          placeholder="N° de commande, produit ou boutique…"
          density="comfortable"
          variant="outlined"
          hide-details
          clearable
          class="toolbar__search"
          aria-label="Rechercher une commande"
        >
          <template #prepend-inner>
            <PhMagnifyingGlass :size="18" color="var(--color-neutral-400)" />
          </template>
        </v-text-field>
        <v-select
          v-model="period"
          :items="PERIODS"
          density="comfortable"
          variant="outlined"
          hide-details
          class="toolbar__select"
          aria-label="Période"
        />
        <v-select
          v-model="sort"
          :items="SORTS"
          density="comfortable"
          variant="outlined"
          hide-details
          class="toolbar__select"
          aria-label="Trier par"
        >
          <template #prepend-inner>
            <PhFunnelSimple :size="16" color="var(--color-neutral-400)" />
          </template>
        </v-select>
      </div>

      <div class="toolbar__row toolbar__row--chips">
        <div class="chips" role="group" aria-label="Statut">
          <button
            v-for="f in STATUS_FILTERS"
            :key="f.value"
            type="button"
            class="chip"
            :class="{ 'chip--active': status === f.value }"
            :aria-pressed="status === f.value"
            @click="status = f.value"
          >
            {{ f.label }}
            <span class="chip__count">{{ statusCounts[f.value] }}</span>
          </button>
        </div>
        <div class="toolbar__meta">
          <span>{{ visible.length }} résultat{{ visible.length > 1 ? 's' : '' }}</span>
          <button v-if="hasActiveFilters" type="button" class="reset" @click="resetFilters">
            <PhX :size="13" weight="bold" /> Réinitialiser
          </button>
        </div>
      </div>
    </section>

    <div v-if="pending" class="orders-grid">
      <v-skeleton-loader v-for="n in 8" :key="n" type="article" class="skeleton" />
    </div>
    <CommonEmptyState
      v-else-if="error"
      :icon="PhWarningCircle"
      message="Impossible de charger vos commandes. Réessayez plus tard."
    />
    <CommonEmptyState v-else-if="orders.length === 0" :icon="PhPackage" message="Vous n'avez encore passé aucune commande." />
    <div v-else-if="visible.length === 0" class="no-result">
      <CommonEmptyState message="Aucune commande ne correspond à votre recherche." />
      <v-btn variant="tonal" color="primary" @click="resetFilters">Réinitialiser les filtres</v-btn>
    </div>

    <div v-else class="orders-grid">
      <NuxtLink
        v-for="order in visible"
        :key="order.id"
        :to="`/commandes/${order.id}`"
        class="order-card"
        :style="{ '--accent': statusAccent[order.status] }"
      >
        <div class="order-card__head">
          <div>
            <div class="order-card__id">{{ shortId(order.id) }}</div>
            <div class="order-card__date">{{ formatDate(order.created_at) }}</div>
          </div>
          <StatusBadge :status="order.status" />
        </div>

        <div class="order-card__thumbs">
          <div v-for="item in orderItems(order).slice(0, MAX_THUMBS)" :key="item.id" class="thumb">
            <img
              v-if="item.product_image"
              :src="resolveImageUrl(item.product_image, apiBase)"
              :alt="item.product_name"
              loading="lazy"
            />
            <PhImage v-else :size="18" weight="light" color="var(--color-neutral-500)" />
          </div>
          <div v-if="orderItems(order).length > MAX_THUMBS" class="thumb thumb--more">
            +{{ orderItems(order).length - MAX_THUMBS }}
          </div>
        </div>

        <div class="order-card__title">{{ orderTitle(order) }}</div>

        <ul class="order-card__facts">
          <li>
            <PhStorefront :size="15" />
            <span class="truncate">{{ shopsLabel(order) }}</span>
          </li>
          <li>
            <PhPackage :size="15" />
            <span>
              {{ itemCount(order) }} article{{ itemCount(order) > 1 ? 's' : '' }} ·
              {{ order.delivery_type === 'pickup_point' ? 'Point de retrait' : 'Livraison à domicile' }}
            </span>
          </li>
          <li v-if="orderDeliveryEstimate(order)" class="order-card__eta">
            <PhTruck :size="15" />
            <span>Estimée : <strong>{{ orderDeliveryEstimate(order) }}</strong></span>
          </li>
        </ul>

        <div class="order-card__foot">
          <div>
            <div class="order-card__total-label">Total</div>
            <div class="order-card__total">{{ formatGnf(order.total) }}</div>
          </div>
          <span class="order-card__cta">Détails <PhArrowRight :size="14" weight="bold" /></span>
        </div>
      </NuxtLink>
    </div>
  </div>
</template>

<style scoped>
/* Pas de .detail-card ici (plafonnée à 640px) : la grille a besoin de la
   largeur de l'écran — la route est en app-shell--catalog (layouts/default.vue). */
.orders-page {
  max-width: 1320px;
  margin: 0 auto;
  padding: 16px 16px 24px;
}

.orders-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: 16px;
}

.orders-head__title {
  margin: 0;
  font-family: var(--font-heading);
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--color-neutral-200);
}

.orders-head__sub {
  margin: 2px 0 0;
  font-size: 13.5px;
  color: var(--color-neutral-400);
}

/* --- Produits à noter ----------------------------------------------------- */

.to-review {
  margin-bottom: 20px;
  padding: 16px;
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider);
  border-left: 4px solid var(--color-accent);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
}

.to-review__head {
  margin-bottom: 12px;
}

.to-review__title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-family: var(--font-heading);
  font-size: 16px;
  font-weight: 800;
  color: var(--color-neutral-200);
}

.to-review__count {
  padding: 0 8px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-accent) 16%, transparent);
  color: var(--color-accent);
  font-size: 12.5px;
  line-height: 22px;
}

.to-review__sub {
  margin: 2px 0 0;
  font-size: 13px;
  color: var(--color-neutral-400);
}

/* Défilement horizontal : la bande garde une hauteur fixe quel que soit le
   nombre de produits à noter. */
.to-review__list {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding-bottom: 4px;
  scroll-snap-type: x proximity;
}

.to-review__item {
  display: flex;
  gap: 12px;
  flex: 0 0 290px;
  padding: 10px;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-md);
  scroll-snap-align: start;
}

.to-review__thumb {
  width: 64px;
  height: 64px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-sm);
  background: #fff;
}

.to-review__thumb img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.to-review__info {
  min-width: 0;
}

.to-review__name {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--color-neutral-200);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.to-review__date {
  font-size: 12px;
  color: var(--color-neutral-400);
}

.to-review__stars {
  display: flex;
  margin: 4px 0 0 -3px;
}

.to-review__star {
  display: flex;
  padding: 3px;
  border: none;
  background: none;
  color: var(--color-neutral-500);
  cursor: pointer;
  transition: color 0.12s ease, transform 0.12s ease;
}

/* Survol : l'étoile survolée et toutes celles à sa gauche s'allument. */
.to-review__stars:hover .to-review__star {
  color: var(--color-accent);
}

.to-review__stars .to-review__star:hover ~ .to-review__star {
  color: var(--color-neutral-500);
}

.to-review__star:hover {
  transform: scale(1.15);
}

@media (max-width: 560px) {
  .to-review__item {
    flex-basis: 260px;
  }
}

/* --- Barre d'outils ------------------------------------------------------- */

.toolbar {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  margin-bottom: 20px;
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
}

.toolbar__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.toolbar__search {
  flex: 1 1 320px;
}

.toolbar__select {
  flex: 0 1 210px;
  min-width: 170px;
}

.toolbar__row--chips {
  justify-content: space-between;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 34px;
  padding: 0 12px;
  border: 1px solid var(--color-divider-strong);
  border-radius: 999px;
  background: transparent;
  color: var(--color-neutral-300);
  font-family: var(--font-body);
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}

.chip:hover {
  background: var(--color-neutral-800);
}

.chip--active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: #fff;
}

.chip--active:hover {
  background: var(--color-primary-darken-1);
}

.chip__count {
  min-width: 20px;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--color-neutral-800);
  color: var(--color-neutral-300);
  font-size: 12px;
  line-height: 20px;
  text-align: center;
}

.chip--active .chip__count {
  background: rgb(255 255 255 / 22%);
  color: #fff;
}

.toolbar__meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  color: var(--color-neutral-400);
}

.reset {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: none;
  background: none;
  padding: 0;
  color: var(--color-primary-300);
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
}

.no-result {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

/* --- Grille --------------------------------------------------------------- */

/* 4 cartes par ligne sur grand écran, puis 3, 2, 1. */
.orders-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

@media (max-width: 1280px) {
  .orders-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}

@media (max-width: 960px) {
  .orders-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 560px) {
  .orders-grid { grid-template-columns: minmax(0, 1fr); }
  .toolbar__select { flex: 1 1 140px; min-width: 0; }
}

.skeleton {
  border-radius: var(--radius-lg);
}

.order-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider);
  border-top: 3px solid var(--accent);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  color: var(--color-neutral-200);
  text-decoration: none;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.order-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
  border-color: var(--color-divider-strong);
  border-top-color: var(--accent);
}

.order-card:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.order-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.order-card__id {
  font-family: var(--font-heading);
  font-size: 15.5px;
  font-weight: 800;
  letter-spacing: -0.01em;
  color: var(--color-neutral-200);
}

.order-card__date {
  margin-top: 1px;
  font-size: 12.5px;
  color: var(--color-neutral-400);
}

.order-card__thumbs {
  display: flex;
  gap: 8px;
}

.thumb {
  width: 52px;
  height: 52px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-sm);
  background: #fff;
}

.thumb img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.thumb--more {
  background: var(--color-neutral-800);
  color: var(--color-neutral-300);
  font-family: var(--font-heading);
  font-size: 13px;
  font-weight: 700;
}

.order-card__title {
  font-family: var(--font-heading);
  font-size: 14.5px;
  font-weight: 700;
  line-height: 1.35;
  color: var(--color-neutral-200);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.order-card__facts {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: 13px;
  color: var(--color-neutral-300);
}

.order-card__facts li {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}

.order-card__facts svg {
  flex: none;
  color: var(--color-neutral-400);
}

.order-card__eta strong {
  color: var(--color-neutral-200);
}

.truncate {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.order-card__foot {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin-top: auto;
  padding-top: 12px;
  border-top: 1px solid var(--color-divider);
}

.order-card__total-label {
  font-size: 11.5px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-neutral-400);
}

.order-card__total {
  font-family: var(--font-heading);
  font-size: 17px;
  font-weight: 800;
  color: var(--color-neutral-200);
  font-variant-numeric: tabular-nums;
}

.order-card__cta {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 700;
  color: var(--color-primary-300);
}

.order-card:hover .order-card__cta svg {
  transform: translateX(2px);
}

.order-card__cta svg {
  transition: transform 0.15s ease;
}
</style>
