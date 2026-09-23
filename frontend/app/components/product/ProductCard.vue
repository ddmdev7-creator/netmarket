<script setup lang="ts">
import { PhImage, PhShoppingCartSimple, PhStar, PhStorefront, PhTruck } from '@phosphor-icons/vue'
import type { ProductRead, ProductVariantRead } from '~/types/api'

const props = defineProps<{ product: ProductRead }>()

const apiBase = useApiBase()
const router = useRouter()
const auth = useAuthStore()
const cartStore = useCartStore()
const toast = useToastStore()

const adding = ref(false)
const justAdded = ref(false)

const isOutOfStock = computed(() => props.product.stock <= 0)
const isLowStock = computed(() => props.product.stock > 0 && props.product.stock <= 5)
const hasVariants = computed(() => props.product.variants.length > 0)

// L'attribut le plus "visuel" d'une variante — celui qu'une photo différente
// représente le plus souvent. À défaut d'un attribut nommé Couleur/Color, le
// premier attribut de la variante sert de repli (mieux qu'une carte muette).
const PRIMARY_ATTRIBUTE_NAMES = ['couleur', 'color', 'coloris']
function primaryAttributeValue(variant: ProductVariantRead): string | null {
  const preferred = variant.attributes.find((a) => PRIMARY_ATTRIBUTE_NAMES.includes(a.name.toLowerCase()))
  return (preferred ?? variant.attributes[0])?.value ?? null
}

interface CardFrame {
  image: string
  /** Valeur d'attribut représentée par cette photo — null pour la photo par défaut du produit. */
  label: string | null
}

// Une photo par variante qui a SA PROPRE image (voir ProductVariantRead.images
// — null hérite des photos du produit, donc rien de nouveau à montrer), plus
// la photo par défaut du produit en tête si elle existe. Dédoublonnée par nom
// de fichier : si une variante réutilise justement la photo par défaut, elle
// n'apparaît pas deux fois dans le défilement.
const frames = computed<CardFrame[]>(() => {
  const result: CardFrame[] = []
  const seen = new Set<string>()
  const baseImage = props.product.images[0]
  if (baseImage) {
    result.push({ image: baseImage, label: null })
    seen.add(baseImage)
  }
  for (const variant of props.product.variants) {
    const image = variant.images?.[0]
    if (!image || seen.has(image)) continue
    seen.add(image)
    result.push({ image, label: primaryAttributeValue(variant) })
  }
  return result
})

const hasCarousel = computed(() => frames.value.length > 1)

// Résumé compact des valeurs d'attribut disponibles (ex. "Noire · Rouge") —
// affiché quand il y a des variantes mais rien à faire défiler (aucune n'a
// sa propre photo), pour que l'info reste visible même sans carrousel.
const attributeSummary = computed(() => {
  if (!hasVariants.value) return null
  const values: string[] = []
  for (const variant of props.product.variants) {
    const value = primaryAttributeValue(variant)
    if (value && !values.includes(value)) values.push(value)
  }
  if (values.length === 0) return null
  const shown = values.slice(0, 3)
  const extra = values.length - shown.length
  return shown.join(' · ') + (extra > 0 ? ` +${extra}` : '')
})

// Une seule ligne de caractéristique sous le prix, jamais deux : on garde une
// hauteur de carte prévisible (voir .product-card__tags) plutôt que de
// risquer un retour à la ligne sur les cartes étroites (grille mobile,
// minmax 150px).
const deliveryLabel = computed(() => {
  const { estimated_delivery_min, estimated_delivery_max } = props.product
  return estimated_delivery_min && estimated_delivery_max
    ? formatDeliveryEstimate(estimated_delivery_min, estimated_delivery_max)
    : null
})

// Note affichée en étoiles fractionnaires (4,3 → 4 pleines + 30 % de la
// cinquième) : une rangée d'étoiles vides, et par-dessus la même rangée
// pleine, rognée à la largeur de la note.
const hasRating = computed(() => props.product.average_rating !== null && props.product.review_count > 0)
const ratingPct = computed(() => ((props.product.average_rating ?? 0) / 5) * 100)
// Montant et devise séparés : « GNF » en plus petit libère la place de la
// note sur la même ligne, même sur une carte de téléphone.
const priceAmount = computed(() => formatGnf(props.product.price).replace(/\s*GNF$/, ''))
const ratingLabel = computed(() => (props.product.average_rating ?? 0).toFixed(1).replace('.', ','))

// --- Carrousel synchronisé -----------------------------------------------
// Le défilement lui-même est du CSS pur (scroll-snap) — l'observer ne sert
// qu'à savoir QUELLE photo est visible, pour que le libellé sous le prix
// (activeFrameLabel) suive le doigt sans code de scroll fait main.
const carouselRef = ref<HTMLElement | null>(null)
const frameRefs = ref<(HTMLElement | null)[]>([])
const activeFrameIndex = ref(0)
const activeFrameLabel = computed(() => frames.value[activeFrameIndex.value]?.label ?? null)

let frameObserver: IntersectionObserver | null = null

onMounted(() => {
  if (!hasCarousel.value || !carouselRef.value) return
  frameObserver = new IntersectionObserver(
    (entries) => {
      const mostVisible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0]
      if (!mostVisible) return
      const index = frameRefs.value.findIndex((el) => el === mostVisible.target)
      if (index !== -1) activeFrameIndex.value = index
    },
    { root: carouselRef.value, threshold: [0.6] },
  )
  for (const el of frameRefs.value) {
    if (el) frameObserver.observe(el)
  }
})

onBeforeUnmount(() => frameObserver?.disconnect())

async function quickAdd(event: MouseEvent) {
  // Un produit à variantes (couleur, taille…) ne peut pas être ajouté
  // directement depuis la carte — pas de sélection possible ici. On laisse
  // alors le clic remonter normalement vers le NuxtLink englobant plutôt que
  // de faire disparaître l'icône : elle sert à ouvrir la fiche pour choisir.
  if (hasVariants.value) return
  event.preventDefault()
  event.stopPropagation()
  if (isOutOfStock.value || adding.value) return

  if (!auth.isAuthenticated) {
    await router.push({ path: '/connexion', query: { redirect: `/produits/${props.product.id}` } })
    return
  }

  adding.value = true
  try {
    await cartStore.addItem(props.product.id, 1)
    toast.success('Ajouté au panier.')
    justAdded.value = true
    setTimeout(() => (justAdded.value = false), 1500)
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'ajouter ce produit au panier."))
  } finally {
    adding.value = false
  }
}
</script>

<template>
  <NuxtLink :to="`/produits/${product.id}`" class="product-card">
    <v-card class="product-card__card" :class="{ 'product-card__card--out': isOutOfStock }">
      <div class="product-card__image">
        <div v-if="hasCarousel" ref="carouselRef" class="product-card__carousel">
          <div
            v-for="(frame, i) in frames"
            :key="frame.image"
            :ref="(el) => (frameRefs[i] = el as HTMLElement | null)"
            class="product-card__frame"
          >
            <img :src="resolveImageUrl(frame.image, apiBase)" :alt="product.name" loading="lazy" />
          </div>
        </div>
        <img
          v-else-if="frames[0]"
          :src="resolveImageUrl(frames[0].image, apiBase)"
          :alt="product.name"
          loading="lazy"
        />
        <PhImage v-else :size="28" weight="light" color="var(--color-neutral-500)" />

        <!-- Purement informatifs (quel index est visible), jamais cliquables :
             le défilement se pilote au doigt sur la photo elle-même. -->
        <div v-if="hasCarousel" class="product-card__dots" aria-hidden="true">
          <span
            v-for="(frame, i) in frames"
            :key="frame.image"
            class="product-card__dot"
            :class="{ 'product-card__dot--active': i === activeFrameIndex }"
          />
        </div>

        <span v-if="isOutOfStock" class="product-card__stock-tag product-card__stock-tag--out">Rupture de stock</span>
        <span v-else-if="isLowStock" class="product-card__stock-tag product-card__stock-tag--low">Derniers exemplaires</span>

        <button
          v-if="!isOutOfStock"
          type="button"
          class="product-card__quick-add"
          :class="{ 'product-card__quick-add--done': justAdded }"
          :disabled="adding"
          :aria-label="hasVariants ? `Voir les options de ${product.name}` : `Ajouter ${product.name} au panier`"
          @click="quickAdd"
        >
          <PhShoppingCartSimple v-if="!justAdded" :size="16" weight="bold" />
          <span v-else class="product-card__quick-add-check">✓</span>
        </button>
      </div>
      <div class="product-card__body">
        <div class="product-card__name" :title="product.name">{{ product.name }}</div>

        <!-- Prix à gauche, note à droite : les deux infos d'achat sur une
             seule ligne. Un prix très long passe la note à la ligne (wrap)
             plutôt que de se faire tronquer sur les cartes étroites. -->
        <div class="product-card__meta">
          <span class="product-card__price" :class="{ 'product-card__price--long': priceAmount.length > 7 }">{{ priceAmount }}<span class="product-card__currency">GNF</span></span>
          <span
            v-if="hasRating"
            class="product-card__rating"
            :aria-label="`Noté ${ratingLabel} sur 5 (${product.review_count} avis)`"
          >
            <span class="stars" aria-hidden="true">
              <span class="stars__row stars__row--empty">
                <PhStar v-for="n in 5" :key="n" :size="12" weight="fill" />
              </span>
              <span class="stars__row stars__row--full" :style="{ width: `${ratingPct}%` }">
                <PhStar v-for="n in 5" :key="n" :size="12" weight="fill" />
              </span>
            </span>
            <span class="product-card__rating-value">{{ ratingLabel }}</span>
            <span class="product-card__rating-count">({{ product.review_count }})</span>
          </span>
          <span v-else class="product-card__rating product-card__rating--none" title="Pas encore d'avis">
            <span class="stars" aria-hidden="true">
              <span class="stars__row stars__row--empty">
                <PhStar v-for="n in 5" :key="n" :size="12" weight="fill" />
              </span>
            </span>
          </span>
        </div>

        <!-- Hauteur réservée même vide : toutes les cartes gardent la même
             hauteur qu'une caractéristique s'affiche ou non. Priorité : le
             libellé synchronisé avec la photo du carrousel affichée (ex.
             "Rouge" pendant qu'on swipe dessus) ; à défaut le résumé des
             attributs disponibles. -->
        <div class="product-card__tags">
          <span v-if="hasCarousel && activeFrameLabel" class="product-card__tag product-card__tag--variant">
            {{ activeFrameLabel }}
          </span>
          <span v-else-if="attributeSummary" class="product-card__tag">{{ attributeSummary }}</span>
        </div>

        <!-- Ligne dédiée, toujours réservée : le délai de livraison ne doit
             pas disparaître juste parce que le produit a des variantes. -->
        <div class="product-card__delivery">
          <span v-if="deliveryLabel" class="product-card__tag product-card__tag--delivery">
            <PhTruck :size="12" weight="bold" />
            {{ deliveryLabel }}
          </span>
        </div>

        <div class="product-card__shop">
          <PhStorefront :size="12" weight="bold" />
          <span>{{ product.vendor_shop_name }}</span>
        </div>
      </div>
    </v-card>
  </NuxtLink>
</template>

<style scoped>
.product-card {
  text-decoration: none;
  color: inherit;
  display: block;
  /* La grille (ProductGrid) étire déjà chaque item de rangée à la même
     hauteur (comportement grid par défaut) — sans cette hauteur explicite ici
     et sur .product-card__card ci-dessous, seule la zone cliquable suivrait,
     pas le cadre visuel de la carte, donc les bas de cartes resteraient
     décalés entre deux fiches de longueurs de nom différentes. */
  height: 100%;
}

.product-card__card {
  height: 100%;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-md);
  overflow: hidden;
  box-shadow: var(--shadow-sm) !important;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.product-card:hover .product-card__card {
  transform: translateY(-3px);
  box-shadow: var(--shadow-lg) !important;
  border-color: var(--color-divider-strong);
}

.product-card__card--out {
  opacity: 0.7;
}

.product-card__image {
  /* Carré plutôt qu'une bande basse et large : plus de hauteur pour que
     l'image se déploie vraiment, et un ratio stable quel que soit le format
     de la photo source. */
  position: relative;
  aspect-ratio: 1 / 1;
  display: flex;
  align-items: center;
  justify-content: center;
  /* Fond uni et clair : la plupart des photos produit sont détourées sur
     blanc, un dégradé gris les faisait paraître « posées » sur un bloc. */
  background: var(--color-neutral-800);
  overflow: hidden;
  padding: 8px;
  box-sizing: border-box;
}

.product-card__image img {
  width: 100%;
  height: 100%;
  /* "contain" plutôt que "cover" : l'image entière reste visible (jamais
     rognée), quitte à laisser un léger fond neutre sur les côtés pour les
     photos qui ne sont pas déjà carrées. */
  object-fit: contain;
}

/* Enfant DIRECT seulement (pas ">img" dans .product-card__carousel, plus
   bas) : l'effet de zoom au survol ne s'applique qu'à la photo unique sans
   carrousel — combiné au scroll-snap du carrousel, un zoom simultané sur
   toutes les photos aurait perturbé les points d'ancrage du défilement. */
.product-card__image > img {
  transition: transform 0.3s cubic-bezier(0.22, 1, 0.36, 1);
}

.product-card:hover .product-card__image > img {
  transform: scale(1.1);
}

/* :active plutôt que :hover seul : sur mobile (l'essentiel du trafic PWA,
   voir ProductGrid) il n'y a pas de survol — sans ce répondant au toucher,
   l'effet de zoom ne se verrait jamais en usage réel. */
.product-card:active .product-card__image > img {
  transform: scale(1.04);
}

.product-card__carousel {
  display: flex;
  width: 100%;
  height: 100%;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
}

.product-card__carousel::-webkit-scrollbar {
  display: none;
}

.product-card__frame {
  flex: 0 0 100%;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  scroll-snap-align: start;
  scroll-snap-stop: always;
}

.product-card__dots {
  position: absolute;
  bottom: 7px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 4px;
  z-index: 1;
}

.product-card__dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.5);
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.15);
  transition: transform 0.15s ease, background 0.15s ease;
}

.product-card__dot--active {
  background: #fff;
  transform: scale(1.35);
}

.product-card__stock-tag {
  position: absolute;
  top: 8px;
  left: 8px;
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: 0.02em;
  padding: 3px 7px;
  border-radius: 999px;
  color: #fff;
  text-transform: uppercase;
}

.product-card__stock-tag--low {
  background: var(--color-accent);
}

.product-card__stock-tag--out {
  background: var(--color-neutral-400);
}

.product-card__quick-add {
  position: absolute;
  bottom: 8px;
  right: 8px;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  /* Orange comme le prix (--color-accent) plutôt que le bleu primary habituel
     — associe visuellement le bouton d'ajout rapide au prix qu'il ajoute au
     panier, cohérent avec la charte "orange = ce qui accroche l'œil sur le
     prix/l'achat" déjà utilisée sur la carte (prix, étoiles de notation). */
  background: var(--color-accent);
  color: #fff;
  box-shadow: var(--shadow-md);
  transition: transform 0.15s ease, background 0.15s ease;
}

.product-card__quick-add:active {
  transform: scale(0.9);
}

.product-card__quick-add--done {
  background: var(--color-success);
}

.product-card__quick-add-check {
  font-size: 14px;
  font-weight: 700;
  line-height: 1;
}

.product-card__body {
  display: flex;
  flex-direction: column;
  /* Comble le reste de la carte étirée par la grille, pour que le nom de
     boutique s'aligne en bas d'une rangée quelle que soit la longueur du nom. */
  flex: 1;
  padding: 10px 9px 9px;
  /* Les règles @container plus bas adaptent la ligne prix/note à la largeur
     réelle de la carte (2 colonnes sur téléphone, 4-6 sur desktop). */
  container-type: inline-size;
}

.product-card__name {
  font-size: 13.5px;
  font-weight: 600;
  line-height: 1.35;
  /* 2 lignes maximum, hauteur toujours réservée pour 2 : prix et note
     tombent à la même hauteur sur toute une rangée. */
  min-height: 2.7em;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  color: var(--color-neutral-200);
}

.product-card__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 2px 8px;
  margin-top: 8px;
}

.product-card__price {
  font-family: var(--font-heading);
  font-size: 16px;
  font-weight: 800;
  letter-spacing: -0.01em;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
  /* Prix en orange, seule dérogation à la charte primary (bleu) sur la
     carte — même logique que les étoiles : accroche l'œil sur ce qui doit
     se voir en premier. */
  color: var(--color-accent);
}

.product-card__rating {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
  white-space: nowrap;
  font-size: 12px;
  line-height: 1;
}

.product-card__rating--none {
  opacity: 0.55;
}

.stars {
  position: relative;
  display: inline-flex;
}

.stars__row {
  display: inline-flex;
  gap: 1px;
}

.stars__row--empty {
  color: var(--color-neutral-600);
}

.stars__row--full {
  position: absolute;
  inset: 0 auto 0 0;
  overflow: hidden;
  color: var(--color-accent);
}

.stars__row svg {
  flex: none;
}

.product-card__rating-value {
  font-family: var(--font-heading);
  font-weight: 800;
  color: var(--color-neutral-200);
}

.product-card__rating-count {
  font-weight: 500;
  color: var(--color-neutral-400);
}

.product-card__currency {
  margin-left: 3px;
  font-size: 0.68em;
  font-weight: 700;
}

/* Carte étroite (2 colonnes sur téléphone) : étoiles et note restent sur la
   ligne du prix, en plus compact ; seul le nombre d'avis s'efface. */
@container (max-width: 200px) {
  .product-card__rating-count {
    display: none;
  }

  .product-card__price {
    font-size: 15px;
  }

  /* Montant à 7 chiffres et plus (« 1 250 000 ») : un cran plus petit pour
     laisser la note sur la même ligne. */
  .product-card__price--long {
    font-size: 13.5px;
  }

  .product-card__rating {
    gap: 3px;
    font-size: 11px;
  }

  .stars__row {
    gap: 0;
  }

  .stars__row svg {
    width: 10px;
    height: 10px;
  }
}

/* Toujours présente (même vide) pour que la hauteur de la carte ne varie
   pas selon qu'une caractéristique s'affiche ou non. */
.product-card__tags {
  min-height: 1.6em;
  margin-top: 6px;
  display: flex;
  align-items: center;
}

.product-card__delivery {
  min-height: 1.6em;
  margin-bottom: 6px;
  display: flex;
  align-items: center;
}

.product-card__tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--color-neutral-300);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Libellé synchronisé avec la photo du carrousel affichée — distinct du gris
   neutre pour bien montrer qu'il vient de changer avec le défilement. */
.product-card__tag--variant {
  color: var(--color-primary);
}

/* Un délai de livraison est une info rassurante : vert (--color-success,
   déjà utilisé pour « ajouté au panier »), sobre à côté de l'orange du prix. */
.product-card__tag--delivery {
  color: var(--color-success);
}

.product-card__shop {
  display: flex;
  align-items: center;
  gap: 5px;
  /* Poussé en bas de la carte (flex column) et séparé du reste par un filet :
     repère aligné sur toute la rangée. */
  margin-top: auto;
  padding-top: 8px;
  border-top: 1px solid var(--color-divider);
  font-size: 12px;
  font-weight: 500;
  color: var(--color-neutral-400);
  min-width: 0;
}

.product-card__shop span {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.product-card__shop svg {
  flex: none;
}
</style>
