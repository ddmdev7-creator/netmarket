<script setup lang="ts">
import { PhArrowLeft, PhImage, PhMotorcycle, PhStorefront, PhUser } from '@phosphor-icons/vue'
import type { AdminOrderRead } from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const route = useRoute()
const router = useRouter()
const { apiFetch } = useApi()
const apiBase = useApiBase()

const orderId = route.params.id as string

const { data: order, error } = await useAsyncData(`admin-order-${orderId}`, () =>
  apiFetch<AdminOrderRead>(`/admin/orders/${orderId}`),
)

const tab = ref<'commande' | 'boutique' | 'acheteur' | 'livreur'>('commande')

function shortId(id: string) {
  return `#GN-${id.slice(0, 5).toUpperCase()}`
}
function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <div class="dashboard-shell">
    <div v-if="error">
      <CommonEmptyState message="Commande introuvable." />
    </div>

    <template v-else-if="order">
      <div class="d-flex align-center ga-2 mb-4">
        <v-btn icon variant="text" size="small" @click="router.back()">
          <PhArrowLeft :size="18" />
        </v-btn>
        <h1 class="text-h6 mb-0">Commande {{ shortId(order.id) }}</h1>
        <StatusBadge :status="order.status" />
      </div>

      <div class="summary-bar mb-5">
        <div>
          <div class="text-muted text-fine">Passée le</div>
          <div style="font-weight: 600">{{ formatDate(order.created_at) }}</div>
        </div>
        <div>
          <div class="text-muted text-fine">Paiement</div>
          <div style="font-weight: 600">
            {{ order.payment_method === 'cash_on_delivery' ? 'À la livraison' : order.payment_method }}
            · {{ order.payment_status ?? '—' }}
          </div>
        </div>
        <div>
          <div class="text-muted text-fine">Total</div>
          <div class="amount">{{ formatGnf(order.total) }}</div>
        </div>
      </div>

      <v-tabs v-model="tab" color="primary" class="mb-5">
        <v-tab value="commande">Commande</v-tab>
        <v-tab value="boutique">Boutique</v-tab>
        <v-tab value="acheteur">Acheteur</v-tab>
        <v-tab value="livreur">Livreur</v-tab>
      </v-tabs>

      <v-window v-model="tab">
        <v-window-item value="commande">
          <div class="panel-card mb-3" v-for="so in order.sub_orders" :key="so.id">
            <div class="panel-card__header">
              <span class="panel-card__title">{{ so.shop_name }}</span>
              <StatusBadge :status="so.status" />
            </div>
            <div class="panel-card__body">
              <div v-for="item in so.items" :key="item.id" class="order-item-row mb-2">
                <div class="order-item-row__thumb">
                  <img
                    v-if="item.product_image"
                    :src="resolveImageUrl(item.product_image, apiBase)"
                    :alt="item.product_name"
                    loading="lazy"
                  />
                  <PhImage v-else :size="20" weight="light" color="var(--color-neutral-500)" />
                </div>
                <span class="order-item-row__label" style="font-size: 13px"
                  >{{ item.product_name }}<span v-if="item.variant_label" class="text-muted"> ({{ item.variant_label }})</span> ×
                  {{ item.quantity }}</span
                >
                <span style="font-size: 13px; font-weight: 600">{{ formatGnf(item.unit_price * item.quantity) }}</span>
              </div>

              <v-divider class="my-2" />

              <div class="d-flex justify-space-between" style="font-size: 13px">
                <span class="text-muted">Montant · commission {{ formatGnf(so.commission) }}</span>
                <span style="font-weight: 700">{{ formatGnf(so.amount) }}</span>
              </div>
              <p
                v-if="so.estimated_delivery_min && so.estimated_delivery_max"
                class="text-muted mt-2 mb-0"
                style="font-size: 12px"
              >
                Livraison estimée :
                <strong>{{ formatDeliveryEstimate(so.estimated_delivery_min, so.estimated_delivery_max) }}</strong>
              </p>
              <p v-if="so.storage_location" class="text-muted mt-1 mb-0" style="font-size: 12px">
                Emplacement au point de retrait : <strong>{{ so.storage_location }}</strong>
              </p>
            </div>
          </div>

          <div class="panel-card">
            <div class="panel-card__header">
              <span class="panel-card__title">Livraison</span>
            </div>
            <div class="panel-card__body">
              <OrderDeliveryDetails
                :zone="order.delivery_zone"
                :address="order.delivery_address"
                :instructions="order.delivery_instructions"
                :delivery-type="order.delivery_type"
                :recipient-name="order.recipient_name"
                :recipient-phone="order.recipient_phone"
                :pickup-point-contacts="order.pickup_point_contacts"
              />
            </div>
          </div>
        </v-window-item>

        <v-window-item value="boutique">
          <div class="panel-card mb-3" v-for="so in order.sub_orders" :key="so.id">
            <div class="panel-card__header">
              <span class="panel-card__title">{{ so.shop_name }}</span>
            </div>
            <div class="panel-card__body">
              <div v-if="so.vendor_owner_full_name || so.vendor_owner_phone" class="d-flex align-center ga-2 mb-2">
                <PhStorefront :size="18" color="var(--color-primary)" />
                <div>
                  <div style="font-weight: 600">{{ so.vendor_owner_full_name ?? 'Nom non renseigné' }}</div>
                  <div class="text-muted text-meta">
                    {{ so.vendor_owner_phone }}<span v-if="so.vendor_owner_email"> · {{ so.vendor_owner_email }}</span>
                  </div>
                </div>
              </div>
              <p v-else class="text-muted mb-0" style="font-size: 13px">Compte introuvable pour cette boutique.</p>
            </div>
          </div>
        </v-window-item>

        <v-window-item value="acheteur">
          <div class="panel-card">
            <div class="panel-card__header">
              <span class="panel-card__title">Acheteur</span>
            </div>
            <div class="panel-card__body">
              <div class="d-flex align-center ga-2 mb-3">
                <PhUser :size="18" color="var(--color-primary)" />
                <div>
                  <div style="font-weight: 600">{{ order.buyer_full_name ?? 'Nom non renseigné' }}</div>
                  <div class="text-muted text-meta">
                    {{ order.buyer_phone }}<span v-if="order.buyer_email"> · {{ order.buyer_email }}</span>
                  </div>
                </div>
              </div>
              <v-divider class="mb-3" />
              <OrderDeliveryDetails
                :zone="order.delivery_zone"
                :address="order.delivery_address"
                :instructions="order.delivery_instructions"
                :delivery-type="order.delivery_type"
                :recipient-name="order.recipient_name"
                :recipient-phone="order.recipient_phone"
                :pickup-point-contacts="order.pickup_point_contacts"
              />
            </div>
          </div>
        </v-window-item>

        <v-window-item value="livreur">
          <div class="panel-card mb-3" v-for="so in order.sub_orders" :key="so.id">
            <div class="panel-card__header">
              <span class="panel-card__title">{{ so.shop_name }}</span>
            </div>
            <div class="panel-card__body">
              <div v-if="so.courier_name" class="d-flex align-center ga-2">
                <PhMotorcycle :size="18" color="var(--color-primary)" />
                <div>
                  <div style="font-weight: 600">{{ so.courier_name }}</div>
                  <div class="text-muted text-meta">{{ so.courier_phone }}</div>
                </div>
              </div>
              <p v-else class="text-muted mb-0" style="font-size: 13px">Aucun livreur assigné.</p>
            </div>
          </div>
        </v-window-item>
      </v-window>
    </template>
  </div>
</template>

<style scoped>
.summary-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  padding: 14px 16px;
  border-radius: var(--radius-lg);
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider);
}

.amount {
  font-family: var(--font-heading);
  font-weight: 700;
  color: var(--color-primary-300);
}

.panel-card {
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}

.panel-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--color-primary-800);
}

.panel-card__title {
  font-weight: 700;
  font-size: 13.5px;
  color: var(--color-primary-100);
}

.panel-card__body {
  padding: 16px;
}

.order-item-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.order-item-row__thumb {
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

.order-item-row__thumb img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.order-item-row__label {
  flex: 1 1 auto;
  min-width: 0;
}
</style>
