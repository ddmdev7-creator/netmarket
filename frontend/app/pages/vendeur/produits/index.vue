<script setup lang="ts">
import { PhCaretRight, PhImage, PhPlus, PhTrash } from '@phosphor-icons/vue'
import type { CategoryRead, Page, ProductRead, ProductStatus, StockLevel, VendorRead } from '~/types/api'

definePageMeta({ middleware: 'vendor', layout: 'vendeur' })

const { apiFetch } = useApi()
const apiBase = useApiBase()
const toast = useToastStore()
const pageSize = 20

// getCachedData: hydrateThenRefetch — see app/pages/vendeur/index.vue for why:
// without it, switching tabs in the vendor bottom nav re-serves whatever was
// fetched last time this page mounted instead of the current stock/status.
const { data: vendor } = await useAsyncData('vendor-me-products-page', () => apiFetch<VendorRead>('/vendors/me'), {
  getCachedData: hydrateThenRefetch,
})

const { data: categories } = await useAsyncData('vendor-products-categories', () => apiFetch<CategoryRead[]>('/categories'), {
  default: () => [],
})

const STATUS_FILTERS: { value: ProductStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'Tous' },
  { value: 'active', label: 'Actifs' },
  { value: 'inactive', label: 'Inactifs' },
]
const STOCK_FILTERS: { value: StockLevel | 'all'; label: string }[] = [
  { value: 'all', label: 'Stock : tous' },
  { value: 'low', label: 'Stock faible' },
  { value: 'out', label: 'Rupture' },
]

const statusFilter = ref<ProductStatus | 'all'>('all')
const stockFilter = ref<StockLevel | 'all'>('all')
const categoryFilter = ref<string | null>(null)

const page = ref(1)
const emptyPage: Page<ProductRead> = { items: [], total: 0, page: 1, page_size: pageSize, pages: 0 }
const {
  data: productsPage,
  pending,
  refresh,
} = await useAsyncData(
  'vendor-my-products',
  () =>
    apiFetch<Page<ProductRead>>('/products/me', {
      query: {
        page: page.value,
        page_size: pageSize,
        category_id: categoryFilter.value ?? undefined,
        status: statusFilter.value === 'all' ? undefined : statusFilter.value,
        stock_level: stockFilter.value === 'all' ? undefined : stockFilter.value,
      },
    }),
  { default: () => emptyPage, getCachedData: hydrateThenRefetch },
)

const products = computed(() => productsPage.value?.items ?? [])
const pageCount = computed(() => Math.max(1, productsPage.value?.pages ?? 1))
watch(page, () => refresh())

function applyFilters() {
  page.value = 1
  refresh()
}

function selectStatus(value: ProductStatus | 'all') {
  statusFilter.value = value
  applyFilters()
}

function selectStock(value: StockLevel | 'all') {
  stockFilter.value = value
  applyFilters()
}

const canPublish = computed(() => vendor.value?.status === 'approved')

const confirmDeleteId = ref<string | null>(null)
const deleting = ref(false)
async function deleteProduct() {
  if (!confirmDeleteId.value) return
  deleting.value = true
  try {
    await apiFetch(`/products/${confirmDeleteId.value}`, { method: 'DELETE' })
    toast.success('Produit supprimé.')
    confirmDeleteId.value = null
    await refresh()
  } catch (e) {
    toast.error(
      apiErrorMessage(
        e,
        "Impossible de supprimer ce produit — il est probablement déjà référencé dans une commande. Tu peux le désactiver à la place.",
      ),
    )
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <div class="dashboard-shell">
    <h1 class="text-h6 mb-4">Mes produits</h1>

    <v-alert v-if="vendor && !canPublish" type="warning" variant="tonal" density="compact" class="mb-4">
      Ta boutique doit être approuvée par un administrateur avant de publier des produits.
    </v-alert>

    <v-btn
      :to="canPublish ? '/vendeur/produits/nouveau' : undefined"
      :disabled="!canPublish"
      color="primary"
      block
      class="mb-4"
    >
      <PhPlus :size="18" class="mr-1" />
      Nouveau produit
    </v-btn>

    <v-select
      v-model="categoryFilter"
      :items="categories"
      item-title="name"
      item-value="id"
      label="Catégorie"
      density="compact"
      variant="outlined"
      hide-details
      clearable
      class="mb-3"
      @update:model-value="applyFilters"
    />

    <div class="status-filters mb-2">
      <button
        v-for="f in STATUS_FILTERS"
        :key="f.value"
        type="button"
        class="status-filter"
        :class="{ 'status-filter--active': statusFilter === f.value }"
        @click="selectStatus(f.value)"
      >
        {{ f.label }}
      </button>
    </div>
    <div class="status-filters mb-4">
      <button
        v-for="f in STOCK_FILTERS"
        :key="f.value"
        type="button"
        class="status-filter"
        :class="{ 'status-filter--active': stockFilter === f.value }"
        @click="selectStock(f.value)"
      >
        {{ f.label }}
      </button>
    </div>

    <CommonEmptyState v-if="!pending && products.length === 0" message="Aucun produit pour ces filtres." />

    <NuxtLink v-for="p in products" :key="p.id" :to="`/vendeur/produits/${p.id}`" class="product-row">
      <div class="product-row__thumb">
        <img v-if="p.images[0]" :src="resolveImageUrl(p.images[0], apiBase)" :alt="p.name" />
        <PhImage v-else :size="20" weight="light" color="var(--color-neutral-500)" />
      </div>
      <div class="flex-grow-1">
        <div style="font-size: 13px">{{ p.name }}</div>
        <div class="d-flex ga-2 mt-1 align-center">
          <span style="font-size: 12.5px; font-weight: 600">{{ formatGnf(p.price) }}</span>
          <span class="text-muted" style="font-size: 11.5px">· {{ p.stock }} en stock</span>
        </div>
      </div>
      <v-chip :color="p.status === 'active' ? 'success' : 'default'" size="x-small" variant="tonal">
        {{ p.status === 'active' ? 'Actif' : 'Inactif' }}
      </v-chip>
      <PhCaretRight :size="16" color="var(--color-neutral-500)" class="flex-shrink-0" />
      <button
        type="button"
        class="product-row__delete"
        aria-label="Supprimer ce produit"
        @click.stop.prevent="confirmDeleteId = p.id"
      >
        <PhTrash :size="16" />
      </button>
    </NuxtLink>

    <v-pagination v-if="pageCount > 1" v-model="page" :length="pageCount" density="compact" class="mt-4" />

    <v-dialog :model-value="!!confirmDeleteId" max-width="340" @update:model-value="(v) => !v && (confirmDeleteId = null)">
      <v-card class="pa-5">
        <div class="text-subtitle-1 mb-2">Supprimer ce produit ?</div>
        <p class="text-muted mb-4" style="font-size: 13px">Cette action est définitive.</p>
        <div class="d-flex ga-2">
          <v-btn variant="outlined" class="flex-grow-1" @click="confirmDeleteId = null">Annuler</v-btn>
          <v-btn color="error" class="flex-grow-1" :loading="deleting" @click="deleteProduct">Supprimer</v-btn>
        </div>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.status-filters {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 2px;
  scrollbar-width: none;
}
.status-filters::-webkit-scrollbar {
  display: none;
}

.status-filter {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid var(--color-divider);
  background: var(--color-neutral-900);
  color: var(--color-neutral-300);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}

.status-filter--active {
  border-color: var(--color-primary);
  background: var(--color-primary-800);
  color: var(--color-primary-100);
}

.product-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 8px;
  margin: 0 -8px;
  border-radius: var(--radius-sm);
  border-bottom: 1px solid var(--color-divider);
  text-decoration: none;
  color: inherit;
  transition: background 0.15s ease;
}

.product-row:hover {
  background: var(--color-neutral-800);
}

.product-row__thumb {
  width: 48px;
  height: 48px;
  flex: none;
  border-radius: var(--radius-sm);
  background: var(--color-neutral-800);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.product-row__thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.product-row__delete {
  background: none;
  border: none;
  color: var(--color-neutral-500);
  flex-shrink: 0;
  padding: 8px;
  margin: -8px -4px -8px 0;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: color 0.15s ease, background 0.15s ease;
}

.product-row__delete:hover {
  color: var(--color-error);
  background: var(--color-neutral-800);
}
</style>
