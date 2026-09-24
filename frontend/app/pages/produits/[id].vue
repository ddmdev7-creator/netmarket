<script setup lang="ts">
import { PhArrowLeft, PhFlag, PhMapPin, PhShoppingCart, PhStar, PhTruck } from '@phosphor-icons/vue'
import type { ProductRead, ProductVariantRead, ReviewRead } from '~/types/api'

definePageMeta({ layout: 'blank' })

const route = useRoute()
const router = useRouter()
const { apiFetch } = useApi()
const cartStore = useCartStore()
const auth = useAuthStore()
const toast = useToastStore()

const productId = route.params.id as string

const { data: product, error, refresh: refreshProduct } = await useAsyncData(`product-${productId}`, () =>
  apiFetch<ProductRead>(`/products/${productId}`),
)

const reviewListRef = ref<{ refresh: () => Promise<void> } | null>(null)
const reviewFormOpen = ref(false)
const reportProductOpen = ref(false)

// Seul un acheteur qui a reçu ce produit peut le noter (règle backend) :
// la liste de ses produits reçus dit s'il peut laisser un avis, ou s'il en
// a déjà un à modifier.
const reviewable = useReviewableProducts()
const myEntry = computed(() => reviewable.byProduct.value.get(productId) ?? null)

function openReviewForm() {
  if (!auth.isAuthenticated) {
    router.push({ path: '/connexion', query: { redirect: route.fullPath } })
    return
  }
  reviewFormOpen.value = true
}

function onReviewSubmitted(review: ReviewRead) {
  reviewable.applyReview(review)
  reviewListRef.value?.refresh()
  refreshProduct()
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

function variantHasValue(variant: ProductVariantRead, name: string, value: string) {
  return variant.attributes.some((a) => a.name === name && a.value === value)
}

const COLOR_ATTRIBUTE_NAMES = ['couleur', 'color', 'coloris']

interface AttributeGroup {
  name: string
  values: string[]
  /** Photo représentative de chaque valeur (1re variante qui en a une). */
  images: Record<string, string | null>
  /** Groupe "visuel" (ex. Couleur) : ses valeurs ont des photos distinctes,
      affichées en vignettes plutôt qu'en simples pastilles de texte. */
  visual: boolean
}

const attributeGroups = computed<AttributeGroup[]>(() => {
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
  const groups = order.map((name) => {
    const groupValues = values.get(name)!
    const images: Record<string, string | null> = {}
    for (const value of groupValues) {
      const withImage = product.value!.variants.find((v) => variantHasValue(v, name, value) && v.images?.length)
      images[value] = withImage?.images?.[0] ?? null
    }
    const distinct = new Set(Object.values(images).filter(Boolean))
    const eligible = groupValues.every((v) => images[v]) && distinct.size > 1
    return { name, values: groupValues, images, visual: eligible }
  })
  // Un seul groupe en vignettes : la couleur de préférence, sinon le premier
  // éligible — une RAM ou une taille en photos n'apporterait rien.
  const visualGroup =
    groups.find((g) => g.visual && COLOR_ATTRIBUTE_NAMES.includes(g.name.toLowerCase())) ?? groups.find((g) => g.visual)
  for (const g of groups) g.visual = g === visualGroup
  return groups
})

// Variantes encore possibles compte tenu de la sélection (même partielle) —
// sert à la fois à marquer les valeurs incompatibles et à prévisualiser une
// image dès qu'un seul attribut est choisi.
function variantsMatchingSelection(partial: Record<string, string>) {
  if (!product.value) return []
  const entries = Object.entries(partial)
  return product.value.variants.filter((v) => entries.every(([name, value]) => variantHasValue(v, name, value)))
}

const possibleVariants = computed(() => (hasVariants.value ? variantsMatchingSelection(selected) : []))

function selectionWithout(name: string) {
  const rest: Record<string, string> = {}
  for (const [key, value] of Object.entries(selected)) if (key !== name) rest[key] = value
  return rest
}

// Chaque valeur reste TOUJOURS cliquable : une valeur incompatible avec le
// reste de la sélection est seulement signalée (pointillés), et la choisir
// bascule dessus en retirant les choix qui la contredisent (voir
// selectAttribute) — plus besoin de "Réinitialiser" pour changer d'avis.
const groupsView = computed(() =>
  attributeGroups.value.map((group) => {
    const others = selectionWithout(group.name)
    return {
      ...group,
      options: group.values.map((value) => {
        const matches = variantsMatchingSelection({ ...others, [group.name]: value })
        const everMatches = matches.length ? matches : variantsMatchingSelection({ [group.name]: value })
        return {
          value,
          image: group.images[value],
          compatible: matches.length > 0,
          soldOut: everMatches.every((v) => v.stock === 0),
        }
      }),
    }
  }),
)

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

const missingGroups = computed(() => attributeGroups.value.filter((g) => !selected[g.name]).map((g) => g.name))

// Pour la galerie uniquement : dès qu'un attribut est choisi (même sans
// combinaison complète), montre la photo de la première variante encore
// possible qui en a une. Le prix/stock reste lui piloté par activeVariant
// (correspondance exacte).
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

// Tant que la combinaison n'est pas complète, les variantes encore possibles
// peuvent avoir des prix différents : on affiche "À partir de" plutôt qu'un
// prix qui risque de changer au dernier choix.
const priceFrom = computed(() => {
  if (!product.value || activeVariant.value || !hasVariants.value) return null
  const prices = possibleVariants.value.map((v) => v.price ?? product.value!.price)
  if (prices.length < 2) return null
  const min = Math.min(...prices)
  return min === Math.max(...prices) ? null : min
})

const effectiveImages = computed(() => {
  if (!product.value) return []
  return previewVariant.value?.images?.length ? previewVariant.value.images : product.value.images
})

const stockLabel = computed(() => {
  if (hasVariants.value && !activeVariant.value) return null
  if (effectiveStock.value === 0) return 'Épuisé'
  return effectiveStock.value <= 5 ? `Plus que ${effectiveStock.value}` : 'En stock'
})
const stockChipColor = computed(() => {
  if (effectiveStock.value === 0) return 'error'
  return effectiveStock.value <= 5 ? 'warning' : 'success'
})

// Dès qu'un choix ne laisse plus qu'une seule valeur possible pour un autre
// attribut (ex. "Rouge" n'existe qu'en taille M), on la coche directement.
// En boucle car cocher un groupe peut à son tour rendre un troisième groupe
// non ambigu (au-delà de 2 attributs).
function autoSelectUnambiguousAttributes() {
  let changed = true
  while (changed) {
    changed = false
    for (const group of attributeGroups.value) {
      if (selected[group.name]) continue
      const stillPossible = group.values.filter(
        (value) => variantsMatchingSelection({ ...selected, [group.name]: value }).length > 0,
      )
      if (stillPossible.length === 1) {
        selected[group.name] = stillPossible[0]!
        changed = true
      }
    }
  }
}

// Message discret quand un choix en a retiré un autre (ex. "32Go n'existe
// pas en Noire : choix ajusté"), pour que la bascule ne passe pas inaperçue.
const switchNotice = ref<string | null>(null)
let switchNoticeTimer: ReturnType<typeof setTimeout> | undefined

function selectAttribute(name: string, value: string) {
  // Recliquer la valeur déjà choisie revient dessus (désélection).
  clearTimeout(switchNoticeTimer)
  switchNotice.value = null
  if (selected[name] === value) {
    delete selected[name]
  } else {
    selected[name] = value
    const dropped: string[] = []
    // D'abord les choix directement contradictoires avec la nouvelle valeur…
    for (const key of Object.keys(selected)) {
      if (key === name) continue
      if (variantsMatchingSelection({ [name]: value, [key]: selected[key]! }).length === 0) {
        dropped.push(selected[key]!)
        delete selected[key]
      }
    }
    // … puis, au-delà de 2 attributs, ceux qui ne tiennent qu'ensemble.
    while (variantsMatchingSelection(selected).length === 0) {
      const key = Object.keys(selected).reverse().find((k) => k !== name)
      if (!key) break
      dropped.push(selected[key]!)
      delete selected[key]
    }
    autoSelectUnambiguousAttributes()
    switchNotice.value = dropped.length ? `${dropped.join(', ')} n'existe pas en ${value} : choix ajusté.` : null
    if (dropped.length) switchNoticeTimer = setTimeout(() => (switchNotice.value = null), 4000)
  }
  quantity.value = 1
  justAdded.value = false
}

// À l'ouverture : on présélectionne la valeur "visuelle" (ex. la couleur) de
// la première variante en stock — la photo et les tailles disponibles
// s'affichent tout de suite. Les autres groupes (taille…) restent un choix
// conscient de l'acheteur, sauf s'ils n'ont qu'une réponse possible.
function preselectDefaults() {
  const firstInStock = product.value?.variants.find((v) => v.stock > 0)
  const visualGroup = attributeGroups.value.find((g) => g.visual)
  if (firstInStock && visualGroup) {
    const attr = firstInStock.attributes.find((a) => a.name === visualGroup.name)
    if (attr) selected[attr.name] = attr.value
  }
  autoSelectUnambiguousAttributes()
}
preselectDefaults()

const selectionSummary = computed(() =>
  attributeGroups.value
    .map((g) => selected[g.name])
    .filter(Boolean)
    .join(' · '),
)

// Bouton principal : tant qu'il manque un choix, il le dit ("Choisir :
// Taille") et amène directement au groupe concerné au lieu d'être grisé.
const optionsEl = ref<HTMLElement | null>(null)
const flashGroup = ref<string | null>(null)

function goToMissingGroup() {
  const name = missingGroups.value[0]
  if (!name) return
  const el = optionsEl.value?.querySelector<HTMLElement>(`[data-group="${CSS.escape(name)}"]`)
  el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  flashGroup.value = name
  setTimeout(() => (flashGroup.value = null), 1200)
}

// Barre compacte (téléphone) : dès que la galerie sort de l'écran, une
// vignette de la photo en cours + le prix restent visibles en haut — plus
// besoin de remonter voir l'image après chaque choix d'option.
const mediaEl = ref<HTMLElement | null>(null)
const mediaOutOfView = ref(false)
let mediaObserver: IntersectionObserver | null = null

onMounted(() => {
  if (!mediaEl.value) return
  mediaObserver = new IntersectionObserver(
    ([entry]) => {
      mediaOutOfView.value = !!entry && !entry.isIntersecting
    },
    { threshold: 0, rootMargin: '-40% 0px 0px 0px' },
  )
  mediaObserver.observe(mediaEl.value)
})
onBeforeUnmount(() => {
  mediaObserver?.disconnect()
  clearTimeout(switchNoticeTimer)
})

function scrollToTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

const addDisabled = computed(() => {
  if (!product.value) return true
  if (hasVariants.value) return !!activeVariant.value && activeVariant.value.stock === 0
  return product.value.stock === 0
})

const apiBase = useApiBase()
const miniThumb = computed(() => (effectiveImages.value[0] ? resolveImageUrl(effectiveImages.value[0], apiBase) : null))

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

    <Transition name="mini-bar">
      <button v-if="mediaOutOfView" type="button" class="mini-bar" aria-label="Revoir les photos" @click="scrollToTop">
        <img v-if="miniThumb" :src="miniThumb" :alt="product.name" class="mini-bar__thumb" />
        <span class="mini-bar__text">
          <span class="mini-bar__name">{{ product.name }}</span>
          <span class="mini-bar__meta">
            <strong><template v-if="priceFrom !== null">dès </template>{{ formatGnf(priceFrom ?? effectivePrice) }}</strong>
            <template v-if="selectionSummary"> · {{ selectionSummary }}</template>
          </span>
        </span>
      </button>
    </Transition>

    <div class="px-4 product-detail">
      <div ref="mediaEl" class="product-detail__media">
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

        <div class="price-row mb-4">
          <span v-if="priceFrom !== null" class="price-row__from">À partir de</span>
          <span class="price-row__amount">{{ formatGnf(priceFrom ?? effectivePrice) }}</span>
          <v-chip v-if="stockLabel" size="small" :color="stockChipColor" variant="tonal">
            {{ stockLabel }}
          </v-chip>
        </div>

        <section v-if="hasVariants" ref="optionsEl" class="options mb-4" aria-label="Options du produit">
          <div
            v-for="group in groupsView"
            :key="group.name"
            :data-group="group.name"
            class="option-group"
            :class="{ 'option-group--flash': flashGroup === group.name }"
          >
            <div class="option-group__label">
              <span>{{ group.name }}</span>
              <strong v-if="selected[group.name]">{{ selected[group.name] }}</strong>
              <span v-else class="option-group__todo">à choisir</span>
            </div>
            <div class="option-values" :class="{ 'option-values--swatches': group.visual }">
              <button
                v-for="opt in group.options"
                :key="opt.value"
                type="button"
                class="option-value"
                :class="{
                  'is-selected': selected[group.name] === opt.value,
                  'is-incompatible': !opt.compatible,
                  'is-soldout': opt.soldOut,
                }"
                :aria-pressed="selected[group.name] === opt.value"
                :title="opt.soldOut ? `${opt.value} — épuisé` : !opt.compatible ? `${opt.value} — change les autres choix` : opt.value"
                @click="selectAttribute(group.name, opt.value)"
              >
                <img
                  v-if="group.visual && opt.image"
                  :src="resolveImageUrl(opt.image, apiBase)"
                  :alt="opt.value"
                  class="option-value__img"
                  loading="lazy"
                />
                <span class="option-value__label">{{ opt.value }}</span>
              </button>
            </div>
          </div>
          <Transition name="fade">
            <p v-if="switchNotice" class="options__notice">{{ switchNotice }}</p>
          </Transition>
        </section>

        <v-divider class="mb-4" />

        <div class="mb-4">
          <div class="mb-1 text-body" style="font-weight: 700">Quantité</div>
          <div class="qty-selector">
            <button type="button" :disabled="quantity <= 1" @click="decr">−</button>
            <span>{{ quantity }}</span>
            <button type="button" :disabled="quantity >= effectiveStock" @click="incr">+</button>
          </div>
        </div>

        <v-divider class="mb-2" />

        <v-expansion-panels variant="accordion">
          <v-expansion-panel>
            <v-expansion-panel-title>Description</v-expansion-panel-title>
            <v-expansion-panel-text>
              <!-- v-html sûr ici : le backend assainit systématiquement la
                   description à l'écriture (app/catalog/service.py::_sanitize_description),
                   quel que soit le point d'entrée — jamais confiance dans le HTML
                   saisi côté client seul, voir le commentaire côté backend. -->
              <div
                v-if="product.description"
                class="description-content text-muted text-meta"
                v-html="product.description"
              />
              <p v-else class="text-muted text-meta mb-0">Aucune description fournie par le vendeur.</p>
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>

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
          <v-btn v-if="!auth.isAuthenticated" variant="outlined" size="small" @click="openReviewForm">
            Laisser un avis
          </v-btn>
          <v-btn v-else-if="myEntry" variant="outlined" size="small" color="primary" @click="openReviewForm">
            <PhStar :size="15" weight="fill" class="mr-1" />
            {{ myEntry.review ? 'Modifier mon avis' : 'Noter ce produit' }}
          </v-btn>
        </div>
        <p v-if="auth.isAuthenticated && !myEntry && !reviewable.pending.value" class="text-muted text-meta mb-3">
          Seuls les acheteurs ayant reçu ce produit peuvent le noter.
        </p>
        <ProductReviewList ref="reviewListRef" :product-id="productId" />
      </div>
    </div>

    <ProductReviewForm
      v-model="reviewFormOpen"
      :product-id="productId"
      :product-name="product?.name"
      :product-image="product?.images?.[0] ?? null"
      :existing="myEntry?.review ?? null"
      @submitted="onReviewSubmitted"
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
      <v-btn v-else-if="hasVariants && missingGroups.length" color="primary" variant="tonal" block size="large" @click="goToMissingGroup">
        Choisir : {{ missingGroups.join(', ') }}
      </v-btn>
      <v-btn
        v-else
        color="primary"
        block
        size="large"
        :loading="adding"
        :disabled="addDisabled"
        @click="addToCart"
      >
        <template v-if="addDisabled">Épuisé</template>
        <template v-else>Ajouter au panier — {{ formatGnf(effectivePrice * quantity) }}</template>
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

.price-row {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 4px 10px;
}

.price-row__from {
  font-size: 12.5px;
  color: var(--color-neutral-400);
}

.price-row__amount {
  font-family: var(--font-heading);
  font-size: 24px;
  font-weight: 800;
  color: var(--color-accent);
  font-variant-numeric: tabular-nums;
}

.price-row .v-chip {
  align-self: center;
}

/* Options empilées (une rangée par attribut), libellé + valeur choisie sur
   la même ligne : on voit d'un coup d'œil ce qui est choisi et ce qui manque. */
.options {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 14px;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-lg);
  background: var(--color-neutral-900);
}

.option-group {
  border-radius: var(--radius-md);
  transition: box-shadow 0.2s ease, background 0.2s ease;
}

.option-group--flash {
  animation: option-flash 1.2s ease;
}

@keyframes option-flash {
  0%,
  60% {
    background: color-mix(in srgb, var(--color-primary) 12%, transparent);
    box-shadow: 0 0 0 6px color-mix(in srgb, var(--color-primary) 12%, transparent);
  }
  100% {
    background: transparent;
    box-shadow: 0 0 0 6px transparent;
  }
}

.option-group__label {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--color-neutral-400);
}

.option-group__label span:first-child::after {
  content: ' :';
}

.option-group__label strong {
  color: var(--color-neutral-100);
  font-weight: 700;
}

.option-group__todo {
  color: var(--color-accent);
  font-weight: 600;
}

.option-values {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.option-value {
  position: relative;
  min-width: 48px;
  min-height: 40px;
  padding: 0 14px;
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  border: 1.5px solid var(--color-divider-strong);
  border-radius: var(--radius-md);
  background: var(--color-neutral-900);
  color: var(--color-neutral-200);
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease, transform 0.1s ease;
}

.option-value:active {
  transform: scale(0.96);
}

.option-value.is-selected {
  border-color: var(--color-primary);
  background: color-mix(in srgb, var(--color-primary) 10%, var(--color-neutral-900));
  color: var(--color-primary);
  box-shadow: 0 0 0 1px var(--color-primary);
}

/* Incompatible avec les autres choix : reste cliquable (bascule), juste
   atténué en pointillés. */
.option-value.is-incompatible:not(.is-selected) {
  border-style: dashed;
  color: var(--color-neutral-500);
}

.option-value.is-soldout .option-value__label {
  text-decoration: line-through;
  color: var(--color-neutral-500);
}

/* Vignettes photo (groupe visuel, ex. Couleur) : l'acheteur voit la
   couleur sans remonter jusqu'à la galerie. */
.option-values--swatches .option-value {
  width: 76px;
  padding: 4px 4px 6px;
}

.option-value__img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: contain;
  border-radius: calc(var(--radius-md) - 3px);
  background: #fff;
}

.option-values--swatches .option-value__label {
  max-width: 100%;
  font-size: 11.5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.options__notice {
  margin: 0;
  font-size: 12px;
  color: var(--color-accent);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Barre compacte du haut (téléphone uniquement) — voir mediaOutOfView. */
.mini-bar {
  position: fixed;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 100%;
  max-width: 480px;
  z-index: 6;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px;
  padding-top: calc(8px + env(safe-area-inset-top, 0px));
  border: none;
  border-bottom: 1px solid var(--color-divider);
  background: var(--color-neutral-900);
  box-shadow: var(--shadow-md);
  text-align: left;
  color: inherit;
  cursor: pointer;
}

.mini-bar__thumb {
  width: 52px;
  height: 52px;
  flex: none;
  object-fit: contain;
  border-radius: var(--radius-sm);
  background: #fff;
  border: 1px solid var(--color-divider);
}

.mini-bar__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.mini-bar__name {
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mini-bar__meta {
  font-size: 12.5px;
  color: var(--color-neutral-400);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mini-bar__meta strong {
  color: var(--color-accent);
}

.mini-bar-enter-active,
.mini-bar-leave-active {
  transition: transform 0.2s ease, opacity 0.2s ease;
}

.mini-bar-enter-from,
.mini-bar-leave-to {
  transform: translate(-50%, -100%);
  opacity: 0;
}

@media (min-width: 960px) {
  .mini-bar {
    display: none;
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
