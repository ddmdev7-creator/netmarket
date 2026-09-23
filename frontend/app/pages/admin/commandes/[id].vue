<script setup lang="ts">
import {
  PhArrowLeft,
  PhArrowSquareOut,
  PhImage,
  PhMagnifyingGlassPlus,
  PhMapPin,
  PhMotorcycle,
  PhStar,
  PhStorefront,
  PhUser,
} from '@phosphor-icons/vue'
import type { AdminOrderRead, CourierStatus, OrderItemRead, VehicleType, VendorStatus } from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const route = useRoute()
const router = useRouter()
const { apiFetch } = useApi()
const apiBase = useApiBase()

const orderId = route.params.id as string

const { data: order, error } = await useAsyncData(`admin-order-${orderId}`, () =>
  apiFetch<AdminOrderRead>(`/admin/orders/${orderId}`),
)

const vendorStatusLabels: Record<VendorStatus, string> = {
  pending: 'En attente de validation',
  approved: 'Approuvée',
  rejected: 'Rejetée',
  suspended: 'Suspendue',
}
const courierStatusLabels: Record<CourierStatus, string> = {
  pending: 'En attente de validation',
  approved: 'Approuvé',
  rejected: 'Rejeté',
  suspended: 'Suspendu',
}
const accountTone = (status: VendorStatus | CourierStatus) =>
  status === 'approved' ? 'success' : status === 'pending' ? 'warning' : 'error'
const vehicleLabels: Record<VehicleType, string> = { moto: 'Moto', taxi: 'Taxi', voiture: 'Voiture' }

function shortId(id: string) {
  return `#GN-${id.slice(0, 5).toUpperCase()}`
}
function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}
function formatDay(iso: string) {
  return new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' })
}
function mapsUrl(lat: number | null, lng: number | null) {
  return lat !== null && lng !== null ? `https://www.google.com/maps?q=${lat},${lng}` : null
}

// Agrandissement d'une photo produit — l'admin doit pouvoir identifier
// l'article sans ouvrir la fiche produit (qui a pu changer depuis).
const zoomed = ref<OrderItemRead | null>(null)
</script>

<template>
  <div class="dashboard-shell">
    <div v-if="error">
      <CommonEmptyState message="Commande introuvable." />
    </div>

    <template v-else-if="order">
      <div class="d-flex align-center ga-2 mb-4 flex-wrap">
        <v-btn icon variant="text" size="small" aria-label="Retour" @click="router.back()">
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
            {{ PAYMENT_METHOD_LABELS[order.payment_method].short }}
            · {{ order.payment_status ?? '—' }}
          </div>
        </div>
        <div>
          <div class="text-muted text-fine">Livraison</div>
          <div style="font-weight: 600">{{ order.delivery_type === 'pickup_point' ? 'Point de retrait' : 'À domicile' }}</div>
        </div>
        <div>
          <div class="text-muted text-fine">Total</div>
          <div class="amount">{{ formatGnf(order.total) }}</div>
        </div>
      </div>

      <!-- Un bloc par boutique : articles, puis la boutique et son livreur. -->
      <section v-for="so in order.sub_orders" :key="so.id" class="panel-card mb-5">
        <div class="panel-card__header">
          <span class="panel-card__title">{{ so.shop_name }}</span>
          <StatusBadge :status="so.status" />
        </div>
        <div class="panel-card__body">
          <div class="items">
            <div v-for="item in so.items" :key="item.id" class="item">
              <button
                v-if="item.product_image"
                type="button"
                class="item__photo item__photo--zoomable"
                :aria-label="`Agrandir la photo de ${item.product_name}`"
                @click="zoomed = item"
              >
                <img :src="resolveImageUrl(item.product_image, apiBase)" :alt="item.product_name" loading="lazy" />
                <span class="item__zoom"><PhMagnifyingGlassPlus :size="16" weight="bold" /></span>
              </button>
              <div v-else class="item__photo" title="Aucune photo (produit ou variante supprimé)">
                <PhImage :size="36" weight="light" color="var(--color-neutral-500)" />
              </div>
              <div class="item__info">
                <div class="item__name">{{ item.product_name }}</div>
                <div v-if="item.variant_label" class="text-muted text-meta">{{ item.variant_label }}</div>
                <div class="text-muted text-meta mt-1">
                  {{ item.quantity }} × {{ formatGnf(item.unit_price) }}
                </div>
                <div class="item__total">{{ formatGnf(item.unit_price * item.quantity) }}</div>
                <NuxtLink :to="`/produits/${item.product_id}`" target="_blank" class="ext-link mt-1">
                  Fiche produit <PhArrowSquareOut :size="13" />
                </NuxtLink>
              </div>
            </div>
          </div>

          <dl class="facts facts--inline mt-4">
            <div><dt>Montant</dt><dd>{{ formatGnf(so.amount) }}</dd></div>
            <div><dt>Commission</dt><dd>{{ formatGnf(so.commission) }}</dd></div>
            <div><dt>Frais de livraison</dt><dd>{{ formatGnf(so.delivery_fee) }}</dd></div>
            <div v-if="so.estimated_delivery_min && so.estimated_delivery_max">
              <dt>Livraison estimée</dt>
              <dd>{{ formatDeliveryEstimate(so.estimated_delivery_min, so.estimated_delivery_max) }}</dd>
            </div>
            <div v-if="so.storage_location"><dt>Emplacement au point</dt><dd>{{ so.storage_location }}</dd></div>
            <div><dt>Dernière mise à jour</dt><dd>{{ formatDate(so.updated_at) }}</dd></div>
          </dl>

          <div class="entities mt-4">
            <!-- Boutique -->
            <div class="entity">
              <div class="entity__head">
                <PhStorefront :size="18" color="var(--color-primary)" />
                <span>Boutique</span>
                <v-chip v-if="so.vendor" :color="accountTone(so.vendor.status)" size="x-small" variant="tonal" class="ms-auto">
                  {{ vendorStatusLabels[so.vendor.status] }}
                </v-chip>
              </div>
              <template v-if="so.vendor">
                <div class="entity__name">{{ so.vendor.shop_name }}</div>
                <p v-if="so.vendor.shop_name !== so.shop_name" class="text-muted text-meta mb-2">
                  Nom au moment de la commande : {{ so.shop_name }}
                </p>
                <dl class="facts">
                  <div><dt>Propriétaire</dt><dd>{{ so.vendor.owner_full_name ?? 'Nom non renseigné' }}</dd></div>
                  <div v-if="so.vendor.owner_phone">
                    <dt>Téléphone</dt><dd><a :href="`tel:${so.vendor.owner_phone}`">{{ so.vendor.owner_phone }}</a></dd>
                  </div>
                  <div v-if="so.vendor.owner_email">
                    <dt>E-mail</dt><dd><a :href="`mailto:${so.vendor.owner_email}`">{{ so.vendor.owner_email }}</a></dd>
                  </div>
                  <div><dt>Zone</dt><dd>{{ so.vendor.zone ?? '—' }}</dd></div>
                  <div>
                    <dt>Position</dt>
                    <dd>
                      <a v-if="mapsUrl(so.vendor.latitude, so.vendor.longitude)" :href="mapsUrl(so.vendor.latitude, so.vendor.longitude)!" target="_blank" rel="noopener" class="ext-link">
                        Voir sur la carte <PhArrowSquareOut :size="13" />
                      </a>
                      <span v-else class="text-muted">Non renseignée</span>
                    </dd>
                  </div>
                  <div><dt>Commission</dt><dd>{{ so.vendor.commission_rate }} %</dd></div>
                  <div><dt>Préparation</dt><dd>{{ so.vendor.preparation_days }} jour{{ so.vendor.preparation_days > 1 ? 's' : '' }}</dd></div>
                  <div><dt>Inscrite le</dt><dd>{{ formatDay(so.vendor.created_at) }}</dd></div>
                </dl>
              </template>
              <p v-else class="text-muted mb-0 text-meta">Boutique introuvable (supprimée ?).</p>
            </div>

            <!-- Livreur -->
            <div class="entity">
              <div class="entity__head">
                <PhMotorcycle :size="18" color="var(--color-primary)" />
                <span>Livreur</span>
                <v-chip v-if="so.courier" :color="accountTone(so.courier.status)" size="x-small" variant="tonal" class="ms-auto">
                  {{ courierStatusLabels[so.courier.status] }}
                </v-chip>
              </div>
              <template v-if="so.courier">
                <div class="courier-id">
                  <AdminCourierAvatar
                    :courier-id="so.courier.id"
                    :photo-key="so.courier.face_photo_key"
                    :name="so.courier.full_name"
                    :size="88"
                  />
                  <div style="min-width: 0">
                    <div class="entity__name">{{ so.courier.full_name ?? 'Nom non renseigné' }}</div>
                    <div class="d-flex align-center ga-1 text-meta">
                      <span class="online-dot" :class="{ 'online-dot--on': so.courier.is_online }" />
                      {{ so.courier.is_online ? 'En ligne' : 'Hors ligne' }}
                    </div>
                    <div v-if="so.courier.review_count > 0" class="d-flex align-center ga-1 mt-1 text-meta">
                      <PhStar :size="13" weight="fill" color="#e0a82e" />
                      {{ so.courier.average_rating?.toFixed(1) }} ({{ so.courier.review_count }} avis)
                    </div>
                    <p v-if="!so.courier.face_photo_key" class="text-muted text-fine mb-0 mt-1">Pas de photo enregistrée.</p>
                  </div>
                </div>
                <dl class="facts mt-3">
                  <div><dt>Téléphone</dt><dd><a :href="`tel:${so.courier.phone}`">{{ so.courier.phone }}</a></dd></div>
                  <div><dt>Engin</dt><dd>{{ vehicleLabels[so.courier.vehicle_type] }}<span v-if="so.courier.vehicle_name"> · {{ so.courier.vehicle_name }}</span></dd></div>
                  <div v-if="so.courier.vehicle_plate_number"><dt>Immatriculation</dt><dd>{{ so.courier.vehicle_plate_number }}</dd></div>
                  <div><dt>Zone</dt><dd>{{ so.courier.zone ?? '—' }}</dd></div>
                </dl>
              </template>
              <template v-else>
                <div class="courier-id">
                  <AdminCourierAvatar courier-id="" :photo-key="null" :name="null" :size="56" />
                  <p class="text-muted mb-0 text-meta">
                    <template v-if="so.dispatch_offered_courier_name">
                      Aucun livreur assigné — course proposée à <strong>{{ so.dispatch_offered_courier_name }}</strong>, en attente de réponse.
                    </template>
                    <template v-else>Aucun livreur assigné.</template>
                  </p>
                </div>
              </template>
            </div>
          </div>
        </div>
      </section>

      <div class="entities">
        <!-- Acheteur -->
        <section class="panel-card">
          <div class="panel-card__header">
            <span class="panel-card__title d-flex align-center ga-2"><PhUser :size="16" /> Acheteur</span>
            <v-chip v-if="order.buyer && !order.buyer.is_active" color="error" size="x-small" variant="tonal">Compte désactivé</v-chip>
          </div>
          <div class="panel-card__body">
            <template v-if="order.buyer">
              <div class="entity__name">{{ order.buyer.full_name ?? 'Nom non renseigné' }}</div>
              <dl class="facts mt-2">
                <div><dt>Téléphone</dt><dd><a :href="`tel:${order.buyer.phone}`">{{ order.buyer.phone }}</a></dd></div>
                <div>
                  <dt>E-mail</dt>
                  <dd>
                    <template v-if="order.buyer.email">
                      <a :href="`mailto:${order.buyer.email}`">{{ order.buyer.email }}</a>
                      <span class="text-muted"> · {{ order.buyer.email_verified ? 'vérifié' : 'non vérifié' }}</span>
                    </template>
                    <span v-else class="text-muted">—</span>
                  </dd>
                </div>
                <div><dt>Client depuis</dt><dd>{{ formatDay(order.buyer.created_at) }}</dd></div>
                <div><dt>Commandes</dt><dd>{{ order.buyer.order_count }}</dd></div>
              </dl>
            </template>
            <p v-else class="text-muted text-meta">Compte acheteur introuvable.</p>

            <v-divider class="my-3" />
            <div class="text-muted text-fine mb-2">Adresse de livraison</div>
            <OrderDeliveryDetails
              :zone="order.delivery_zone"
              :address="order.delivery_address"
              :instructions="order.delivery_instructions"
              :delivery-type="order.delivery_type"
              :recipient-name="order.recipient_name"
              :recipient-phone="order.recipient_phone"
              :pickup-point-contacts="order.pickup_point_contacts"
              :show-party="order.delivery_type === 'home_delivery'"
            />
            <a
              v-if="order.delivery_type === 'home_delivery' && mapsUrl(order.delivery_latitude, order.delivery_longitude)"
              :href="mapsUrl(order.delivery_latitude, order.delivery_longitude)!"
              target="_blank"
              rel="noopener"
              class="ext-link mt-2"
            >
              Position GPS du destinataire <PhArrowSquareOut :size="13" />
            </a>
          </div>
        </section>

        <!-- Point de retrait -->
        <section class="panel-card">
          <div class="panel-card__header">
            <span class="panel-card__title d-flex align-center ga-2"><PhMapPin :size="16" /> Point de retrait</span>
            <v-chip v-if="order.pickup_point" :color="order.pickup_point.is_active ? 'success' : 'error'" size="x-small" variant="tonal">
              {{ order.pickup_point.is_active ? 'Actif' : 'Inactif' }}
            </v-chip>
          </div>
          <div class="panel-card__body">
            <template v-if="order.pickup_point">
              <div class="entity__name">{{ order.pickup_point.name }}</div>
              <dl class="facts mt-2">
                <div><dt>Zone</dt><dd>{{ order.pickup_point.zone }}</dd></div>
                <div>
                  <dt>Position</dt>
                  <dd>
                    <a v-if="mapsUrl(order.pickup_point.latitude, order.pickup_point.longitude)" :href="mapsUrl(order.pickup_point.latitude, order.pickup_point.longitude)!" target="_blank" rel="noopener" class="ext-link">
                      Voir sur la carte <PhArrowSquareOut :size="13" />
                    </a>
                    <span v-else class="text-muted">Non renseignée</span>
                  </dd>
                </div>
                <div v-if="order.pickup_point.vendor_shop_name"><dt>Boutique liée</dt><dd>{{ order.pickup_point.vendor_shop_name }}</dd></div>
                <div>
                  <dt>Avis</dt>
                  <dd>
                    <template v-if="order.pickup_point.review_count > 0">
                      {{ order.pickup_point.average_rating?.toFixed(1) }} / 5 ({{ order.pickup_point.review_count }} avis)
                    </template>
                    <span v-else class="text-muted">Aucun</span>
                  </dd>
                </div>
                <div>
                  <dt>Gestionnaires</dt>
                  <dd>
                    <template v-if="order.pickup_point_contacts.length">
                      <div v-for="c in order.pickup_point_contacts" :key="c.phone">
                        {{ c.name ?? 'Nom non renseigné' }} · <a :href="`tel:${c.phone}`">{{ c.phone }}</a>
                      </div>
                    </template>
                    <span v-else class="text-muted">Aucun gestionnaire assigné</span>
                  </dd>
                </div>
                <div v-for="so in order.sub_orders.filter((s) => s.storage_location)" :key="so.id">
                  <dt>Emplacement · {{ so.shop_name }}</dt><dd>{{ so.storage_location }}</dd>
                </div>
              </dl>
              <NuxtLink to="/admin/points-retrait" class="ext-link mt-3">Voir les points de retrait</NuxtLink>
            </template>
            <p v-else class="text-muted text-meta mb-0">
              {{ order.delivery_type === 'pickup_point' ? 'Point de retrait introuvable (supprimé ?).' : 'Livraison à domicile — pas de point de retrait.' }}
            </p>
          </div>
        </section>
      </div>

      <v-dialog :model-value="zoomed !== null" max-width="720" @update:model-value="(v) => { if (!v) zoomed = null }">
        <v-card v-if="zoomed" class="zoom-card">
          <img :src="resolveImageUrl(zoomed.product_image!, apiBase)" :alt="zoomed.product_name" class="zoom-card__img" />
          <div class="pa-4 d-flex align-center ga-3">
            <div style="flex: 1; min-width: 0">
              <div style="font-weight: 700">{{ zoomed.product_name }}</div>
              <div v-if="zoomed.variant_label" class="text-muted text-meta">{{ zoomed.variant_label }}</div>
            </div>
            <v-btn variant="text" @click="zoomed = null">Fermer</v-btn>
          </div>
        </v-card>
      </v-dialog>
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
  gap: 8px;
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

/* --- Articles ------------------------------------------------------------ */

.items {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 340px), 1fr));
  gap: 12px;
}

.item {
  display: flex;
  gap: 14px;
  padding: 10px;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-md);
}

.item__photo {
  position: relative;
  width: 150px;
  height: 150px;
  flex: none;
  border-radius: var(--radius-sm);
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border: 1px solid var(--color-divider);
  padding: 0;
}

.item__photo--zoomable {
  cursor: zoom-in;
}

.item__photo img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.item__zoom {
  position: absolute;
  right: 6px;
  bottom: 6px;
  display: flex;
  padding: 5px;
  border-radius: 50%;
  background: rgb(0 0 0 / 55%);
  color: #fff;
}

.item__info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.item__name {
  font-weight: 700;
  font-size: 14.5px;
  overflow-wrap: anywhere;
}

.item__total {
  font-weight: 700;
  margin-top: 4px;
}

@media (max-width: 480px) {
  .item__photo {
    width: 110px;
    height: 110px;
  }
}

/* --- Entités ------------------------------------------------------------- */

.entities {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 320px), 1fr));
  gap: 16px;
}

.entity {
  padding: 14px;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--color-neutral-800) 35%, transparent);
}

.entity__head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-neutral-400);
  margin-bottom: 10px;
}

.entity__name {
  font-family: var(--font-heading);
  font-weight: 700;
  font-size: 16px;
  overflow-wrap: anywhere;
}

.courier-id {
  display: flex;
  align-items: center;
  gap: 14px;
}

.online-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-neutral-500);
}

.online-dot--on {
  background: var(--color-success);
}

.facts {
  display: grid;
  gap: 6px;
  margin: 0;
  font-size: 13px;
}

.facts > div {
  display: grid;
  grid-template-columns: 130px 1fr;
  gap: 8px;
}

.facts dt {
  color: var(--color-neutral-400);
}

.facts dd {
  margin: 0;
  min-width: 0;
  overflow-wrap: anywhere;
}

.facts--inline {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 24px;
}

.facts--inline > div {
  display: block;
}

.facts--inline dt {
  font-size: 11.5px;
}

.facts--inline dd {
  font-weight: 600;
}

.ext-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12.5px;
  color: var(--color-primary-300);
  text-decoration: none;
}

.ext-link:hover {
  text-decoration: underline;
}

.zoom-card__img {
  display: block;
  width: 100%;
  max-height: 70vh;
  object-fit: contain;
  background: #fff;
}
</style>
