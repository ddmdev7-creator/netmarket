<script setup lang="ts">
import { PhArrowLeft, PhFlag, PhMapPin, PhShoppingCart, PhStar, PhTruck } from '@phosphor-icons/vue'
import type { ProductRead } from '~/types/api'

definePageMeta({ layout: 'blank' })

const route = useRoute()
const router = useRouter()
const { apiFetch } = useApi()
const cartStore = useCartStore()
const auth = useAuthStore()
const toast = useToastStore()

const productId = route.params.id as string

const { data: product, error } = await useAsyncData(`product-${productId}`, () =>
  apiFetch<ProductRead>(`/products/${productId}`),
)

const reviewListRef = ref<{ refresh: () => Promise<void> } | null>(null)
const reviewFormOpen = ref(false)
const reportProductOpen = ref(false)

function openReviewForm() {
  if (!auth.isAuthenticated) {
    router.push({ path: '/connexion', query: { redirect: route.fullPath } })
    return
  }
  reviewFormOpen.value = true
}

const quantity = ref(1)
const adding = ref(false)
const justAdded = ref(false)

function incr() {
  if (product.value && quantity.value < product.value.stock) quantity.value++
  justAdded.value = false
}
function decr() {
  if (quantity.value > 1) quantity.value--
  justAdded.value = false
}

async function addToCart() {
  if (!auth.isAuthenticated) {
    await router.push({ path: '/connexion', query: { redirect: route.fullPath } })
    return
  }
  adding.value = true
  try {
    await cartStore.addItem(productId, quantity.value)
    toast.success('Ajouté au panier.')
    justAdded.value = true
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'ajouter ce produit au panier."))
  } finally {
    adding.value = false
  }
}
</script>

<template>
  <div v-if="error" class="pa-6">
    <CommonEmptyState message="Produit introuvable." />
  </div>
  <div v-else-if="product" class="app-shell" style="padding-bottom: 88px">
    <div class="d-flex align-center pa-2 ga-2">
      <v-btn icon variant="text" @click="router.back()">
        <PhArrowLeft :size="20" />
      </v-btn>
      <LayoutHomeLink />
    </div>

    <div class="px-4">
      <ProductImageGallery :images="product.images" :alt="product.name" />

      <div class="d-flex justify-space-between align-start mt-4 mb-1">
        <h1 class="text-h6 mb-0">{{ product.name }}</h1>
        <button v-if="auth.isAuthenticated" type="button" class="report-btn" @click="reportProductOpen = true">
          <PhFlag :size="16" />
        </button>
      </div>
      <div class="text-muted mb-1 text-meta">Vendu par {{ product.vendor_shop_name }}</div>
      <div v-if="product.average_rating !== null" class="d-flex align-center ga-1 mb-3 text-meta">
        <PhStar :size="14" weight="fill" color="var(--color-accent)" />
        <span>{{ product.average_rating.toFixed(1) }}</span>
        <span class="text-muted">({{ product.review_count }} avis)</span>
      </div>
      <div v-else class="text-muted mb-3 text-meta">Aucun avis pour l'instant</div>

      <div class="d-flex align-center ga-3 mb-4">
        <span class="text-heading" style="font-size: 22px; font-weight: 600; color: var(--color-accent)">{{
          formatGnf(product.price)
        }}</span>
        <v-chip size="small" :color="product.stock > 0 ? 'success' : 'error'" variant="tonal">
          {{ product.stock > 0 ? 'En stock' : 'Épuisé' }}
        </v-chip>
      </div>

      <div class="mb-4">
        <div class="text-muted mb-1 text-meta">Quantité</div>
        <div class="qty-selector">
          <button type="button" :disabled="quantity <= 1" @click="decr">−</button>
          <span>{{ quantity }}</span>
          <button type="button" :disabled="quantity >= product.stock" @click="incr">+</button>
        </div>
      </div>

      <v-divider class="mb-4" />

      <h3 class="text-subtitle-1 mb-2">Description</h3>
      <p class="text-muted text-meta" style="white-space: pre-line">
        {{ product.description || 'Aucune description fournie par le vendeur.' }}
      </p>

      <div
        v-if="product.estimated_delivery_min && product.estimated_delivery_max"
        class="d-flex ga-2 mt-4 align-center text-meta"
      >
        <PhTruck :size="16" color="var(--color-primary)" />
        <span>
          Livraison estimée :
          <strong>{{ formatDeliveryEstimate(product.estimated_delivery_min, product.estimated_delivery_max) }}</strong>
        </span>
      </div>

      <div class="d-flex ga-2 mt-2 text-muted text-meta">
        <PhMapPin :size="16" />
        <span>Livraison par zone/quartier avec point de repère — pas d'adresse postale requise</span>
      </div>

      <v-divider class="my-4" />

      <div class="d-flex justify-space-between align-center mb-2">
        <h3 class="text-subtitle-1 mb-0">Avis</h3>
        <v-btn variant="outlined" size="small" @click="openReviewForm">Laisser un avis</v-btn>
      </div>
      <ProductReviewList ref="reviewListRef" :product-id="productId" />
    </div>

    <ProductReviewForm
      v-model="reviewFormOpen"
      :product-id="productId"
      @submitted="reviewListRef?.refresh()"
    />
    <CommonReportDialog v-model="reportProductOpen" :endpoint="`/products/${productId}/reports`" />

    <div class="checkout-bar">
      <div v-if="justAdded" class="d-flex flex-column ga-2">
        <v-btn color="primary" block size="large" to="/panier">
          <PhShoppingCart :size="18" class="mr-1" />
          Aller au panier
        </v-btn>
        <v-btn variant="outlined" block @click="justAdded = false">Continuer mes achats</v-btn>
      </div>
      <v-btn
        v-else
        color="primary"
        block
        size="large"
        :loading="adding"
        :disabled="product.stock === 0"
        @click="addToCart"
      >
        Ajouter au panier — {{ formatGnf(product.price * quantity) }}
      </v-btn>
    </div>
  </div>
</template>

<style scoped>
.report-btn {
  background: none;
  border: none;
  color: var(--color-neutral-500);
  padding: 10px;
  margin: -10px;
  cursor: pointer;
}
</style>
