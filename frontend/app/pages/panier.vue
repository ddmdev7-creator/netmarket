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
  <div class="app-shell app-shell--wide" style="padding-bottom: 88px">
    <div class="pa-3">
      <h1 class="text-h6">Mon panier ({{ itemCount }} article{{ itemCount > 1 ? 's' : '' }})</h1>
    </div>

    <div class="px-4 cart-list">
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

        <div class="d-flex justify-space-between mt-2 text-lg">
          <span>Total</span>
          <span>{{ formatGnf(cartStore.cart!.total) }}</span>
        </div>
      </template>
    </div>

    <div v-if="hasItems" class="checkout-bar checkout-bar--wide">
      <v-btn color="primary" block size="large" @click="goCheckout">Passer à la commande</v-btn>
    </div>
  </div>
</template>

<style scoped>
/* La page utilise .app-shell--wide (960px, voir main.css) pour ne plus
   flotter en colonne étroite sur desktop, mais chaque ligne d'article garde
   une largeur de lecture confortable (comme .form-panel dans les
   back-offices) -- sans ce plafond, le sélecteur de quantité et le prix de
   chaque ligne se retrouveraient à des centaines de pixels l'un de l'autre,
   avec un grand vide entre les deux. */
@media (min-width: 960px) {
  .cart-list {
    max-width: 600px;
  }
}

/* This page keeps the default layout's bottom nav (unlike checkout/produit
   which use the blank layout), so the shared .checkout-bar — normally flush
   with the screen bottom — has to sit above it instead of underneath it.
   That bottom nav is hidden on desktop (see BottomNav.vue), so the bar goes
   back to being flush with the screen bottom there. */
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
