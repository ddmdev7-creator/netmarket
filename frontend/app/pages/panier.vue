<script setup lang="ts">
import { PhImage, PhX } from '@phosphor-icons/vue'

definePageMeta({ middleware: 'auth' })

const cartStore = useCartStore()
const router = useRouter()
const apiBase = useApiBase()

// pending matters here: cartStore.cart is null/undefined until this resolves,
// which would otherwise read as "empty" (hasItems below) and flash the wrong
// empty-state message during the initial fetch.
const { pending } = await useAsyncData('panier-cart', () => cartStore.fetchCart())

const itemCount = computed(() => cartStore.itemCount)
const hasItems = computed(() => (cartStore.cart?.vendors.length ?? 0) > 0)

async function updateQty(itemId: string, quantity: number) {
  if (quantity < 1) return
  await cartStore.updateItem(itemId, quantity)
}

async function removeItem(itemId: string) {
  await cartStore.removeItem(itemId)
}

function goCheckout() {
  router.push('/checkout')
}
</script>

<template>
  <!-- Pas de .app-shell ici : layouts/default.vue en fournit déjà un (avec
       app-shell--catalog pour cette route, voir ce fichier) -- un deuxième
       wrapper imbriqué ici l'aurait juste re-plafonné à 720px par défaut,
       annulant l'élargissement du bandeau du haut au-dessus. .cart-inner
       recentre uniquement LE CONTENU de cette page sur une largeur
       confortable, sans replafonner LayoutTopBar avec. -->
  <div class="cart-inner" style="padding-bottom: 88px">
    <div class="pa-3">
      <h1 class="text-h6">Mon panier ({{ itemCount }} article{{ itemCount > 1 ? 's' : '' }})</h1>
    </div>

    <div class="px-4 cart-page">
        <div class="cart-list">
          <div v-if="pending">
            <v-skeleton-loader v-for="n in 2" :key="n" type="list-item-two-line" class="mb-2" />
          </div>
          <CommonEmptyState v-else-if="!hasItems" message="Votre panier est vide." />

          <template v-else>
            <div v-for="group in cartStore.cart!.vendors" :key="group.vendor_id" class="vendor-group">
              <div class="vendor-group__header">{{ group.shop_name }}</div>

              <div v-for="item in group.items" :key="item.id" class="cart-row">
                <NuxtLink :to="`/produits/${item.product_id}`" class="cart-row__thumb">
                  <img
                    v-if="item.product_image"
                    :src="resolveImageUrl(item.product_image, apiBase)"
                    :alt="item.product_name"
                    loading="lazy"
                  />
                  <PhImage v-else :size="20" weight="light" color="var(--color-neutral-500)" />
                </NuxtLink>
                <div class="flex-grow-1">
                  <div class="text-meta">{{ item.product_name }}</div>
                  <div v-if="item.variant_label" class="text-muted text-fine">{{ item.variant_label }}</div>
                  <div class="d-flex justify-space-between align-center mt-1">
                    <div class="qty-selector">
                      <button type="button" @click="updateQty(item.id, item.quantity - 1)">−</button>
                      <span>{{ item.quantity }}</span>
                      <button type="button" @click="updateQty(item.id, item.quantity + 1)">+</button>
                    </div>
                    <span class="text-meta" style="font-weight: 600">{{ formatGnf(item.subtotal) }}</span>
                  </div>
                </div>
                <button class="cart-row__remove" aria-label="Retirer cet article" @click="removeItem(item.id)">
                  <PhX :size="14" />
                </button>
              </div>

              <div class="d-flex justify-space-between text-muted mt-2 text-meta">
                <span>Sous-total {{ group.shop_name }}</span>
                <span>{{ formatGnf(group.subtotal) }}</span>
              </div>
              <v-divider class="my-3" />
            </div>

            <!-- Repris dans .cart-summary sur ordinateur (voir plus bas) — l'un
                 des deux est toujours masqué par media query, jamais les deux
                 à la fois. -->
            <div class="cart-total-inline d-flex justify-space-between mt-2 text-lg">
              <span>Total</span>
              <span>{{ formatGnf(cartStore.cart!.total) }}</span>
            </div>
          </template>
        </div>

        <!-- Résumé fixe (sticky) : n'existe qu'à partir de 960px (voir CSS) —
             sur mobile, le total reste inline ci-dessus et le bouton dans la
             barre collante en bas (.checkout-bar). Sans cette colonne, la
             moitié droite d'un grand écran resterait un vide inutilisé. -->
        <aside v-if="hasItems" class="cart-summary">
          <div class="cart-summary__title">Résumé</div>
          <div class="d-flex justify-space-between text-lg mb-4">
            <span>Total</span>
            <span>{{ formatGnf(cartStore.cart!.total) }}</span>
          </div>
          <v-btn color="primary" block size="large" @click="goCheckout">Passer à la commande</v-btn>
        </aside>
      </div>
    </div>

    <div v-if="hasItems" class="checkout-bar checkout-bar--mobile-only">
      <v-btn color="primary" block size="large" @click="goCheckout">Passer à la commande</v-btn>
    </div>
</template>

<style scoped>
/* Sur mobile, une seule colonne : le résumé (.cart-summary) n'existe pas
   encore, le total reste inline et le bouton vit dans la barre collante du
   bas. */
.cart-summary {
  display: none;
}

/* .app-shell--catalog (voir main.css) n'est plus plafonné sur ordinateur --
   le bandeau du haut (LayoutTopBar) va ainsi bord à bord comme sur l'accueil
   -- mais un panier n'a pas vocation à s'étirer sur toute la largeur d'un
   écran 1920px comme une grille de produits : .cart-inner recentre le
   contenu (titre + liste + résumé) sur une largeur confortable. */
@media (min-width: 960px) {
  .cart-inner {
    max-width: 1120px;
    margin: 0 auto;
  }
}

/* À partir de cette largeur, un vrai layout à deux colonnes (liste + résumé
   fixe) utilise l'espace gagné au lieu de laisser la liste seule s'étirer
   avec un grand vide entre le sélecteur de quantité et le prix de chaque
   ligne, ou de laisser toute la moitié droite de .cart-inner inoccupée. */
@media (min-width: 960px) {
  .cart-page {
    display: grid;
    grid-template-columns: 1fr 320px;
    align-items: start;
    gap: 32px;
  }

  .cart-total-inline {
    /* Remplacé par .cart-summary à cette largeur. */
    display: none;
  }

  .cart-summary {
    display: block;
    position: sticky;
    top: 16px;
    padding: 20px;
    background: var(--color-neutral-900);
    border: 1px solid var(--color-divider);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-md);
  }

  /* Redondant avec le bouton de .cart-summary à cette largeur. */
  .checkout-bar--mobile-only {
    display: none;
  }
}

.cart-summary__title {
  font-family: var(--font-heading);
  font-weight: 700;
  font-size: 15px;
  margin-bottom: 14px;
}

/* This page keeps the default layout's bottom nav (unlike checkout/produit
   which use the blank layout), so the shared .checkout-bar — normally flush
   with the screen bottom — has to sit above it instead of underneath it.
   That bottom nav is hidden on desktop (see BottomNav.vue), so the bar goes
   back to being flush with the screen bottom there — moot now that it's
   hidden at that width (see .checkout-bar--mobile-only above), kept for
   the brief window before the 960px breakpoint kicks in on a resize. */
.checkout-bar {
  bottom: 76px;
  z-index: 6;
}

@media (min-width: 960px) {
  .checkout-bar {
    bottom: 0;
  }
}

.vendor-group__header {
  font-size: 11px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--color-neutral-400);
  margin-bottom: 6px;
}

.cart-row {
  display: flex;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid var(--color-divider);
}

.cart-row:last-of-type {
  border-bottom: none;
}

.cart-row__thumb {
  width: 56px;
  height: 56px;
  flex: none;
  border-radius: var(--radius-sm);
  background: var(--color-neutral-800);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.cart-row__thumb img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.cart-row__remove {
  background: none;
  border: none;
  color: var(--color-neutral-600);
  align-self: flex-start;
  /* Icon is 14px — padding brings the actual tap target to a proper mobile size. */
  padding: 10px;
  margin: -10px -10px 0 0;
  cursor: pointer;
}
</style>
