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
  <div class="px-3 py-4">
    <div class="d-flex align-center ga-2 mb-3">
      <v-text-field
        v-model="search"
        placeholder="Rechercher un produit…"
        density="compact"
        variant="solo-filled"
        hide-details
        flat
        rounded
        @update:model-value="onSearchInput"
      >
        <template #prepend-inner>
          <PhMagnifyingGlass :size="18" color="var(--color-neutral-500)" />
        </template>
      </v-text-field>

      <v-btn
        icon
        variant="tonal"
        :color="hasActiveFilters ? 'primary' : undefined"
        aria-label="Filtres"
        @click="filtersOpen = true"
      >
        <PhFunnel :size="18" weight="bold" />
      </v-btn>
    </div>

    <div class="chip-row mb-3">
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
.chip-row {
  display: flex;
  overflow-x: auto;
  padding-bottom: 4px;
  scrollbar-width: none;
}

.chip-row::-webkit-scrollbar {
  display: none;
}

.chip-row__item {
  flex-shrink: 0;
}
</style>
