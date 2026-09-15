<script setup lang="ts">
import type { DeliveryType, OrderStatus } from '~/types/api'

const props = defineProps<{ status: OrderStatus; deliveryType: DeliveryType }>()

// L'étape "Arrivée au point de retrait" n'existe que pour un retrait en
// point — une livraison à domicile garde exactement les 5 étapes
// historiques (voir app/orders/service.py::_allowed_next_statuses côté
// backend, qui applique la même distinction).
const steps = computed<{ key: OrderStatus; label: string }[]>(() => {
  const base: { key: OrderStatus; label: string }[] = [
    { key: 'pending', label: 'Commande reçue' },
    { key: 'confirmed', label: 'Confirmée' },
    { key: 'preparing', label: 'En préparation' },
    { key: 'shipped', label: 'Expédiée' },
  ]
  if (props.deliveryType === 'pickup_point') {
    base.push({ key: 'arrived_at_pickup_point', label: 'Arrivée au point de retrait' })
  }
  base.push({ key: 'delivered', label: 'Livrée' })
  return base
})

const rank = computed<Record<OrderStatus, number>>(() =>
  props.deliveryType === 'pickup_point'
    ? { pending: 0, confirmed: 1, preparing: 2, shipped: 3, arrived_at_pickup_point: 4, delivered: 5, cancelled: -1 }
    : { pending: 0, confirmed: 1, preparing: 2, shipped: 3, arrived_at_pickup_point: -1, delivered: 4, cancelled: -1 },
)

const currentRank = computed(() => rank.value[props.status])
</script>

<template>
  <v-chip v-if="status === 'cancelled'" color="error" size="small" variant="tonal">Annulée</v-chip>
  <div v-else class="timeline">
    <div
      v-for="(step, index) in steps"
      :key="step.key"
      class="timeline__step"
      :class="{ done: index < currentRank, current: index === currentRank }"
    >
      <div class="timeline__marker">
        <div class="timeline__dot" />
        <div v-if="index < steps.length - 1" class="timeline__line" />
      </div>
      <div class="timeline__label" :class="{ 'text-muted': index > currentRank }">{{ step.label }}</div>
    </div>
  </div>
</template>

<style scoped>
.timeline__step {
  display: flex;
  gap: 12px;
}
.timeline__marker {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 10px;
  flex: none;
}
.timeline__dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--color-neutral-700);
}
.timeline__line {
  width: 1px;
  flex: 1;
  background: var(--color-neutral-700);
  margin: 2px 0;
}
.timeline__step.done .timeline__dot,
.timeline__step.current .timeline__dot {
  background: var(--color-primary);
}
.timeline__step.done .timeline__line {
  background: var(--color-primary-700);
}
.timeline__label {
  font-size: 13px;
  padding-bottom: 16px;
}
.timeline__step.current .timeline__label {
  color: var(--color-primary);
}
</style>
