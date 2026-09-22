<script setup lang="ts">
import { PhImage, PhShoppingCartSimple, PhStar, PhTruck } from '@phosphor-icons/vue'
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
      <v-card-text class="pa-2 product-card__body">
        <div class="product-card__name">{{ product.name }}</div>

        <div class="product-card__meta">
          <span class="product-card__price">{{ formatGnf(product.price) }}</span>
          <span v-if="product.average_rating !== null" class="product-card__rating">
            <PhStar :size="10" weight="fill" color="var(--color-accent)" />
            <span>{{ product.average_rating.toFixed(1) }}</span>
            <span v-if="product.review_count > 0" class="product-card__rating-count">({{ product.review_count }})</span>
          </span>
        </div>

        <!-- Hauteur réservée même vide : toutes les cartes gardent la même
             hauteur naturelle qu'une caractéristique s'affiche ou non, sans
             dépendre du seul étirement de la grille. Priorité : le libellé
             synchronisé avec la photo du carrousel affichée (ex. "Rouge"
             pendant qu'on swipe dessus) ; à défaut le résumé des attributs
             disponibles. -->
        <div class="product-card__tags">
          <span v-if="hasCarousel && activeFrameLabel" class="product-card__tag product-card__tag--variant">
            {{ activeFrameLabel }}
          </span>
          <span v-else-if="attributeSummary" class="product-card__tag">{{ attributeSummary }}</span>
        </div>

        <!-- Ligne dédiée, toujours réservée (hauteur constante même sans
             estimation) — distincte de .product-card__tags ci-dessus : le
             délai de livraison ne doit pas disparaître juste parce que le
             produit a des variantes (voir attributeSummary), c'est une info
             utile pour tout le monde, pas seulement les produits sans
             variante. -->
        <div class="product-card__delivery">
          <span v-if="deliveryLabel" class="product-card__tag">
            <PhTruck :size="10" weight="bold" />
            {{ deliveryLabel }}
          </span>
        </div>

        <div class="product-card__shop">{{ product.vendor_shop_name }}</div>
      </v-card-text>
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
  border-radius: var(--radius-md);
  overflow: hidden;
  transition: transform 0.18s ease, box-shadow 0.18s ease;
}

.product-card:hover .product-card__card {
  transform: translateY(-3px);
  box-shadow: var(--shadow-lg) !important;
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
  background: linear-gradient(180deg, var(--color-neutral-800) 0%, var(--color-neutral-700) 100%);
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
     boutique s'aligne en bas d'une rangée même quand les noms de produit
     font 1 ou 2 lignes selon la fiche. */
  flex: 1;
}

.product-card__name {
  font-size: 13.5px;
  font-weight: 500;
  line-height: 1.32;
  min-height: 2.64em;
  /* 200 = ton "texte fort" de l'échelle neutre (voir main.css) — la valeur
     "100" utilisée ici avant n'existe pas dans l'échelle (900→200 seulement),
     donc ce texte, le plus important de la carte après le prix, dépendait
     par erreur d'une couleur de repli du framework plutôt que du thème. */
  color: var(--color-neutral-200);
}

.product-card__meta {
  display: grid;
  /* Colonnes symétriques (1fr / auto / 1fr) plutôt qu'un simple flex : le
     prix reste au centre EXACT de la rangée, avec ou sans pastille de note,
     au lieu de se décaler vers la gauche dès qu'elle apparaît. */
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  margin-top: 5px;
}

.product-card__price {
  grid-column: 2;
  text-align: center;
  font-family: var(--font-heading);
  font-size: 15px;
  font-weight: 700;
  /* Prix en orange, seule dérogation à la charte primary (bleu) sur la
     carte — même logique que les étoiles de notation : accroche l'œil sur
     ce qui doit se voir en premier, comme sur une fiche produit Ozon. */
  color: var(--color-accent);
}

.product-card__rating {
  grid-column: 3;
  justify-self: end;
  display: flex;
  align-items: center;
  gap: 2px;
  font-size: 10.5px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 999px;
  /* Pastille : reprend l'orange des étoiles en fond très léger pour que la
     note reste identifiable au premier coup d'œil sans rivaliser avec le
     prix, qui doit rester l'élément le plus fort de la carte. */
  background: color-mix(in srgb, var(--color-accent) 14%, transparent);
  color: var(--color-accent);
}

.product-card__rating-count {
  font-weight: 500;
  opacity: 0.8;
}

/* Toujours présente (même vide) pour que la caractéristique du dessous
   (délai de livraison / variantes) ne fasse pas varier la hauteur naturelle
   de la carte selon qu'elle s'affiche ou non — voir deliveryLabel plus haut. */
.product-card__tags {
  min-height: 1.5em;
  margin-top: 4px;
  display: flex;
  align-items: center;
}

.product-card__delivery {
  min-height: 1.5em;
  display: flex;
  align-items: center;
}

.product-card__tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  min-width: 0;
  font-size: 10px;
  font-weight: 600;
  /* 300 plutôt que 400 : cette ligne porte une vraie info utile à l'achat
     (couleur, délai) — elle doit se lire aussi facilement que le nom de
     boutique juste en dessous, pas se fondre dans le fond. */
  color: var(--color-neutral-300);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Libellé synchronisé avec la photo du carrousel affichée — distinct du gris
   neutre des autres caractéristiques pour bien montrer que ça vient de
   changer avec le défilement, pas juste une info statique de plus. */
.product-card__tag--variant {
  color: var(--color-primary);
}

.product-card__shop {
  font-size: 11px;
  font-weight: 500;
  /* 400 plutôt que 500 : reste clairement secondaire (nom de boutique, pas
     l'info principale) tout en restant lisible sans plisser les yeux. */
  color: var(--color-neutral-400);
  /* auto plutôt qu'une valeur fixe : pousse le nom de boutique en bas de
     .product-card__body (flex column, flex: 1), pour aligner ce repère sur
     toute une rangée même quand les noms de produit font 1 ou 2 lignes. */
  margin-top: auto;
  padding-top: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
