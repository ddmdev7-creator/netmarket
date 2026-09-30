<script setup lang="ts">
import {
  PhArrowSquareOut,
  PhCheckCircle,
  PhDotsThreeVertical,
  PhEyeSlash,
  PhImage,
  PhListBullets,
  PhMagnifyingGlass,
  PhMinus,
  PhPackage,
  PhPencilSimple,
  PhPlus,
  PhSquaresFour,
  PhStack,
  PhStar,
  PhTrash,
  PhWarning,
  PhWarningCircle,
  PhX,
} from '@phosphor-icons/vue'
import type { Component } from 'vue'
import type {
  CategoryRead,
  MyProductsSummary,
  Page,
  ProductRead,
  ProductSort,
  ProductStatus,
  StockLevel,
  VendorRead,
} from '~/types/api'

definePageMeta({ middleware: 'vendor', layout: 'vendeur' })

const { apiFetch } = useApi()
const route = useRoute()
const apiBase = useApiBase()
const toast = useToastStore()
const pageSize = 24
const LOW_STOCK = 5

// getCachedData: hydrateThenRefetch — voir app/pages/vendeur/index.vue : sans
// ça, revenir sur cet onglet ré-afficherait un stock/statut périmé.
const { data: vendor } = await useAsyncData('vendor-me-products-page', () => apiFetch<VendorRead>('/vendors/me'), {
  getCachedData: hydrateThenRefetch,
})
const { data: categories } = await useAsyncData('vendor-products-categories', () => apiFetch<CategoryRead[]>('/categories'), {
  default: () => [],
})
// Quota de produits en vente de la formule (null = illimité).
const { overview: plan, planName } = useVendorPlan()
const productLimit = computed(() => plan.value?.products.limit ?? null)

const { data: summary, refresh: refreshSummary } = await useAsyncData(
  'vendor-products-summary',
  () => apiFetch<MyProductsSummary>('/products/me/summary'),
  { getCachedData: hydrateThenRefetch },
)

// --- Filtres ------------------------------------------------------------------

// Une seule « vue » à la fois, portée par les tuiles du haut.
type View = 'all' | 'active' | 'inactive' | 'low' | 'out'
const initialView: View = route.query.stock === 'out' ? 'out' : route.query.stock === 'low' ? 'low' : 'all'
const view = ref<View>(initialView)
const search = ref('')
const categoryFilter = ref<string | null>(null)
const sort = ref<ProductSort>('recent')
const SORTS: { value: ProductSort; title: string }[] = [
  { value: 'recent', title: 'Plus récents' },
  { value: 'stock_asc', title: 'Stock le plus bas' },
  { value: 'price_asc', title: 'Prix croissant' },
  { value: 'price_desc', title: 'Prix décroissant' },
]

const tiles = computed<{ value: View; label: string; count: number; icon: Component; hue: number }[]>(() => {
  const s = summary.value
  return [
    { value: 'all', label: 'Tous', count: s?.total ?? 0, icon: PhStack, hue: 220 },
    { value: 'active', label: 'En vente', count: s?.active ?? 0, icon: PhCheckCircle, hue: 150 },
    { value: 'inactive', label: 'Masqués', count: s?.inactive ?? 0, icon: PhEyeSlash, hue: 250 },
    { value: 'low', label: 'Stock faible', count: s?.low_stock ?? 0, icon: PhWarningCircle, hue: 38 },
    { value: 'out', label: 'Rupture', count: s?.out_of_stock ?? 0, icon: PhWarning, hue: 355 },
  ]
})

const page = ref(1)
const emptyPage: Page<ProductRead> = { items: [], total: 0, page: 1, page_size: pageSize, pages: 0 }
const {
  data: productsPage,
  pending,
  refresh,
} = await useAsyncData(
  'vendor-my-products',
  () => {
    const status: ProductStatus | undefined =
      view.value === 'active' ? 'active' : view.value === 'inactive' ? 'inactive' : undefined
    const stockLevel: StockLevel | undefined = view.value === 'low' || view.value === 'out' ? view.value : undefined
    return apiFetch<Page<ProductRead>>('/products/me', {
      query: {
        page: page.value,
        page_size: pageSize,
        category_id: categoryFilter.value ?? undefined,
        status,
        stock_level: stockLevel,
        q: search.value.trim() || undefined,
        sort: sort.value,
      },
    })
  },
  { default: () => emptyPage, getCachedData: hydrateThenRefetch },
)

const products = computed(() => productsPage.value?.items ?? [])
const total = computed(() => productsPage.value?.total ?? 0)
const pageCount = computed(() => Math.max(1, productsPage.value?.pages ?? 1))
watch(page, () => refresh())

function applyFilters() {
  page.value = 1
  refresh()
}

function selectView(value: View) {
  view.value = value
  applyFilters()
}

let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(search, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(applyFilters, 300)
})

const hasFilters = computed(() => view.value !== 'all' || !!search.value.trim() || !!categoryFilter.value)
function resetFilters() {
  view.value = 'all'
  search.value = ''
  categoryFilter.value = null
  applyFilters()
}

// --- Affichage grille / liste (mémorisé sur l'appareil) ------------------------

const DISPLAY_KEY = 'nm-vendor-products-display'
const display = ref<'grid' | 'list'>('grid')
onMounted(() => {
  try {
    const saved = localStorage.getItem(DISPLAY_KEY)
    if (saved === 'grid' || saved === 'list') display.value = saved
    else if (window.innerWidth < 600) display.value = 'list'
  } catch {
    // Stockage indisponible : grille par défaut.
  }
})
function setDisplay(value: 'grid' | 'list') {
  display.value = value
  try {
    localStorage.setItem(DISPLAY_KEY, value)
  } catch {
    // Sans stockage, le choix n'est simplement pas mémorisé.
  }
}

// --- Présentation d'un produit ----------------------------------------------

function priceInfo(p: ProductRead) {
  const prices = p.variants.map((v) => v.price ?? p.price)
  if (!prices.length) return { min: p.price, varies: false }
  const min = Math.min(...prices)
  return { min, varies: min !== Math.max(...prices) }
}

function stockTone(stock: number): 'out' | 'low' | 'ok' {
  if (stock === 0) return 'out'
  return stock <= LOW_STOCK ? 'low' : 'ok'
}

function stockLabel(stock: number) {
  if (stock === 0) return 'Rupture'
  return `${stock} en stock`
}

function categoryName(id: string) {
  return categories.value.find((c) => c.id === id)?.name ?? ''
}

const canPublish = computed(() => vendor.value?.status === 'approved')

// --- Actions directes -----------------------------------------------------------

function replaceProduct(updated: ProductRead) {
  if (!productsPage.value) return
  productsPage.value = {
    ...productsPage.value,
    items: productsPage.value.items.map((p) => (p.id === updated.id ? updated : p)),
  }
}

const busy = ref<Set<string>>(new Set())
function setBusy(id: string, on: boolean) {
  const next = new Set(busy.value)
  if (on) next.add(id)
  else next.delete(id)
  busy.value = next
}

async function toggleStatus(p: ProductRead) {
  const status: ProductStatus = p.status === 'active' ? 'inactive' : 'active'
  setBusy(p.id, true)
  try {
    replaceProduct(await apiFetch<ProductRead>(`/products/${p.id}`, { method: 'PATCH', body: { status } }))
    toast.success(status === 'active' ? 'Produit remis en vente.' : 'Produit masqué de la boutique.')
    refreshSummary()
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de changer le statut.'))
  } finally {
    setBusy(p.id, false)
  }
}

// Stock ajusté par −/+ : affiché tout de suite, enregistré après une courte
// pause (plusieurs appuis = un seul appel).
const pendingStock = ref<Record<string, number>>({})
const stockTimers = new Map<string, ReturnType<typeof setTimeout>>()

function displayedStock(p: ProductRead) {
  return pendingStock.value[p.id] ?? p.stock
}

function bumpStock(p: ProductRead, delta: number) {
  const next = Math.max(0, displayedStock(p) + delta)
  pendingStock.value = { ...pendingStock.value, [p.id]: next }
  clearTimeout(stockTimers.get(p.id))
  stockTimers.set(
    p.id,
    setTimeout(() => saveStock(p.id, next), 700),
  )
}

async function saveStock(id: string, stock: number) {
  setBusy(id, true)
  try {
    replaceProduct(await apiFetch<ProductRead>(`/products/${id}`, { method: 'PATCH', body: { stock } }))
    refreshSummary()
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'enregistrer le stock."))
  } finally {
    const rest = { ...pendingStock.value }
    delete rest[id]
    pendingStock.value = rest
    setBusy(id, false)
  }
}

onBeforeUnmount(() => {
  clearTimeout(searchTimer)
  for (const t of stockTimers.values()) clearTimeout(t)
})

const confirmDelete = ref<ProductRead | null>(null)
const deleting = ref(false)
async function deleteProduct() {
  if (!confirmDelete.value) return
  deleting.value = true
  try {
    await apiFetch(`/products/${confirmDelete.value.id}`, { method: 'DELETE' })
    toast.success('Produit supprimé.')
    confirmDelete.value = null
    await Promise.all([refresh(), refreshSummary()])
  } catch (e) {
    toast.error(
      apiErrorMessage(
        e,
        'Impossible de supprimer ce produit — il figure sans doute déjà dans une commande. Masquez-le plutôt.',
      ),
    )
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <div class="vp">
    <header class="vp__head">
      <div>
        <h1 class="vp__title">Mes produits</h1>
        <p class="vp__sub">
          <template v-if="summary">
            {{ summary.total }} produit{{ summary.total > 1 ? 's' : '' }} · {{ summary.active }} en vente
          </template>
        </p>
        <NuxtLink v-if="summary && productLimit !== null" to="/vendeur/abonnement" class="vp-quota" :class="{ 'vp-quota--full': summary.active >= productLimit }">
          <span class="vp-quota__bar"><span :style="{ width: `${Math.min(100, (summary.active / Math.max(1, productLimit)) * 100)}%` }" /></span>
          <span>{{ summary.active }} / {{ productLimit }} en vente · formule {{ planName }}</span>
        </NuxtLink>
      </div>
      <v-btn
        :to="canPublish ? '/vendeur/produits/nouveau' : undefined"
        :disabled="!canPublish"
        color="primary"
        class="vp__new"
      >
        <PhPlus :size="16" weight="bold" class="mr-1" />
        Nouveau produit
      </v-btn>
    </header>

    <v-alert v-if="vendor && !canPublish" type="warning" variant="tonal" density="compact" class="mb-4">
      Ta boutique doit être approuvée par un administrateur avant de publier des produits.
    </v-alert>

    <div class="vp__tiles" role="group" aria-label="Filtrer mes produits">
      <button
        v-for="t in tiles"
        :key="t.value"
        type="button"
        class="vp-tile"
        :class="{ 'is-active': view === t.value, 'is-alert': (t.value === 'out' || t.value === 'low') && t.count > 0 }"
        :style="{ '--hue': t.hue }"
        :aria-pressed="view === t.value"
        @click="selectView(t.value)"
      >
        <span class="vp-tile__icon"><component :is="t.icon" :size="18" weight="duotone" /></span>
        <span class="vp-tile__count">{{ t.count }}</span>
        <span class="vp-tile__label">{{ t.label }}</span>
      </button>
    </div>

    <div class="vp__toolbar">
      <label class="vp-search">
        <PhMagnifyingGlass :size="17" />
        <input v-model="search" type="search" placeholder="Rechercher un produit…" aria-label="Rechercher un produit" />
        <button v-if="search" type="button" aria-label="Effacer" @click="search = ''"><PhX :size="13" weight="bold" /></button>
      </label>
      <v-select
        v-model="categoryFilter"
        :items="categories"
        item-title="name"
        item-value="id"
        placeholder="Toutes catégories"
        density="compact"
        variant="outlined"
        hide-details
        clearable
        class="vp__select"
        @update:model-value="applyFilters"
      />
      <v-select
        v-model="sort"
        :items="SORTS"
        item-title="title"
        item-value="value"
        density="compact"
        variant="outlined"
        hide-details
        class="vp__select vp__select--sort"
        @update:model-value="applyFilters"
      />
      <div class="vp-display" role="group" aria-label="Affichage">
        <button type="button" :class="{ 'is-active': display === 'grid' }" aria-label="Grille" @click="setDisplay('grid')">
          <PhSquaresFour :size="18" />
        </button>
        <button type="button" :class="{ 'is-active': display === 'list' }" aria-label="Liste" @click="setDisplay('list')">
          <PhListBullets :size="18" />
        </button>
      </div>
    </div>

    <div v-if="hasFilters && !pending" class="vp__result">
      {{ total }} résultat{{ total > 1 ? 's' : '' }}
      <button type="button" @click="resetFilters">Réinitialiser</button>
    </div>

    <div v-if="pending && !products.length" class="vp-grid">
      <v-skeleton-loader v-for="n in 6" :key="n" type="card" />
    </div>

    <CommonEmptyState
      v-else-if="!products.length && !hasFilters"
      :icon="PhPackage"
      title="Aucun produit pour l'instant"
      message="Ajoutez votre premier produit : quelques minutes suffisent, avec un aperçu avant publication."
      :action-label="canPublish ? 'Ajouter un produit' : undefined"
      :action-to="canPublish ? '/vendeur/produits/nouveau' : undefined"
    />
    <CommonEmptyState
      v-else-if="!products.length"
      :icon="PhMagnifyingGlass"
      title="Aucun produit trouvé"
      message="Essayez un autre mot ou retirez un filtre."
    >
      <v-btn variant="tonal" color="primary" class="mt-2" @click="resetFilters">Réinitialiser les filtres</v-btn>
    </CommonEmptyState>

    <div v-else :class="display === 'grid' ? 'vp-grid' : 'vp-list'">
      <article
        v-for="p in products"
        :key="p.id"
        class="vp-card"
        :class="[`vp-card--${display}`, { 'is-hidden': p.status !== 'active', 'is-busy': busy.has(p.id) }]"
      >
        <NuxtLink :to="`/vendeur/produits/${p.id}`" class="vp-card__media" :aria-label="`Modifier ${p.name}`">
          <img
            v-if="p.images[0]"
            :src="resolveImageUrl(p.images[0], apiBase, display === 'grid' ? 480 : 160)"
            :alt="p.name"
            loading="lazy"
          />
          <PhImage v-else :size="28" weight="light" />
          <span v-if="p.status !== 'active'" class="vp-card__flag"><PhEyeSlash :size="12" /> Masqué</span>
        </NuxtLink>

        <div class="vp-card__body">
          <NuxtLink :to="`/vendeur/produits/${p.id}`" class="vp-card__name">{{ p.name }}</NuxtLink>
          <div class="vp-card__meta">
            <span v-if="categoryName(p.category_id)">{{ categoryName(p.category_id) }}</span>
            <span v-if="p.variants.length">· {{ p.variants.length }} variante{{ p.variants.length > 1 ? 's' : '' }}</span>
          </div>
          <div class="vp-card__price">
            <small v-if="priceInfo(p).varies">dès</small>
            {{ formatGnf(priceInfo(p).min) }}
          </div>
          <div class="vp-card__stats">
            <span class="vp-stock" :class="`vp-stock--${stockTone(displayedStock(p))}`">
              {{ stockLabel(displayedStock(p)) }}
            </span>
            <span v-if="p.review_count" class="vp-card__stat">
              <PhStar :size="12" weight="fill" /> {{ p.average_rating?.toFixed(1).replace('.', ',') }}
            </span>
            <span v-if="summary?.sold[p.id]" class="vp-card__stat">{{ summary.sold[p.id] }} vendu{{ summary.sold[p.id]! > 1 ? 's' : '' }}</span>
          </div>
        </div>

        <div class="vp-card__actions">
          <div v-if="!p.variants.length" class="vp-stepper" :aria-label="`Stock de ${p.name}`">
            <button type="button" :disabled="displayedStock(p) === 0" aria-label="Retirer 1 du stock" @click="bumpStock(p, -1)">
              <PhMinus :size="14" weight="bold" />
            </button>
            <span>{{ displayedStock(p) }}</span>
            <button type="button" aria-label="Ajouter 1 au stock" @click="bumpStock(p, 1)">
              <PhPlus :size="14" weight="bold" />
            </button>
          </div>
          <NuxtLink v-else :to="`/vendeur/produits/${p.id}`" class="vp-card__variants">Stock par variante</NuxtLink>

          <label class="vp-card__sale" :class="{ 'is-on': p.status === 'active' }">
            <span>{{ p.status === 'active' ? 'En vente' : 'Masqué' }}</span>
          <v-switch
            :model-value="p.status === 'active'"
            color="success"
            density="compact"
            hide-details
            inset
            class="vp-card__switch"
            :disabled="busy.has(p.id)"
            :aria-label="p.status === 'active' ? 'En vente — masquer' : 'Masqué — remettre en vente'"
            :title="p.status === 'active' ? 'En vente' : 'Masqué'"
            @update:model-value="toggleStatus(p)"
          />
          </label>

          <v-menu location="bottom end">
            <template #activator="{ props: menuProps }">
              <button v-bind="menuProps" type="button" class="vp-card__more" :aria-label="`Plus d'actions pour ${p.name}`">
                <PhDotsThreeVertical :size="18" weight="bold" />
              </button>
            </template>
            <v-list density="compact" min-width="200">
              <v-list-item :to="`/vendeur/produits/${p.id}`">
                <template #prepend><PhPencilSimple :size="16" class="mr-3" /></template>
                Modifier
              </v-list-item>
              <v-list-item :href="`/produits/${p.id}`" target="_blank">
                <template #prepend><PhArrowSquareOut :size="16" class="mr-3" /></template>
                Voir sur le marché
              </v-list-item>
              <v-list-item base-color="error" @click="confirmDelete = p">
                <template #prepend><PhTrash :size="16" class="mr-3" /></template>
                Supprimer
              </v-list-item>
            </v-list>
          </v-menu>
        </div>
      </article>
    </div>

    <v-pagination v-if="pageCount > 1" v-model="page" :length="pageCount" density="compact" class="mt-4" />

    <v-dialog :model-value="!!confirmDelete" max-width="360" @update:model-value="(v) => !v && (confirmDelete = null)">
      <v-card v-if="confirmDelete" class="pa-5">
        <div class="text-subtitle-1 mb-2">Supprimer « {{ confirmDelete.name }} » ?</div>
        <p class="text-muted mb-4" style="font-size: 13px">
          Cette action est définitive. Pour le retirer temporairement de la vente, masquez-le plutôt.
        </p>
        <div class="d-flex ga-2">
          <v-btn variant="outlined" class="flex-grow-1" @click="confirmDelete = null">Annuler</v-btn>
          <v-btn color="error" class="flex-grow-1" :loading="deleting" @click="deleteProduct">Supprimer</v-btn>
        </div>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.vp-quota {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-neutral-400);
  text-decoration: none;
}

.vp-quota__bar {
  width: 90px;
  height: 6px;
  border-radius: 999px;
  background: var(--color-neutral-800);
  overflow: hidden;
}

.vp-quota__bar span {
  display: block;
  height: 100%;
  background: var(--color-primary);
}

.vp-quota--full {
  color: var(--color-error);
}

.vp-quota--full .vp-quota__bar span {
  background: var(--color-error);
}

.vp__head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.vp__title {
  font-family: var(--font-heading);
  font-size: 22px;
  font-weight: 800;
  margin: 0;
}

.vp__sub {
  margin: 2px 0 0;
  font-size: 13px;
  color: var(--color-neutral-400);
}

.vp__new {
  flex-shrink: 0;
}

/* --- Tuiles-filtres --- */
.vp__tiles {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 14px;
}

.vp-tile {
  display: grid;
  grid-template-columns: auto 1fr;
  grid-template-rows: auto auto;
  column-gap: 10px;
  align-items: center;
  padding: 12px;
  border-radius: var(--radius-md);
  border: 1.5px solid var(--color-divider);
  background: var(--color-neutral-900);
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.vp-tile:hover {
  border-color: hsl(var(--hue) 60% 55%);
}

.vp-tile.is-active {
  border-color: hsl(var(--hue) 65% 50%);
  box-shadow: 0 0 0 3px hsl(var(--hue) 70% var(--tint-bg));
}

.vp-tile__icon {
  grid-row: span 2;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: hsl(var(--hue) 70% var(--tint-bg));
  color: hsl(var(--hue) 60% var(--tint-fg));
}

.vp-tile__count {
  font-family: var(--font-heading);
  font-size: 20px;
  font-weight: 800;
  line-height: 1.1;
}

.vp-tile.is-alert .vp-tile__count {
  color: hsl(var(--hue) 65% var(--tint-fg));
}

.vp-tile__label {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-neutral-400);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

@media (max-width: 720px) {
  .vp__tiles {
    display: flex;
    overflow-x: auto;
    scrollbar-width: none;
    margin: 0 -16px 14px;
    padding: 2px 16px;
  }

  .vp__tiles::-webkit-scrollbar {
    display: none;
  }

  .vp-tile {
    flex: 0 0 132px;
  }
}

/* --- Barre d'outils --- */
.vp__toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.vp-search {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1 1 240px;
  height: 40px;
  padding: 0 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-divider-strong);
  background: var(--color-neutral-900);
  color: var(--color-neutral-500);
}

.vp-search:focus-within {
  border-color: var(--color-primary);
}

.vp-search input {
  flex: 1;
  min-width: 0;
  border: 0;
  outline: none !important;
  background: none;
  color: var(--color-neutral-200);
  font-size: 14px;
}

.vp-search input::-webkit-search-cancel-button {
  display: none;
}

.vp-search button {
  display: flex;
  border: 0;
  background: none;
  color: var(--color-neutral-400);
  cursor: pointer;
}

.vp__select {
  flex: 0 1 190px;
  min-width: 150px;
}

.vp-display {
  display: flex;
  border: 1px solid var(--color-divider-strong);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.vp-display button {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 38px;
  border: 0;
  background: var(--color-neutral-900);
  color: var(--color-neutral-400);
  cursor: pointer;
}

.vp-display button.is-active {
  background: var(--color-primary-100);
  color: var(--color-primary-300);
}

.vp__result {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
  font-size: 13px;
  color: var(--color-neutral-400);
}

.vp__result button {
  border: 0;
  background: none;
  color: var(--color-primary-300);
  font-weight: 700;
  cursor: pointer;
}

/* --- Cartes --- */
.vp-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}

.vp-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.vp-card {
  position: relative;
  display: flex;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-divider);
  background: var(--color-neutral-900);
  overflow: hidden;
  transition: opacity 0.2s ease, box-shadow 0.15s ease;
}

.vp-card:hover {
  box-shadow: var(--shadow-md);
}

.vp-card.is-busy {
  opacity: 0.7;
}

.vp-card--grid {
  flex-direction: column;
}

.vp-card--list {
  flex-direction: row;
  align-items: center;
  gap: 12px;
  padding: 8px 10px 8px 8px;
}

.vp-card__media {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #fff;
  color: var(--color-neutral-500);
  overflow: hidden;
}

.vp-card--grid .vp-card__media {
  aspect-ratio: 4 / 3;
  border-bottom: 1px solid var(--color-divider);
}

.vp-card--list .vp-card__media {
  width: 64px;
  height: 64px;
  flex-shrink: 0;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-divider);
}

.vp-card__media img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.vp-card.is-hidden .vp-card__media img {
  opacity: 0.45;
  filter: grayscale(0.6);
}

.vp-card__flag {
  position: absolute;
  top: 8px;
  left: 8px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(20, 21, 26, 0.75);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
}

.vp-card--list .vp-card__flag {
  top: auto;
  bottom: 3px;
  left: 3px;
  padding: 1px 5px;
  font-size: 9.5px;
}

.vp-card__body {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.vp-card--grid .vp-card__body {
  padding: 12px 12px 6px;
  flex: 1;
}

.vp-card--list .vp-card__body {
  flex: 1;
}

.vp-card__name {
  font-weight: 700;
  font-size: 14px;
  color: var(--color-neutral-200);
  text-decoration: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.vp-card__name:hover {
  color: var(--color-primary-300);
}

.vp-card__meta {
  display: flex;
  gap: 4px;
  font-size: 12px;
  color: var(--color-neutral-400);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.vp-card__price {
  font-family: var(--font-heading);
  font-size: 16px;
  font-weight: 800;
  color: var(--color-accent);
}

.vp-card__price small {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-neutral-400);
}

.vp-card__stats {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 12px;
}

.vp-stock {
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 700;
  font-size: 11.5px;
}

.vp-stock--ok {
  background: hsl(150 70% var(--tint-bg));
  color: hsl(150 55% var(--tint-fg));
}

.vp-stock--low {
  background: hsl(38 85% var(--tint-bg));
  color: hsl(30 70% var(--tint-fg));
}

.vp-stock--out {
  background: hsl(355 80% var(--tint-bg));
  color: hsl(355 65% var(--tint-fg));
}

.vp-card__stat {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  color: var(--color-neutral-400);
}

.vp-card__stat svg {
  color: var(--color-accent);
}

.vp-card__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.vp-card--grid .vp-card__actions {
  padding: 8px 8px 10px 12px;
  border-top: 1px solid var(--color-divider);
}

.vp-card--list .vp-card__actions {
  flex-shrink: 0;
}

.vp-stepper {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--color-divider-strong);
  border-radius: 999px;
  overflow: hidden;
}

.vp-stepper button {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 0;
  background: none;
  color: var(--color-neutral-300);
  cursor: pointer;
}

.vp-stepper button:disabled {
  opacity: 0.35;
  cursor: default;
}

.vp-stepper button:not(:disabled):hover {
  background: var(--color-neutral-800);
}

.vp-stepper span {
  min-width: 34px;
  text-align: center;
  font-weight: 700;
  font-size: 13.5px;
}

.vp-card__variants {
  font-size: 12px;
  font-weight: 700;
  color: var(--color-primary-300);
  text-decoration: none;
}

.vp-card__sale {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-left: auto;
  font-size: 11.5px;
  font-weight: 700;
  color: var(--color-neutral-500);
  cursor: pointer;
}

.vp-card__sale.is-on {
  color: var(--color-success);
}

.vp-card__switch {
  flex: none;
}

.vp-card__more {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 0;
  border-radius: 50%;
  background: none;
  color: var(--color-neutral-400);
  cursor: pointer;
}

.vp-card__more:hover {
  background: var(--color-neutral-800);
}

@media (max-width: 600px) {
  .vp__head {
    align-items: center;
  }

  .vp-search {
    flex-basis: 100%;
  }

  /* Catégorie, tri et affichage sur une même ligne. */
  .vp__select {
    flex: 1 1 0;
    min-width: 0;
  }

  .vp-card--list {
    flex-wrap: wrap;
  }

  .vp-card--list .vp-card__actions {
    width: 100%;
    padding-left: 76px;
  }
}
</style>
