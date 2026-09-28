<script setup lang="ts">
import {
  PhArrowUp,
  PhCrosshair,
  PhFunnel,
  PhMagnifyingGlassMinus,
  PhMapPin,
  PhSparkle,
  PhStar,
  PhStorefront,
  PhTag,
} from '@phosphor-icons/vue'
import type { CategoryRead, Page, ProductRead, ProductSort, SearchSuggestions } from '~/types/api'

const { apiFetch } = useApi()
const route = useRoute()
const router = useRouter()
const toast = useToastStore()
const { near, locating, resolve: resolveNear, requestPosition: askPosition } = useNearPosition()

const PAGE_SIZE = 20
const RAIL_SIZE = 10

const SORT_OPTIONS: { value: ProductSort; title: string }[] = [
  { value: 'recent', title: 'Nouveautés' },
  { value: 'top_rated', title: 'Mieux notés' },
  { value: 'nearest', title: 'Près de moi' },
  { value: 'price_asc', title: 'Prix croissant' },
  { value: 'price_desc', title: 'Prix décroissant' },
]
const SORT_VALUES = SORT_OPTIONS.map((o) => o.value)

// --- État de recherche (q, catégorie et tri repris de l'URL : un retour
// arrière depuis une fiche produit retrouve la même liste) -----------------

// query = recherche appliquée à la liste ; search = texte en cours de
// frappe dans la barre (qui ne relance la liste qu'à la validation).
const query = ref(typeof route.query.q === 'string' ? route.query.q : '')
const search = ref(query.value)
const shop = ref<{ id: string; name: string } | null>(
  typeof route.query.shop === 'string'
    ? { id: route.query.shop, name: typeof route.query.shop_name === 'string' ? route.query.shop_name : 'Boutique' }
    : null,
)
const activeCategoryId = ref<string | null>(typeof route.query.cat === 'string' ? route.query.cat : null)
const sort = ref<ProductSort>(
  SORT_VALUES.includes(route.query.sort as ProductSort) ? (route.query.sort as ProductSort) : 'recent',
)
const minPrice = ref<number | null>(null)
const maxPrice = ref<number | null>(null)
const inStockOnly = ref(false)
const filtersOpen = ref(false)


const hasPriceFilter = computed(() => minPrice.value !== null || maxPrice.value !== null)
const hasActiveFilters = computed(() => hasPriceFilter.value || inStockOnly.value)
// Accueil "vitrine" (bandeau + rubriques) tant qu'on ne cherche rien de précis.
const isBrowsing = computed(
  () => !query.value.trim() && !activeCategoryId.value && !shop.value && !hasActiveFilters.value,
)

const { data: categories } = await useAsyncData('home-categories', () => apiFetch<CategoryRead[]>('/categories'), {
  default: () => [],
})

const activeCategory = computed(() => categories.value.find((c) => c.id === activeCategoryId.value) ?? null)
// Pastilles sous-catégories : celles de la catégorie ouverte, ou ses
// "sœurs" si c'est déjà une sous-catégorie (pour passer de Hp à Lenovo).
const subCategoryParent = computed(() => {
  const current = activeCategory.value
  if (!current) return null
  const hasChildren = categories.value.some((c) => c.parent_id === current.id)
  if (hasChildren) return current
  return categories.value.find((c) => c.id === current.parent_id) ?? null
})
const subCategories = computed(() =>
  subCategoryParent.value
    ? categories.value
        .filter((c) => c.parent_id === subCategoryParent.value!.id)
        .sort((a, b) => a.name.localeCompare(b.name, 'fr'))
    : [],
)
const rootCategoryId = computed(() => {
  let current = activeCategory.value
  while (current?.parent_id) current = categories.value.find((c) => c.id === current!.parent_id) ?? null
  return current?.id ?? null
})

function listQuery(page: number, pageSize: number, overrides: Record<string, unknown> = {}) {
  const effectiveSort = sort.value === 'nearest' && !near.value ? 'recent' : sort.value
  return {
    page,
    page_size: pageSize,
    category_id: activeCategoryId.value ?? undefined,
    q: query.value.trim() || undefined,
    vendor_id: shop.value?.id,
    min_price: minPrice.value ?? undefined,
    max_price: maxPrice.value ?? undefined,
    in_stock: inStockOnly.value || undefined,
    sort: effectiveSort,
    near_lat: near.value?.lat,
    near_lng: near.value?.lng,
    ...overrides,
  }
}

// --- Liste principale en défilement infini ---------------------------------

const emptyPage: Page<ProductRead> = { items: [], total: 0, page: 1, page_size: PAGE_SIZE, pages: 0 }
const {
  data: firstPage,
  pending,
  refresh,
} = await useAsyncData('home-products', () => apiFetch<Page<ProductRead>>('/products', { query: listQuery(1, PAGE_SIZE) }), {
  default: () => emptyPage,
})

const extraItems = ref<ProductRead[]>([])
const nextPage = ref(2)
const loadingMore = ref(false)
// Incrémenté à chaque changement de critères : une page "suivante" encore en
// vol pour les anciens critères est alors ignorée au lieu d'être ajoutée.
let generation = 0

const products = computed(() => [...(firstPage.value?.items ?? []), ...extraItems.value])
const total = computed(() => firstPage.value?.total ?? 0)
const hasMore = computed(() => products.value.length < total.value)

async function loadMore() {
  if (loadingMore.value || pending.value || !hasMore.value) return
  loadingMore.value = true
  const gen = generation
  try {
    const page = await apiFetch<Page<ProductRead>>('/products', { query: listQuery(nextPage.value, PAGE_SIZE) })
    if (gen !== generation) return
    const seen = new Set(products.value.map((p) => p.id))
    extraItems.value.push(...page.items.filter((p) => !seen.has(p.id)))
    nextPage.value += 1
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de charger la suite des produits.'))
  } finally {
    loadingMore.value = false
  }
}

function syncUrl() {
  const q: Record<string, string> = {}
  if (query.value.trim()) q.q = query.value.trim()
  if (activeCategoryId.value) q.cat = activeCategoryId.value
  if (shop.value) {
    q.shop = shop.value.id
    q.shop_name = shop.value.name
  }
  if (sort.value !== 'recent') q.sort = sort.value
  router.replace({ query: q })
}

function reload() {
  generation += 1
  extraItems.value = []
  nextPage.value = 2
  loadingMore.value = false
  syncUrl()
  refresh()
}

const resultsAnchor = ref<HTMLElement | null>(null)
function scrollToResults() {
  nextTick(() => {
    const el = resultsAnchor.value
    if (!el) return
    // Sous la barre du haut (sticky) plutôt que caché derrière.
    window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - 72, behavior: 'smooth' })
  })
}

function selectCategory(id: string | null) {
  activeCategoryId.value = id
  reload()
}

async function selectSort(value: ProductSort, scroll = false) {
  if (value === 'nearest' && !near.value && !(await requestPosition())) return
  sort.value = value
  reload()
  if (scroll) scrollToResults()
}

function applyFilters() {
  filtersOpen.value = false
  reload()
}

function clearPrice() {
  minPrice.value = null
  maxPrice.value = null
  reload()
}

function clearStock() {
  inStockOnly.value = false
  reload()
}

function resetAll() {
  search.value = ''
  query.value = ''
  shop.value = null
  activeCategoryId.value = null
  minPrice.value = null
  maxPrice.value = null
  inStockOnly.value = false
  sort.value = 'recent'
  reload()
}

function onSearchSubmit(q: string) {
  query.value = q
  reload()
  if (q) scrollToResults()
}

function onSearchCategory(id: string) {
  query.value = ''
  selectCategory(id)
  scrollToResults()
}

function selectShop(value: { id: string; name: string }) {
  query.value = ''
  shop.value = value
  reload()
  scrollToResults()
}

function clearShop() {
  shop.value = null
  reload()
}

function applySuggestion(q: string) {
  search.value = q
  onSearchSubmit(q)
}

// "Vouliez-vous dire…" quand une recherche ne donne rien.
const didYouMean = ref<string | null>(null)
watch(
  () => [pending.value, total.value, query.value] as const,
  async ([isPending, count, q]) => {
    didYouMean.value = null
    if (isPending || count > 0 || q.trim().length < 2) return
    try {
      const result = await apiFetch<SearchSuggestions>('/products/suggest', { query: { q: q.trim() } })
      if (q === query.value) didYouMean.value = result.did_you_mean
    } catch {
      // Sans correction proposée, les conseils suffisent.
    }
  },
)
const noResults = computed(() => !pending.value && products.value.length === 0 && !isBrowsing.value)
const fallbackProducts = computed(() => (topRated.value.length >= MIN_RAIL ? topRated.value : railRecent.value?.items ?? []))

const priceChipLabel = computed(() => {
  if (minPrice.value !== null && maxPrice.value !== null) return `${formatGnf(minPrice.value)} – ${formatGnf(maxPrice.value)}`
  if (minPrice.value !== null) return `Dès ${formatGnf(minPrice.value)}`
  return `Jusqu'à ${formatGnf(maxPrice.value ?? 0)}`
})

const resultsTitle = computed(() => {
  if (isBrowsing.value) return 'Tous les produits'
  const count = `${total.value} produit${total.value > 1 ? 's' : ''}`
  if (query.value.trim()) return `${count} pour « ${query.value.trim()} »`
  if (activeCategory.value) return `${activeCategory.value.name} · ${count}`
  if (shop.value) return `${shop.value.name} · ${count}`
  return count
})

// --- Rubriques de l'accueil -------------------------------------------------

const railFetch = (sortKey: ProductSort) => () =>
  apiFetch<Page<ProductRead>>('/products', { query: { page: 1, page_size: RAIL_SIZE, sort: sortKey, in_stock: true } })

const [{ data: railRecent, pending: railRecentPending }, { data: railTop }, { data: railCheap }] = await Promise.all([
  useAsyncData('home-rail-recent', railFetch('recent'), { default: () => emptyPage }),
  useAsyncData('home-rail-top', railFetch('top_rated'), { default: () => emptyPage }),
  useAsyncData('home-rail-cheap', railFetch('price_asc'), { default: () => emptyPage }),
])

const nearItems = ref<ProductRead[]>([])
const nearLoading = ref(false)

// Une rubrique n'apparaît que si elle a de quoi défiler ; "Mieux notés" ne
// garde que les produits réellement notés (les autres arrivent en fin de tri).
const MIN_RAIL = 3
const topRated = computed(() => (railTop.value?.items ?? []).filter((p) => p.review_count > 0))

async function loadNearRail() {
  if (!near.value) return
  nearLoading.value = true
  try {
    const page = await apiFetch<Page<ProductRead>>('/products', {
      query: { page: 1, page_size: RAIL_SIZE, sort: 'nearest', in_stock: true, near_lat: near.value.lat, near_lng: near.value.lng },
    })
    nearItems.value = page.items
  } catch {
    nearItems.value = []
  } finally {
    nearLoading.value = false
  }
}

async function requestPosition(): Promise<boolean> {
  try {
    await askPosition()
    await loadNearRail()
    return true
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Impossible de récupérer ta position.')
    return false
  }
}

async function initNear() {
  await resolveNear()
  await loadNearRail()
  // Tri "Près de moi" repris de l'URL : la liste serveur a été triée par date
  // faute de position, on la recharge maintenant qu'elle est connue.
  if (sort.value === 'nearest' && near.value) reload()
}

// --- Défilement infini + bouton "haut de page" ------------------------------

const sentinel = ref<HTMLElement | null>(null)
const showBackToTop = ref(false)
let sentinelObserver: IntersectionObserver | null = null

function backToTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function onScroll() {
  showBackToTop.value = window.scrollY > 900
}

onMounted(() => {
  initNear()
  window.addEventListener('scroll', onScroll, { passive: true })
  sentinelObserver = new IntersectionObserver((entries) => entries[0]?.isIntersecting && loadMore(), {
    rootMargin: '600px 0px',
  })
  if (sentinel.value) sentinelObserver.observe(sentinel.value)
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', onScroll)
  sentinelObserver?.disconnect()
})
</script>

<template>
  <div class="home-page">
    <div class="d-flex align-center ga-2 mb-4">
      <HomeSearchBox
        v-model="search"
        :categories="categories"
        @submit="onSearchSubmit"
        @category="onSearchCategory"
        @shop="selectShop"
      />
      <button
        type="button"
        class="filter-btn"
        :class="{ 'filter-btn--active': hasActiveFilters }"
        aria-label="Filtres"
        @click="filtersOpen = true"
      >
        <PhFunnel :size="18" weight="bold" />
        <span v-if="hasActiveFilters" class="filter-btn__dot" />
      </button>
    </div>

    <HomeHeroBanner v-if="isBrowsing" class="mb-5" />

    <HomeCategoryRail
      v-if="categories.length"
      :categories="categories"
      :active-id="rootCategoryId"
      class="mb-4"
      @select="selectCategory"
    />

    <template v-if="isBrowsing">
      <HomeProductRail
        v-if="nearItems.length >= MIN_RAIL || nearLoading"
        title="Près de chez vous"
        :icon="PhMapPin"
        :hue="150"
        :products="nearItems"
        :loading="nearLoading"
        class="mb-5"
        @see-all="selectSort('nearest', true)"
      />
      <button
        v-else-if="!near"
        type="button"
        class="near-cta mb-5"
        :disabled="locating"
        @click="requestPosition"
      >
        <span class="near-cta__icon"><PhCrosshair :size="20" weight="bold" /></span>
        <span class="near-cta__text">
          <strong>Voir les boutiques près de chez vous</strong>
          <span>Livraison plus rapide et moins chère</span>
        </span>
        <v-progress-circular v-if="locating" indeterminate size="18" width="2" color="primary" />
      </button>

      <HomeProductRail
        v-if="(railRecent?.items.length ?? 0) >= MIN_RAIL || railRecentPending"
        title="Nouveautés"
        :icon="PhSparkle"
        :hue="220"
        :products="railRecent?.items ?? []"
        :loading="railRecentPending"
        class="mb-5"
        @see-all="selectSort('recent', true)"
      />
      <HomeProductRail
        v-if="topRated.length >= MIN_RAIL"
        title="Les mieux notés"
        :icon="PhStar"
        :hue="35"
        :products="topRated"
        class="mb-5"
        @see-all="selectSort('top_rated', true)"
      />
      <HomeProductRail
        v-if="(railCheap?.items.length ?? 0) >= MIN_RAIL"
        title="Petits prix"
        :icon="PhTag"
        :hue="345"
        :products="railCheap?.items ?? []"
        class="mb-5"
        @see-all="selectSort('price_asc', true)"
      />
    </template>

    <div ref="resultsAnchor" class="results-head">
      <h2 class="results-head__title">{{ resultsTitle }}</h2>
      <button v-if="!isBrowsing" type="button" class="results-head__reset" @click="resetAll">Tout effacer</button>
    </div>

    <div v-if="subCategories.length" class="chip-scroll mb-2">
      <v-chip
        :variant="activeCategoryId === subCategoryParent!.id ? 'flat' : 'outlined'"
        :color="activeCategoryId === subCategoryParent!.id ? 'primary' : undefined"
        size="small"
        @click="selectCategory(subCategoryParent!.id)"
      >
        Tout {{ subCategoryParent!.name }}
      </v-chip>
      <v-chip
        v-for="child in subCategories"
        :key="child.id"
        :variant="activeCategoryId === child.id ? 'flat' : 'outlined'"
        :color="activeCategoryId === child.id ? 'primary' : undefined"
        size="small"
        @click="selectCategory(child.id)"
      >
        {{ child.name }}
      </v-chip>
    </div>

    <div class="chip-scroll mb-3" role="group" aria-label="Trier par">
      <button
        v-for="option in SORT_OPTIONS"
        :key="option.value"
        type="button"
        class="sort-chip"
        :class="{ 'sort-chip--active': sort === option.value }"
        :aria-pressed="sort === option.value"
        @click="selectSort(option.value)"
      >
        {{ option.title }}
      </button>
      <span v-if="hasActiveFilters || shop" class="chip-scroll__sep" />
      <v-chip v-if="shop" size="small" color="primary" variant="tonal" closable @click:close="clearShop">
        <PhStorefront :size="14" class="mr-1" />
        {{ shop.name }}
      </v-chip>
      <v-chip v-if="hasPriceFilter" size="small" color="primary" variant="tonal" closable @click:close="clearPrice">
        {{ priceChipLabel }}
      </v-chip>
      <v-chip v-if="inStockOnly" size="small" color="primary" variant="tonal" closable @click:close="clearStock">
        En stock
      </v-chip>
    </div>

    <div v-if="noResults" class="no-results">
      <span class="no-results__icon"><PhMagnifyingGlassMinus :size="30" weight="duotone" /></span>
      <h3 class="no-results__title">
        {{ query.trim() ? `Aucun résultat pour « ${query.trim()} »` : 'Aucun produit ne correspond à ces critères' }}
      </h3>
      <p v-if="didYouMean" class="no-results__dym">
        Vouliez-vous dire
        <button type="button" class="no-results__dym-btn" @click="applySuggestion(didYouMean)">{{ didYouMean }}</button>
        ?
      </p>
      <ul class="no-results__tips">
        <li v-if="query.trim()">Vérifiez l'orthographe ou essayez un mot plus simple (« téléphone » plutôt que le modèle exact).</li>
        <li v-if="activeCategoryId || shop || hasActiveFilters">Retirez un filtre ou cherchez dans toutes les catégories.</li>
      </ul>
      <v-btn variant="tonal" color="primary" @click="resetAll">Voir tous les produits</v-btn>
    </div>
    <HomeProductRail
      v-if="noResults && fallbackProducts.length"
      title="Ça pourrait vous plaire"
      :icon="PhStar"
      :hue="35"
      :products="fallbackProducts"
      class="mt-6"
      @see-all="resetAll"
    />
    <ProductGrid v-if="!noResults" :products="products" :loading="pending" />

    <div ref="sentinel" class="load-more">
      <v-progress-circular v-if="loadingMore" indeterminate size="26" width="3" color="primary" />
      <v-btn v-else-if="hasMore && !pending" variant="text" color="primary" @click="loadMore">Voir plus</v-btn>
      <span v-else-if="!pending && products.length > PAGE_SIZE / 2" class="load-more__end">
        Vous avez tout vu
      </span>
    </div>

    <transition name="fade">
      <button v-if="showBackToTop" type="button" class="back-to-top" aria-label="Revenir en haut" @click="backToTop">
        <PhArrowUp :size="20" weight="bold" />
      </button>
    </transition>

    <v-bottom-sheet v-model="filtersOpen">
      <v-card class="pa-4">
        <div class="text-subtitle-1 mb-4">Filtres</div>
        <div class="field-label">Prix (GNF)</div>
        <div class="d-flex ga-2 mb-4">
          <v-text-field v-model.number="minPrice" type="number" placeholder="Min" density="compact" hide-details />
          <v-text-field v-model.number="maxPrice" type="number" placeholder="Max" density="compact" hide-details />
        </div>
        <v-switch v-model="inStockOnly" label="En stock uniquement" density="compact" hide-details class="mb-4" />
        <div class="d-flex ga-2">
          <v-btn
            variant="outlined"
            class="flex-grow-1"
            @click="
              minPrice = null;
              maxPrice = null;
              inStockOnly = false;
              applyFilters()
            "
          >
            Réinitialiser
          </v-btn>
          <v-btn color="primary" class="flex-grow-1" @click="applyFilters">Appliquer</v-btn>
        </div>
      </v-card>
    </v-bottom-sheet>
  </div>
</template>

<style scoped>
/* Reprend px-3 py-4 (12px/16px, l'ancien padding Vuetify utilitaire) sur
   mobile, élargi sur ordinateur maintenant que .app-shell--catalog n'est
   plus plafonné (voir main.css). Les rubriques (HomeProductRail) débordent
   de ce padding pour aller jusqu'au bord de l'écran — garder les deux en phase. */
.home-page {
  padding: 16px 12px;
  overflow-x: clip;
}

@media (min-width: 960px) {
  .home-page {
    padding: 24px 32px;
  }
}

/* Bouton filtre : toujours visible comme un vrai bouton (bordure) plutôt
   que de compter uniquement sur un changement de couleur pour signaler
   l'état actif — le point orange en complément reste lisible même pour qui
   ne perçoit pas bien la différence de teinte. */
.filter-btn {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-divider-strong);
  background: var(--color-neutral-900);
  color: var(--color-neutral-300);
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease, background 0.15s ease;
}

.filter-btn:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.filter-btn--active {
  border-color: var(--color-primary);
  background: var(--color-primary-100);
  color: var(--color-primary);
}

.filter-btn__dot {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-accent);
  border: 2px solid var(--color-neutral-900);
}

.no-results {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 28px 16px 8px;
}

.no-results__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  margin-bottom: 12px;
  border-radius: 50%;
  background: hsl(220 70% var(--tint-bg));
  color: hsl(220 60% var(--tint-fg));
}

.no-results__title {
  font-family: var(--font-heading);
  font-size: 17px;
  font-weight: 800;
  margin: 0 0 6px;
}

.no-results__dym {
  font-size: 15px;
  margin: 0 0 8px;
}

.no-results__dym-btn {
  border: 0;
  background: none;
  padding: 0;
  color: var(--color-primary-300);
  font-weight: 800;
  font-size: inherit;
  text-decoration: underline;
  cursor: pointer;
}

.no-results__tips {
  max-width: 420px;
  margin: 4px 0 16px;
  padding-left: 18px;
  text-align: left;
  font-size: 13px;
  color: var(--color-neutral-400);
}

.near-cta {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 12px 14px;
  border: 1.5px dashed hsl(150 50% 45% / 0.6);
  border-radius: var(--radius-md);
  background: hsl(150 70% var(--tint-bg-soft));
  color: var(--color-neutral-300);
  text-align: left;
  cursor: pointer;
}

.near-cta__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  flex-shrink: 0;
  border-radius: 50%;
  background: hsl(150 70% var(--tint-bg));
  color: hsl(150 60% var(--tint-fg));
}

.near-cta__text {
  display: flex;
  flex-direction: column;
  flex: 1;
  font-size: 12.5px;
  color: var(--color-neutral-400);
}

.near-cta__text strong {
  font-size: 14px;
  color: var(--color-neutral-200);
}

.results-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 10px;
}

.results-head__title {
  flex: 1;
  font-family: var(--font-heading);
  font-size: 17px;
  font-weight: 800;
  margin: 0;
}

.results-head__reset {
  border: 0;
  background: none;
  color: var(--color-primary-300);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.chip-scroll {
  display: flex;
  align-items: center;
  gap: 6px;
  overflow-x: auto;
  scrollbar-width: none;
  padding-bottom: 2px;
}

.chip-scroll::-webkit-scrollbar {
  display: none;
}

.chip-scroll > * {
  flex-shrink: 0;
}

.chip-scroll__sep {
  width: 1px;
  height: 20px;
  margin: 0 2px;
  background: var(--color-divider-strong);
}

.sort-chip {
  padding: 6px 12px;
  border-radius: 999px;
  border: 1px solid var(--color-divider-strong);
  background: var(--color-neutral-900);
  color: var(--color-neutral-300);
  font-size: 12.5px;
  font-weight: 600;
  white-space: nowrap;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}

.sort-chip--active {
  border-color: var(--color-neutral-200);
  background: var(--color-neutral-200);
  color: var(--color-neutral-900);
}

.load-more {
  display: flex;
  justify-content: center;
  min-height: 56px;
  padding: 16px 0 8px;
}

.load-more__end {
  font-size: 12.5px;
  color: var(--color-neutral-500);
}

.back-to-top {
  position: fixed;
  right: 16px;
  bottom: 88px;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border: 0;
  border-radius: 50%;
  background: var(--color-neutral-900);
  color: var(--color-primary);
  box-shadow: var(--shadow-md);
  cursor: pointer;
}

@media (min-width: 960px) {
  .back-to-top {
    bottom: 32px;
    right: 32px;
  }
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(8px);
}
</style>
