<script setup lang="ts">
import { PhImage, PhShoppingCartSimple, PhStar } from '@phosphor-icons/vue'
import type { ProductRead } from '~/types/api'

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

async function quickAdd(event: MouseEvent) {
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
        <img
          v-if="product.images[0]"
          :src="resolveImageUrl(product.images[0], apiBase)"
          :alt="product.name"
          loading="lazy"
        />
        <PhImage v-else :size="28" weight="light" color="var(--color-neutral-500)" />

        <span v-if="isOutOfStock" class="product-card__stock-tag product-card__stock-tag--out">Rupture de stock</span>
        <span v-else-if="isLowStock" class="product-card__stock-tag product-card__stock-tag--low">Derniers exemplaires</span>

        <button
          v-if="!isOutOfStock && product.variants.length === 0"
          type="button"
          class="product-card__quick-add"
          :class="{ 'product-card__quick-add--done': justAdded }"
          :disabled="adding"
          :aria-label="`Ajouter ${product.name} au panier`"
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
  transition: transform 0.25s ease;
}

.product-card:hover .product-card__image img {
  transform: scale(1.06);
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
  font-size: 12.5px;
  line-height: 1.3;
  min-height: 2.6em;
}

.product-card__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  margin-top: 4px;
}

.product-card__price {
  font-family: var(--font-heading);
  font-size: 13.5px;
  font-weight: 700;
  /* Prix en orange, seule dérogation à la charte primary (bleu) sur la
     carte — même logique que les étoiles de notation : accroche l'œil sur
     ce qui doit se voir en premier, comme sur une fiche produit Ozon. */
  color: var(--color-accent);
}

.product-card__rating {
  display: flex;
  align-items: center;
  gap: 2px;
  flex: none;
  font-size: 10px;
  font-weight: 600;
  padding: 2px 5px;
  border-radius: 999px;
  /* Pastille : reprend l'orange des étoiles en fond très léger pour que la
     note reste identifiable au premier coup d'œil sans rivaliser avec le
     prix, qui doit rester l'élément le plus fort de la carte. */
  background: color-mix(in srgb, var(--color-accent) 14%, transparent);
  color: var(--color-accent);
}

.product-card__shop {
  font-size: 10.5px;
  color: var(--color-neutral-500);
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
