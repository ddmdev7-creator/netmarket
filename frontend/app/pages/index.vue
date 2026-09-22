<script setup lang="ts">
import { PhFunnel, PhMagnifyingGlass } from '@phosphor-icons/vue'
import type { CategoryRead, Page, ProductRead, ProductSort } from '~/types/api'

const { apiFetch } = useApi()

const activeCategoryId = ref<string | null>(null)
const search = ref('')
const page = ref(1)
const pageSize = 20

const filtersOpen = ref(false)
const minPrice = ref<number | null>(null)
const maxPrice = ref<number | null>(null)
const inStockOnly = ref(false)
const sort = ref<ProductSort>('recent')

const SORT_OPTIONS: { value: ProductSort; title: string }[] = [
  { value: 'recent', title: 'Plus récents' },
  { value: 'price_asc', title: 'Prix croissant' },
  { value: 'price_desc', title: 'Prix décroissant' },
]

const hasActiveFilters = computed(
  () => minPrice.value !== null || maxPrice.value !== null || inStockOnly.value || sort.value !== 'recent',
)

const { data: categories } = await useAsyncData('home-categories', () => apiFetch<CategoryRead[]>('/categories'), {
  default: () => [],
})

const emptyPage: Page<ProductRead> = { items: [], total: 0, page: 1, page_size: pageSize, pages: 0 }

const {
  data: productsPage,
  pending,
  refresh,
} = await useAsyncData(
  'home-products',
  () =>
    apiFetch<Page<ProductRead>>('/products', {
      query: {
        page: page.value,
        page_size: pageSize,
        category_id: activeCategoryId.value ?? undefined,
        q: search.value || undefined,
        min_price: minPrice.value ?? undefined,
        max_price: maxPrice.value ?? undefined,
        in_stock: inStockOnly.value || undefined,
        sort: sort.value,
      },
    }),
  { default: () => emptyPage },
)

const products = computed(() => productsPage.value?.items ?? [])
const total = computed(() => productsPage.value?.total ?? 0)
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

function selectCategory(id: string | null) {
  activeCategoryId.value = id
  page.value = 1
  refresh()
}

function applyFilters() {
  page.value = 1
  filtersOpen.value = false
  refresh()
}

function resetFilters() {
  minPrice.value = null
  maxPrice.value = null
  inStockOnly.value = false
  sort.value = 'recent'
  applyFilters()
}

let searchTimeout: ReturnType<typeof setTimeout>
function onSearchInput() {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    page.value = 1
    refresh()
  }, 350)
}

watch(page, () => refresh())
</script>

<template>
  <div class="home-page">
    <div class="d-flex align-center ga-2 mb-3">
      <v-text-field
        v-model="search"
        placeholder="Rechercher un produit…"
        density="comfortable"
        variant="solo"
        hide-details
        flat
        rounded
        class="search-field"
        @update:model-value="onSearchInput"
      >
        <template #prepend-inner>
          <PhMagnifyingGlass :size="19" weight="bold" color="var(--color-primary)" />
        </template>
      </v-text-field>

      <button type="button" class="filter-btn" :class="{ 'filter-btn--active': hasActiveFilters }" aria-label="Filtres" @click="filtersOpen = true">
        <PhFunnel :size="18" weight="bold" />
        <span v-if="hasActiveFilters" class="filter-btn__dot" />
      </button>
    </div>

    <div class="chip-row-wrap mb-3">
      <div class="chip-row">
        <v-chip
          :variant="activeCategoryId === null ? 'flat' : 'outlined'"
          :color="activeCategoryId === null ? 'primary' : undefined"
          class="chip-row__item mr-2"
          @click="selectCategory(null)"
        >
          Tout
        </v-chip>
        <v-chip
          v-for="category in categories"
          :key="category.id"
          :variant="activeCategoryId === category.id ? 'flat' : 'outlined'"
          :color="activeCategoryId === category.id ? 'primary' : undefined"
          class="chip-row__item mr-2"
          @click="selectCategory(category.id)"
        >
          {{ category.name }}
        </v-chip>
      </div>
    </div>

    <ProductGrid :products="products" :loading="pending" />

    <v-pagination v-if="pageCount > 1" v-model="page" :length="pageCount" density="compact" class="mt-4" />

    <v-bottom-sheet v-model="filtersOpen">
      <v-card class="pa-4">
        <div class="text-subtitle-1 mb-4">Filtres</div>

        <div class="field-label">Prix (GNF)</div>
        <div class="d-flex ga-2 mb-4">
          <v-text-field v-model.number="minPrice" type="number" placeholder="Min" density="compact" hide-details />
          <v-text-field v-model.number="maxPrice" type="number" placeholder="Max" density="compact" hide-details />
        </div>

        <v-switch v-model="inStockOnly" label="En stock uniquement" density="compact" hide-details class="mb-2" />

        <div class="field-label mt-2">Trier par</div>
        <v-select
          v-model="sort"
          :items="SORT_OPTIONS"
          item-title="title"
          item-value="value"
          density="compact"
          variant="outlined"
          hide-details
          class="mb-4"
        />

        <div class="d-flex ga-2">
          <v-btn variant="outlined" class="flex-grow-1" @click="resetFilters">Réinitialiser</v-btn>
          <v-btn color="primary" class="flex-grow-1" @click="applyFilters">Appliquer</v-btn>
        </div>
      </v-card>
    </v-bottom-sheet>
  </div>
</template>

<style scoped>
/* Reprend px-3 py-4 (12px/16px, l'ancien padding Vuetify utilitaire) sur
   mobile, élargi sur ordinateur maintenant que .app-shell--catalog n'est
   plus plafonné (voir main.css) — sans ça, le contenu resterait collé aux
   bords de la fenêtre sur un grand écran malgré la largeur disponible. */
.home-page {
  padding: 16px 12px;
}

@media (min-width: 960px) {
  .home-page {
    padding: 24px 32px;
  }
}

/* Champ de recherche mis en avant : fond blanc plein (variant="solo") avec
   une ombre légère plutôt que le gris plat "solo-filled" précédent, qui se
   fondait presque dans le fond de page — c'est la première action de la
   page, elle doit se voir immédiatement. */
.search-field :deep(.v-field) {
  box-shadow: var(--shadow-sm);
}

.search-field :deep(.v-field__input) {
  font-size: 14px;
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

/* Le fondu à droite (mask-image) signale qu'il y a plus de catégories à
   découvrir sans avoir à réactiver la scrollbar native — un indice visuel
   discret mais immédiat, plutôt que de compter sur l'utilisateur pour
   deviner que la liste défile. */
.chip-row-wrap {
  position: relative;
  -webkit-mask-image: linear-gradient(to right, black calc(100% - 28px), transparent 100%);
  mask-image: linear-gradient(to right, black calc(100% - 28px), transparent 100%);
}

.chip-row {
  display: flex;
  overflow-x: auto;
  padding: 2px 20px 6px 2px;
  scrollbar-width: none;
}

.chip-row::-webkit-scrollbar {
  display: none;
}

.chip-row__item {
  flex-shrink: 0;
}
</style>
