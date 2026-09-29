<script setup lang="ts">
import { PhArrowCounterClockwise, PhGift, PhImage, PhShieldCheck, PhShoppingCart, PhTrash, PhTruck } from '@phosphor-icons/vue'
import type { VendorCartGroup } from '~/types/api'

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

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join('')
}

function offerReached(group: VendorCartGroup) {
  return group.pickup_offer_min != null && group.subtotal >= group.pickup_offer_min
}

function goCheckout() {
  router.push('/checkout')
}
</script>

<template>
  <!-- Pas de .app-shell ici : layouts/default.vue en fournit déjà un (avec
       app-shell--catalog pour cette route, voir ce fichier). .cart-inner
       recentre uniquement le contenu de cette page. -->
  <div class="cart-inner">
    <header class="cart-head">
      <h1 class="text-h6 mb-0">Mon panier</h1>
      <span v-if="hasItems" class="cart-head__count">{{ itemCount }} article{{ itemCount > 1 ? 's' : '' }}</span>
    </header>

    <div class="cart-page">
      <div class="cart-list">
        <div v-if="pending" class="cart-card">
          <v-skeleton-loader v-for="n in 2" :key="n" type="list-item-avatar-two-line" class="mb-2" />
        </div>
        <div v-else-if="!hasItems" class="cart-card">
          <CommonEmptyState
            :icon="PhShoppingCart"
            title="Votre panier est vide"
            message="Parcourez le catalogue et ajoutez les produits qui vous plaisent."
            action-label="Découvrir les produits"
            action-to="/"
          >
            <NuxtLink to="/favoris" class="empty-link">Voir mes favoris</NuxtLink>
          </CommonEmptyState>
        </div>

        <template v-else>
          <section v-for="group in cartStore.cart!.vendors" :key="group.vendor_id" class="cart-card vendor-group">
            <header class="vendor-group__header">
              <span class="vendor-group__logo">{{ initials(group.shop_name) }}</span>
              <span class="vendor-group__name">{{ group.shop_name }}</span>
              <span class="vendor-group__subtotal">{{ formatGnf(group.subtotal) }}</span>
            </header>

            <div v-if="group.pickup_offer_min != null" class="offer" :class="{ 'offer--done': offerReached(group) }">
              <div class="offer__text">
                <PhGift :size="16" weight="fill" />
                <span v-if="offerReached(group)">Livraison en point de retrait <strong>offerte</strong> par la boutique.</span>
                <span v-else>
                  Plus que <strong>{{ formatGnf(group.pickup_offer_min - group.subtotal) }}</strong> pour un retrait offert.
                </span>
              </div>
              <div v-if="group.pickup_offer_min > 0" class="offer__bar" aria-hidden="true">
                <span :style="{ width: `${Math.min(100, (group.subtotal / group.pickup_offer_min) * 100)}%` }" />
              </div>
            </div>

            <div v-for="item in group.items" :key="item.id" class="cart-row">
              <NuxtLink :to="`/produits/${item.product_id}`" class="cart-row__thumb">
                <img
                  v-if="item.product_image"
                  :src="resolveImageUrl(item.product_image, apiBase, 160)"
                  :alt="item.product_name"
                  loading="lazy"
                />
                <PhImage v-else :size="22" weight="light" color="var(--color-neutral-500)" />
              </NuxtLink>
              <div class="cart-row__body">
                <div class="cart-row__top">
                  <NuxtLink :to="`/produits/${item.product_id}`" class="cart-row__name">{{ item.product_name }}</NuxtLink>
                  <button class="cart-row__remove" aria-label="Retirer cet article" @click="removeItem(item.id)">
                    <PhTrash :size="16" />
                  </button>
                </div>
                <div v-if="item.variant_label" class="cart-row__variant">{{ item.variant_label }}</div>
                <div class="cart-row__bottom">
                  <div class="qty-selector">
                    <button type="button" :disabled="item.quantity <= 1" aria-label="Diminuer" @click="updateQty(item.id, item.quantity - 1)">−</button>
                    <span>{{ item.quantity }}</span>
                    <button type="button" aria-label="Augmenter" @click="updateQty(item.id, item.quantity + 1)">+</button>
                  </div>
                  <div class="cart-row__price">
                    <strong>{{ formatGnf(item.subtotal) }}</strong>
                    <small v-if="item.quantity > 1">{{ formatGnf(item.unit_price) }} / unité</small>
                  </div>
                </div>
              </div>
            </div>

            <footer v-if="group.estimated_delivery_min && group.estimated_delivery_max" class="vendor-group__foot">
              <PhTruck :size="14" weight="bold" />
              Livraison estimée : <strong>{{ formatDeliveryEstimate(group.estimated_delivery_min, group.estimated_delivery_max) }}</strong>
            </footer>
          </section>
        </template>
      </div>

      <aside v-if="hasItems" class="cart-summary cart-card">
        <div class="cart-summary__title">Récapitulatif</div>
        <div class="sum-line">
          <span>Articles ({{ itemCount }})</span>
          <span>{{ formatGnf(cartStore.cart!.total) }}</span>
        </div>
        <div class="sum-line">
          <span>Livraison</span>
          <span class="text-muted">Calculée à l'étape suivante</span>
        </div>
        <div class="sum-line sum-line--total">
          <span>Total</span>
          <span>{{ formatGnf(cartStore.cart!.total) }}</span>
        </div>
        <v-btn color="primary" block size="large" class="mt-4" @click="goCheckout">Passer à la commande</v-btn>
        <ul class="cart-trust">
          <li><PhShieldCheck :size="15" /> Paiement sécurisé en ligne ou NdjouriBank</li>
          <li><PhArrowCounterClockwise :size="15" /> Annulation remboursée avant préparation</li>
        </ul>
      </aside>
    </div>

    <div v-if="hasItems" class="checkout-bar checkout-bar--mobile-only">
      <div class="dock">
        <div class="dock__total">
          <span class="dock__amount">{{ formatGnf(cartStore.cart!.total) }}</span>
          <span class="dock__meta">{{ itemCount }} article{{ itemCount > 1 ? 's' : '' }} · hors livraison</span>
        </div>
        <v-btn color="primary" size="large" @click="goCheckout">Commander</v-btn>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cart-inner {
  padding: 16px 16px 160px;
}

@media (min-width: 960px) {
  .cart-inner {
    max-width: 1160px;
    margin: 0 auto;
    padding: 24px 24px 48px;
  }
}

.cart-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 16px;
}

.cart-head__count {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-neutral-400);
}

.cart-page {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 16px;
}

@media (min-width: 960px) {
  .cart-page {
    grid-template-columns: minmax(0, 1fr) 340px;
    align-items: start;
    gap: 24px;
  }
}

.cart-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.cart-card {
  padding: 16px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-divider);
  background: var(--color-neutral-900);
  box-shadow: var(--shadow-sm);
}

@media (min-width: 960px) {
  .cart-card {
    padding: 20px 22px;
  }
}

.vendor-group__header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--color-divider);
}

.vendor-group__logo {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  border-radius: 10px;
  background: linear-gradient(135deg, hsl(152 68% 42%), hsl(190 70% 42%));
  color: #fff;
  font-size: 12px;
  font-weight: 800;
}

.vendor-group__name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-heading);
  font-size: 14.5px;
  font-weight: 800;
}

.vendor-group__subtotal {
  font-size: 13px;
  font-weight: 700;
  color: var(--color-neutral-300);
}

.offer {
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  background: var(--color-neutral-800);
  font-size: 12.5px;
  color: var(--color-neutral-300);
}

.offer--done {
  background: hsl(150 70% var(--tint-bg));
  color: hsl(150 55% var(--tint-fg));
}

.offer__text {
  display: flex;
  align-items: center;
  gap: 8px;
}

.offer__text svg {
  flex-shrink: 0;
  color: hsl(150 60% 45%);
}

.offer__bar {
  height: 5px;
  margin-top: 8px;
  border-radius: 999px;
  background: var(--color-neutral-700);
  overflow: hidden;
}

.offer__bar span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, hsl(152 68% 42%), hsl(170 70% 40%));
  transition: width 0.3s ease;
}

.cart-row {
  display: flex;
  gap: 14px;
  padding: 14px 0;
  border-bottom: 1px solid var(--color-divider);
}

.cart-row:last-of-type {
  border-bottom: none;
}

.cart-row__thumb {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 88px;
  height: 88px;
  flex: none;
  overflow: hidden;
  border-radius: var(--radius-md);
  background: var(--color-neutral-800);
}

.cart-row__thumb img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.cart-row__body {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.cart-row__top {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.cart-row__name {
  flex: 1;
  min-width: 0;
  color: inherit;
  font-size: 14px;
  font-weight: 700;
  line-height: 1.35;
  text-decoration: none;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.cart-row__name:hover {
  color: var(--color-primary-300);
}

.cart-row__variant {
  margin-top: 2px;
  font-size: 12px;
  color: var(--color-neutral-400);
}

.cart-row__bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: auto;
  padding-top: 10px;
}

.cart-row__price {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  line-height: 1.2;
}

.cart-row__price strong {
  font-family: var(--font-heading);
  font-size: 15px;
  font-weight: 800;
  color: var(--color-accent);
  font-variant-numeric: tabular-nums;
}

.cart-row__price small {
  font-size: 11px;
  color: var(--color-neutral-400);
}

.cart-row__remove {
  display: flex;
  padding: 6px;
  margin: -6px -6px 0 0;
  border: none;
  border-radius: 50%;
  background: none;
  color: var(--color-neutral-500);
  cursor: pointer;
}

.cart-row__remove:hover {
  background: hsl(355 80% var(--tint-bg));
  color: var(--color-error);
}

.vendor-group__foot {
  display: flex;
  align-items: center;
  gap: 6px;
  padding-top: 12px;
  border-top: 1px solid var(--color-divider);
  font-size: 12.5px;
  color: var(--color-neutral-400);
}

.vendor-group__foot svg {
  color: var(--color-success);
}

.vendor-group__foot strong {
  color: var(--color-neutral-200);
}

.cart-summary {
  display: none;
}

@media (min-width: 960px) {
  .cart-summary {
    display: block;
    position: sticky;
    top: 84px;
  }

  .checkout-bar--mobile-only {
    display: none;
  }
}

.cart-summary__title {
  margin-bottom: 14px;
  font-family: var(--font-heading);
  font-size: 15px;
  font-weight: 800;
}

.sum-line {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 6px 0;
  font-size: 13.5px;
}

.sum-line--total {
  margin-top: 6px;
  padding-top: 12px;
  border-top: 1px solid var(--color-divider);
  font-family: var(--font-heading);
  font-size: 17px;
  font-weight: 800;
}

.cart-trust {
  margin: 16px 0 0;
  padding: 0;
  list-style: none;
  font-size: 12px;
  color: var(--color-neutral-400);
}

.cart-trust li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 0;
}

.cart-trust svg {
  color: var(--color-success);
}

/* Cette page garde la barre de navigation du bas : la barre de commande se
   place au-dessus d'elle sur téléphone. */
.checkout-bar {
  bottom: 76px;
  z-index: 6;
}

.dock {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.dock__total {
  display: flex;
  flex-direction: column;
  line-height: 1.2;
}

.dock__amount {
  font-family: var(--font-heading);
  font-size: 17px;
  font-weight: 800;
}

.dock__meta {
  font-size: 11.5px;
  color: var(--color-neutral-400);
}

.empty-link {
  margin-top: 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-primary-300);
}
</style>
