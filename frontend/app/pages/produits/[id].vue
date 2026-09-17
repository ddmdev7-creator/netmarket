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

// Sélecteur de variante : un groupe par nom d'attribut distinct (ex.
// "Couleur", "Taille"), valeurs distinctes de ce groupe dans l'ordre où
// elles apparaissent sur les variantes — pas une grille cartésienne
// couleur×taille, seulement les combinaisons qui existent réellement comme
// variantes. Vide (et tout ce sélecteur inutilisé) pour un produit sans
// variante, comportement strictement inchangé dans ce cas.
const selected = reactive<Record<string, string>>({})

const hasVariants = computed(() => (product.value?.variants.length ?? 0) > 0)

const attributeGroups = computed(() => {
  if (!product.value) return []
  const order: string[] = []
  const values = new Map<string, string[]>()
  for (const variant of product.value.variants) {
    for (const attr of variant.attributes) {
      if (!values.has(attr.name)) {
        values.set(attr.name, [])
        order.push(attr.name)
      }
      const list = values.get(attr.name)!
      if (!list.includes(attr.value)) list.push(attr.value)
    }
  }
  return order.map((name) => ({ name, values: values.get(name)! }))
})

// Variantes encore possibles compte tenu de la sélection (même partielle) —
// sert à la fois à filtrer les valeurs proposées (on ne laisse jamais
// construire une combinaison qui n'existe pas) et à prévisualiser une image
// dès qu'un seul attribut est choisi, sans attendre que la combinaison soit
// complète.
function variantsMatchingSelection(partial: Record<string, string>) {
  if (!product.value) return []
  const entries = Object.entries(partial)
  return product.value.variants.filter((v) =>
    entries.every(([name, value]) => v.attributes.some((a) => a.name === name && a.value === value)),
  )
}

const possibleVariants = computed(() => (hasVariants.value ? variantsMatchingSelection(selected) : []))

// Une valeur reste proposable si, en l'ajoutant à la sélection actuelle des
// AUTRES attributs, au moins une variante correspond encore — évite de
// pouvoir construire un choix qui ne mène à aucune variante (ex. Rouge
// n'existe qu'en M/L : XS devient grisé dès que Rouge est choisi).
function isValueAvailable(groupName: string, value: string): boolean {
  return variantsMatchingSelection({ ...selected, [groupName]: value }).length > 0
}

const activeVariant = computed(() => {
  if (!product.value || !hasVariants.value) return null
  const groups = attributeGroups.value
  if (Object.keys(selected).length !== groups.length) return null
  return (
    product.value.variants.find(
      (v) => v.attributes.length === groups.length && v.attributes.every((a) => selected[a.name] === a.value),
    ) ?? null
  )
})

// Sélection complète (une valeur par attribut) mais qui ne correspond à
// aucune variante existante — ne devrait plus guère arriver maintenant que
// les valeurs impossibles sont grisées au fur et à mesure (voir
// isValueAvailable), gardé comme filet de sécurité.
const selectionIncomplete = computed(
  () => hasVariants.value && Object.keys(selected).length === attributeGroups.value.length && !activeVariant.value,
)

// Pour la galerie uniquement : dès qu'un attribut est choisi (même sans
// combinaison complète), montre la photo de la première variante encore
// possible qui en a une — ex. choisir "Noir" affiche tout de suite une
// variante noire, avant même d'avoir choisi la taille. Le prix/stock reste
// lui piloté par activeVariant (correspondance exacte) : ils ne doivent
// jamais laisser croire qu'une variante précise est sélectionnée avant que
// ce soit vraiment le cas.
const previewVariant = computed(() => {
  if (!hasVariants.value || Object.keys(selected).length === 0) return null
  if (activeVariant.value) return activeVariant.value
  return possibleVariants.value.find((v) => v.images && v.images.length > 0) ?? possibleVariants.value[0] ?? null
})

const effectiveStock = computed(() => {
  if (!product.value) return 0
  return hasVariants.value ? (activeVariant.value?.stock ?? 0) : product.value.stock
})

const effectivePrice = computed(() => {
  if (!product.value) return 0
  return activeVariant.value?.price ?? product.value.price
})

const effectiveImages = computed(() => {
  if (!product.value) return []
  return previewVariant.value?.images?.length ? previewVariant.value.images : product.value.images
})

const stockLabel = computed(() => {
  if (hasVariants.value && !activeVariant.value) return 'Choisissez une variante'
  return effectiveStock.value > 0 ? 'En stock' : 'Épuisé'
})
const stockChipColor = computed(() => {
  if (hasVariants.value && !activeVariant.value) return undefined
  return effectiveStock.value > 0 ? 'success' : 'error'
})

const addDisabled = computed(() => {
  if (!product.value) return true
  return hasVariants.value ? !activeVariant.value || activeVariant.value.stock === 0 : product.value.stock === 0
})

function selectAttribute(name: string, value: string) {
  selected[name] = value
  quantity.value = 1
  justAdded.value = false
}

function incr() {
  if (quantity.value < effectiveStock.value) quantity.value++
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
    await cartStore.addItem(productId, quantity.value, activeVariant.value?.id ?? null)
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
  <div v-else-if="product" class="app-shell app-shell--wide" style="padding-bottom: 88px">
    <div class="d-flex align-center pa-2 ga-2">
      <v-btn icon variant="text" @click="router.back()">
        <PhArrowLeft :size="20" />
      </v-btn>
      <LayoutHomeLink />
    </div>

    <div class="px-4 product-detail">
      <div class="product-detail__media">
        <ProductImageGallery :images="effectiveImages" :alt="product.name" />
      </div>

      <div class="product-detail__info">
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
            formatGnf(effectivePrice)
          }}</span>
          <v-chip size="small" :color="stockChipColor" variant="tonal">
            {{ stockLabel }}
          </v-chip>
        </div>

        <div v-if="hasVariants" class="mb-4">
          <div class="attribute-groups">
            <div v-for="group in attributeGroups" :key="group.name" class="attribute-group">
              <div class="text-muted mb-1 text-meta">{{ group.name }}</div>
              <div class="d-flex flex-wrap ga-2">
                <v-chip
                  v-for="value in group.values"
                  :key="value"
                  :variant="selected[group.name] === value ? 'flat' : 'outlined'"
                  :color="selected[group.name] === value ? 'primary' : undefined"
                  :disabled="selected[group.name] !== value && !isValueAvailable(group.name, value)"
                  @click="selectAttribute(group.name, value)"
                >
                  {{ value }}
                </v-chip>
              </div>
            </div>
          </div>
          <p v-if="selectionIncomplete" class="mt-3 mb-0 text-meta" style="color: var(--color-error)">
            Cette combinaison n'est pas disponible.
          </p>
        </div>

        <div class="mb-4">
          <div class="text-muted mb-1 text-meta">Quantité</div>
          <div class="qty-selector">
            <button type="button" :disabled="quantity <= 1" @click="decr">−</button>
            <span>{{ quantity }}</span>
            <button type="button" :disabled="quantity >= effectiveStock" @click="incr">+</button>
          </div>
        </div>

        <v-divider class="mb-4" />

        <h3 class="text-subtitle-1 mb-2">Description</h3>
        <!-- v-html sûr ici : le backend assainit systématiquement la
             description à l'écriture (app/catalog/service.py::_sanitize_description),
             quel que soit le point d'entrée — jamais confiance dans le HTML
             saisi côté client seul, voir le commentaire côté backend. -->
        <div v-if="product.description" class="description-content text-muted text-meta" v-html="product.description" />
        <p v-else class="text-muted text-meta mb-0">Aucune description fournie par le vendeur.</p>

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
    </div>

    <ProductReviewForm
      v-model="reviewFormOpen"
      :product-id="productId"
      @submitted="reviewListRef?.refresh()"
    />
    <CommonReportDialog v-model="reportProductOpen" :endpoint="`/products/${productId}/reports`" />

    <div class="checkout-bar checkout-bar--wide">
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
        :disabled="addDisabled"
        @click="addToCart"
      >
        Ajouter au panier — {{ formatGnf(effectivePrice * quantity) }}
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

/* white-space: pre-line préserve l'affichage des descriptions déjà en base
   avant le mini éditeur riche (texte brut avec retours à la ligne, sans
   balises) ; les balises produites par l'éditeur (p/ul/ol) gèrent leurs
   propres sauts de ligne via leur affichage en bloc, indépendamment de
   cette règle. */
.description-content {
  white-space: pre-line;
}

.description-content :deep(p) {
  margin: 0 0 8px;
}

.description-content :deep(p:last-child) {
  margin-bottom: 0;
}

.description-content :deep(ul),
.description-content :deep(ol) {
  margin: 0 0 8px;
  padding-left: 20px;
}

/* Un groupe d'attributs (ex. "Couleur") par colonne dès qu'il y a la place
   — empilés verticalement sur mobile (comportement inchangé), côte à côte
   sur desktop plutôt que de scroller une longue liste de groupes. */
.attribute-groups {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
}

@media (min-width: 480px) {
  .attribute-groups {
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  }
}

@media (min-width: 960px) {
  .product-detail {
    display: grid;
    grid-template-columns: 420px 1fr;
    gap: 32px;
    align-items: start;
  }

  .product-detail__media {
    position: sticky;
    top: 16px;
  }
}
</style>
