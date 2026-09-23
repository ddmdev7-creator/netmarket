<script setup lang="ts">
/**
 * Vue « Carte » de /admin/livreurs : les livreurs approuvés à leur dernière
 * position connue et les courses en cours (boutique de départ → destination).
 *
 * La position d'un livreur n'est PAS suivie en direct : elle est enregistrée
 * quand il se met en ligne (voir backend app/couriers/models.py), d'où la
 * mention dans sa fiche. Les tracés sont donc boutique → destination, jamais
 * livreur → quoi que ce soit, qui laisserait croire à un suivi réel.
 * Sélectionner un livreur met en surbrillance les courses qui lui sont
 * attribuées (ou proposées, dispatch en cours). Les repères d'une course en
 * route (statut « shipped ») — son livreur et sa destination — sont animés
 * (halo pulsant, voir utils/mapPins.ts), comme les cartes de /admin/livraisons.
 *
 * Charge ses propres données (tous les livreurs approuvés, indépendamment de
 * l'onglet de statut de la liste) et seulement quand la vue est ouverte.
 */
import { PhArrowsClockwise, PhWarningCircle } from '@phosphor-icons/vue'
import type { OverviewMapItem, OverviewMapLine } from '~/components/admin/OverviewMap.vue'
import { MAP_PIN_META } from '~/utils/mapPins'
import type { ActiveDeliveryRead, CourierDetailRead, OrderStatus } from '~/types/api'

const { apiFetch } = useApi()

const { data, pending, refresh } = useAsyncData(
  'admin-courier-deliveries-map',
  async () => {
    const [couriers, deliveries] = await Promise.all([
      apiFetch<CourierDetailRead[]>('/admin/couriers', { query: { status: 'approved' } }),
      apiFetch<ActiveDeliveryRead[]>('/admin/deliveries/active'),
    ])
    return { couriers, deliveries }
  },
  { default: () => ({ couriers: [], deliveries: [] }), getCachedData: () => undefined },
)

const showCouriers = ref(true)
const showDeliveries = ref(true)
const selectedId = ref<string | null>(null)

const vehicleLabels: Record<string, string> = { moto: 'Moto', taxi: 'Taxi', voiture: 'Voiture' }
const deliveryStatusLabels: Partial<Record<OrderStatus, string>> = {
  confirmed: 'Confirmée',
  preparing: 'En préparation',
  shipped: 'En route',
}

const courierById = computed(() => new Map(data.value.couriers.map((c) => [c.id, c])))
const courierName = (id: string | null) => {
  if (!id) return null
  const courier = courierById.value.get(id)
  return courier ? (courier.full_name ?? courier.phone) : 'Livreur'
}

function carrierLabel(delivery: ActiveDeliveryRead): string {
  if (delivery.courier_id) return courierName(delivery.courier_id)!
  if (delivery.dispatch_offered_courier_id) return `Proposée à ${courierName(delivery.dispatch_offered_courier_id)}`
  return 'Aucun livreur'
}

const isInTransit = (d: ActiveDeliveryRead) => d.status === 'shipped'
const hasOrigin = (d: ActiveDeliveryRead) => d.origin_latitude !== null && d.origin_longitude !== null
const hasDestination = (d: ActiveDeliveryRead) => d.destination_latitude !== null && d.destination_longitude !== null

/**
 * Une destination « point de retrait » est commune à plusieurs commandes :
 * un seul repère par point. Une destination « domicile » est propre à sa
 * commande (plusieurs colis d'une même commande = un seul repère).
 */
function destinationId(d: ActiveDeliveryRead): string {
  return d.delivery_type === 'pickup_point'
    ? `dest-pickup:${d.destination_latitude},${d.destination_longitude}`
    : `dest-home:${d.order_id}`
}

const built = computed(() => {
  const items: OverviewMapItem[] = []
  const lines: OverviewMapLine[] = []
  const deliveries = data.value.deliveries

  if (showCouriers.value) {
    for (const courier of data.value.couriers) {
      if (courier.latitude === null || courier.longitude === null) continue
      const assigned = deliveries.filter(
        (d) => d.courier_id === courier.id || d.dispatch_offered_courier_id === courier.id,
      )
      items.push({
        id: `courier:${courier.id}`,
        kind: 'courier',
        name: courier.full_name ?? courier.phone,
        subtitle: courier.zone,
        lat: courier.latitude,
        lng: courier.longitude,
        muted: !courier.is_online,
        live: deliveries.some((d) => d.courier_id === courier.id && isInTransit(d)),
        statusLabel: courier.is_online ? 'En ligne' : 'Hors ligne',
        statusTone: courier.is_online ? 'success' : 'neutral',
        details: [
          { label: 'Téléphone', value: courier.phone },
          { label: 'Engin', value: vehicleLabels[courier.vehicle_type] ?? courier.vehicle_type },
          { label: 'Courses en cours', value: assigned.length ? assigned.map((d) => d.shop_name).join(', ') : 'Aucune' },
          { label: 'Position', value: 'Dernière mise en ligne (pas de suivi en direct)' },
        ],
      })
    }
  }

  if (showDeliveries.value) {
    const shops = new Map<string, ActiveDeliveryRead[]>()
    const destinations = new Map<string, ActiveDeliveryRead[]>()
    for (const d of deliveries) {
      if (hasOrigin(d)) shops.set(d.vendor_id, [...(shops.get(d.vendor_id) ?? []), d])
      if (hasDestination(d)) destinations.set(destinationId(d), [...(destinations.get(destinationId(d)) ?? []), d])
    }

    for (const [vendorId, group] of shops) {
      const [first] = group
      items.push({
        id: `shop:${vendorId}`,
        kind: 'shop',
        name: first!.shop_name,
        subtitle: `${group.length} colis en cours`,
        lat: first!.origin_latitude!,
        lng: first!.origin_longitude!,
        details: group.map((d) => ({
          label: deliveryStatusLabels[d.status] ?? d.status,
          value: `${d.pickup_point_name ?? d.delivery_zone ?? d.delivery_address} — ${carrierLabel(d)}`,
        })),
      })
    }

    for (const [id, group] of destinations) {
      const [first] = group
      const isPickup = first!.delivery_type === 'pickup_point'
      const orderIds = [...new Set(group.map((d) => d.order_id))]
      items.push({
        id,
        kind: isPickup ? 'pickup' : 'home',
        live: group.some(isInTransit),
        name: isPickup ? (first!.pickup_point_name ?? 'Point de retrait') : (first!.delivery_zone || first!.delivery_address),
        subtitle: `Destination · ${group.length} colis`,
        lat: first!.destination_latitude!,
        lng: first!.destination_longitude!,
        details: group.map((d) => ({
          label: d.shop_name,
          value: `${deliveryStatusLabels[d.status] ?? d.status} — ${carrierLabel(d)}`,
        })),
        ...(orderIds.length === 1 ? { href: `/admin/commandes/${orderIds[0]}`, hrefLabel: 'Voir la commande' } : {}),
      })
    }

    for (const d of deliveries) {
      if (!hasOrigin(d) || !hasDestination(d)) continue
      lines.push({
        id: d.sub_order_id,
        from: [d.origin_longitude!, d.origin_latitude!],
        to: [d.destination_longitude!, d.destination_latitude!],
        itemIds: [
          `shop:${d.vendor_id}`,
          destinationId(d),
          ...(d.courier_id ? [`courier:${d.courier_id}`] : []),
          ...(d.dispatch_offered_courier_id ? [`courier:${d.dispatch_offered_courier_id}`] : []),
        ],
      })
    }
  }

  return { items, lines }
})

const stats = computed(() => {
  const couriers = data.value.couriers
  const deliveries = data.value.deliveries
  return {
    online: couriers.filter((c) => c.is_online).length,
    unplacedCouriers: couriers.filter((c) => c.latitude === null || c.longitude === null).length,
    deliveries: deliveries.length,
    inTransit: deliveries.filter(isInTransit).length,
    unplacedDeliveries: deliveries.filter((d) => !hasOrigin(d) || !hasDestination(d)).length,
  }
})

watch(built, ({ items }) => {
  if (selectedId.value && !items.some((item) => item.id === selectedId.value)) selectedId.value = null
})
</script>

<template>
  <div>
    <div class="cdm-bar">
      <button
        type="button"
        class="cdm-chip"
        :class="{ 'cdm-chip--off': !showCouriers }"
        :aria-pressed="showCouriers"
        @click="showCouriers = !showCouriers"
      >
        <span class="cdm-chip__dot" :style="{ background: MAP_PIN_META.courier.color }">
          <component :is="MAP_PIN_META.courier.icon" :size="10" weight="fill" color="#fff" />
        </span>
        Livreurs
        <span class="cdm-chip__count">{{ stats.online }} en ligne / {{ data.couriers.length }}</span>
      </button>
      <button
        type="button"
        class="cdm-chip"
        :class="{ 'cdm-chip--off': !showDeliveries }"
        :aria-pressed="showDeliveries"
        @click="showDeliveries = !showDeliveries"
      >
        <span class="cdm-chip__dot" :style="{ background: MAP_PIN_META.home.color }">
          <component :is="MAP_PIN_META.home.icon" :size="10" weight="fill" color="#fff" />
        </span>
        Courses en cours
        <span class="cdm-chip__count">{{ stats.deliveries }}</span>
      </button>
      <span v-if="stats.inTransit" class="cdm-live-hint">
        <span class="cdm-live-hint__dot" aria-hidden="true" />
        {{ stats.inTransit }} en route · repères animés
      </span>
      <v-btn variant="text" size="small" :loading="pending" class="ms-auto" @click="refresh()">
        <PhArrowsClockwise :size="15" class="mr-1" />
        Actualiser
      </v-btn>
    </div>

    <p v-if="stats.unplacedCouriers || stats.unplacedDeliveries" class="admin-map-note">
      <PhWarningCircle :size="15" weight="fill" color="#e0822e" />
      <span>
        Absents de la carte faute de position GPS :
        <template v-if="stats.unplacedCouriers">
          {{ stats.unplacedCouriers }} livreur{{ stats.unplacedCouriers > 1 ? 's' : '' }} (jamais mis en ligne)
        </template>
        <template v-if="stats.unplacedCouriers && stats.unplacedDeliveries"> · </template>
        <template v-if="stats.unplacedDeliveries">
          {{ stats.unplacedDeliveries }} tracé{{ stats.unplacedDeliveries > 1 ? 's' : '' }} de course incomplet{{ stats.unplacedDeliveries > 1 ? 's' : '' }}
        </template>
      </span>
    </p>

    <div class="admin-map-frame">
      <AdminOverviewMap
        :items="built.items"
        :lines="built.lines"
        :selected-id="selectedId"
        :legend-kinds="['courier', 'shop', 'home', 'pickup']"
        aria-label="Carte des livreurs et des courses en cours"
        empty-text="Aucun livreur ni course en cours à afficher."
        @select="selectedId = $event"
      />
    </div>
  </div>
</template>

<style scoped>
.cdm-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.cdm-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 6px 11px;
  border: 1px solid var(--color-divider-strong);
  border-radius: 999px;
  background: var(--color-neutral-900);
  color: var(--color-neutral-200);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.12s ease;
}

.cdm-chip--off {
  opacity: 0.5;
  background: transparent;
}

.cdm-chip__dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
}

.cdm-live-hint {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-neutral-400);
}

.cdm-live-hint__dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #ea580c;
  animation: cdm-live 2.2s ease-out infinite;
}

@keyframes cdm-live {
  0% { box-shadow: 0 0 0 0 rgba(234, 88, 12, 0.55); }
  100% { box-shadow: 0 0 0 8px rgba(234, 88, 12, 0); }
}

@media (prefers-reduced-motion: reduce) {
  .cdm-live-hint__dot { animation: none; }
}

.cdm-chip__count {
  font-size: 11.5px;
  font-weight: 500;
  color: var(--color-neutral-400);
}
</style>
