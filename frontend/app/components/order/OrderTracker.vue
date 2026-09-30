<script setup lang="ts">
import {
  PhArrowUUpLeft,
  PhCheck,
  PhCheckCircle,
  PhHandshake,
  PhPackage,
  PhReceipt,
  PhStorefront,
  PhTruck,
  PhXCircle,
} from '@phosphor-icons/vue'
import type { Component } from 'vue'
import type { DeliveryType, OrderStatus } from '~/types/api'

/**
 * Suivi d'un colis en frise illustrée (remplace l'ancienne liste de points) :
 * une carte "où en est mon colis" avec l'étape en cours mise en avant, une
 * barre d'étapes à icônes, puis le détail horodaté de chaque passage.
 */
const props = defineProps<{
  status: OrderStatus
  deliveryType: DeliveryType
  events: { status: OrderStatus; created_at: string }[]
  estimatedMin: string | null
  estimatedMax: string | null
}>()

interface Step {
  key: OrderStatus
  label: string
  icon: Component
}

// L'étape "Au point de retrait" n'existe que pour un retrait en point, comme
// côté backend (app/orders/service.py::_allowed_next_statuses).
const steps = computed<Step[]>(() => {
  const list: Step[] = [
    { key: 'pending', label: 'Reçue', icon: PhReceipt },
    { key: 'confirmed', label: 'Confirmée', icon: PhCheckCircle },
    { key: 'preparing', label: 'Préparée', icon: PhPackage },
    { key: 'shipped', label: 'En route', icon: PhTruck },
  ]
  if (props.deliveryType === 'pickup_point') list.push({ key: 'arrived_at_pickup_point', label: 'Au point', icon: PhStorefront })
  // Colis non retiré : la dernière étape devient le retour à la boutique.
  if (isReturn.value) list.push({ key: props.status, label: 'Retour boutique', icon: PhArrowUUpLeft })
  else list.push({ key: 'delivered', label: 'Livrée', icon: PhHandshake })
  return list
})

const isReturn = computed(() => ['return_pending', 'returning', 'returned'].includes(props.status))
const currentIndex = computed(() => steps.value.findIndex((s) => s.key === props.status))
const isCancelled = computed(() => props.status === 'cancelled' || props.status === 'returned')
const isDone = computed(() => props.status === 'delivered')

// Heure du DERNIER passage par chaque statut.
const reachedAt = computed(() => {
  const map = new Map<OrderStatus, string>()
  for (const e of props.events) map.set(e.status, e.created_at)
  return map
})

function formatWhen(iso: string | undefined): string | null {
  if (!iso) return null
  const d = new Date(iso)
  const today = new Date()
  const yesterday = new Date(today)
  yesterday.setDate(today.getDate() - 1)
  const time = d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
  if (d.toDateString() === today.toDateString()) return `Aujourd'hui, ${time}`
  if (d.toDateString() === yesterday.toDateString()) return `Hier, ${time}`
  return `${d.toLocaleDateString('fr-FR', { weekday: 'short', day: 'numeric', month: 'short' })}, ${time}`
}

const eta = computed(() =>
  props.estimatedMin && props.estimatedMax ? formatDeliveryEstimate(props.estimatedMin, props.estimatedMax) : null,
)

const headline = computed<{ title: string; text: string; icon: Component; hue: number }>(() => {
  const pickup = props.deliveryType === 'pickup_point'
  switch (props.status) {
    case 'pending':
      return { title: 'Commande envoyée à la boutique', text: 'Le vendeur va la confirmer très vite.', icon: PhReceipt, hue: 220 }
    case 'confirmed':
      return { title: 'Commande confirmée', text: 'Le vendeur va préparer votre colis.', icon: PhCheckCircle, hue: 220 }
    case 'preparing':
      return { title: 'Colis en préparation', text: 'Votre colis est en cours d’emballage.', icon: PhPackage, hue: 35 }
    case 'shipped':
      return {
        title: 'Votre colis est en route',
        text: pickup ? 'Il arrive bientôt à votre point de retrait.' : 'Un livreur vous l’apporte.',
        icon: PhTruck,
        hue: 200,
      }
    case 'arrived_at_pickup_point':
      return {
        title: 'Disponible au point de retrait',
        text: 'Venez le chercher avec votre QR code.',
        icon: PhStorefront,
        hue: 270,
      }
    case 'delivered':
      return {
        title: 'Colis livré',
        text: `Remis ${formatWhen(reachedAt.value.get('delivered'))?.toLowerCase() ?? ''}`.trim(),
        icon: PhHandshake,
        hue: 150,
      }
    case 'return_pending':
      return {
        title: 'Non retiré à temps',
        text: 'Il va retourner à la boutique. Vous pouvez encore le retirer au point avec votre QR code tant que le livreur n’est pas passé.',
        icon: PhArrowUUpLeft,
        hue: 30,
      }
    case 'returning':
      return {
        title: 'Retour à la boutique en cours',
        text: 'Vous serez remboursé à sa réception : les articles, moins la livraison aller et le retour.',
        icon: PhArrowUUpLeft,
        hue: 30,
      }
    case 'returned':
      return {
        title: 'Colis rendu à la boutique',
        text: 'Le remboursement (articles, moins la livraison aller et le retour) a été crédité sur NdjouriBank.',
        icon: PhArrowUUpLeft,
        hue: 30,
      }
    default:
      return { title: 'Commande annulée', text: 'Ce colis ne sera pas livré.', icon: PhXCircle, hue: 0 }
  }
})

// Remplissage de la barre : jusqu'au centre de l'étape en cours.
const progress = computed(() => {
  const n = steps.value.length
  if (currentIndex.value <= 0) return 0
  return (currentIndex.value / (n - 1)) * 100
})

const detailOpen = ref(false)
</script>

<template>
  <div class="tracker" :class="{ 'tracker--cancelled': isCancelled, 'tracker--done': isDone }">
    <div class="tracker__hero" :style="{ '--hue': headline.hue }">
      <span class="tracker__hero-icon" :class="{ 'tracker__hero-icon--live': !isCancelled && !isDone }">
        <component :is="headline.icon" :size="26" weight="duotone" />
      </span>
      <span class="tracker__hero-text">
        <strong>{{ headline.title }}</strong>
        <span>{{ headline.text }}</span>
        <span v-if="eta && !isDone && !isCancelled" class="tracker__eta">Livraison prévue : {{ eta }}</span>
      </span>
    </div>

    <div v-if="!isCancelled" class="tracker__rail" :style="{ '--steps': steps.length }">
      <div class="tracker__track">
        <div class="tracker__fill" :style="{ width: `${progress}%` }" />
      </div>
      <div
        v-for="(step, i) in steps"
        :key="step.key"
        class="tracker__step"
        :class="{ 'is-done': i < currentIndex || isDone, 'is-current': i === currentIndex && !isDone }"
      >
        <span class="tracker__node">
          <PhCheck v-if="i < currentIndex || isDone" :size="14" weight="bold" />
          <component :is="step.icon" v-else :size="16" :weight="i === currentIndex ? 'fill' : 'regular'" />
        </span>
        <span class="tracker__label">{{ step.label }}</span>
      </div>
    </div>

    <button v-if="events.length" type="button" class="tracker__toggle" @click="detailOpen = !detailOpen">
      {{ detailOpen ? 'Masquer le détail' : 'Voir le détail du suivi' }}
    </button>
    <ol v-if="detailOpen" class="tracker__log">
      <li v-for="step in steps.slice(0, Math.max(currentIndex, 0) + 1).reverse()" :key="step.key">
        <span class="tracker__log-dot" />
        <span class="tracker__log-label">{{ step.label }}</span>
        <span class="tracker__log-when">{{ formatWhen(reachedAt.get(step.key)) ?? '' }}</span>
      </li>
      <li v-if="isCancelled">
        <span class="tracker__log-dot tracker__log-dot--cancel" />
        <span class="tracker__log-label">Annulée</span>
        <span class="tracker__log-when">{{ formatWhen(reachedAt.get('cancelled')) ?? '' }}</span>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.tracker__hero {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px;
  border-radius: var(--radius-md);
  background: hsl(var(--hue) 70% var(--tint-bg-soft));
  border: 1px solid hsl(var(--hue) 60% 50% / 0.18);
}

.tracker__hero-icon {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  flex-shrink: 0;
  border-radius: 50%;
  background: hsl(var(--hue) 70% var(--tint-bg));
  color: hsl(var(--hue) 60% var(--tint-fg));
}

/* Halo qui "respire" : l'étape est en cours, quelque chose se passe. */
.tracker__hero-icon--live::after {
  content: '';
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  border: 2px solid hsl(var(--hue) 60% 50% / 0.5);
  animation: breathe 1.8s ease-in-out infinite;
}

@keyframes breathe {
  0%,
  100% {
    transform: scale(0.92);
    opacity: 0.9;
  }
  50% {
    transform: scale(1.1);
    opacity: 0;
  }
}

.tracker__hero-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  font-size: 13px;
  color: var(--color-neutral-400);
}

.tracker__hero-text strong {
  font-family: var(--font-heading);
  font-size: 16px;
  font-weight: 800;
  color: var(--color-neutral-200);
}

.tracker__eta {
  margin-top: 2px;
  font-weight: 700;
  color: var(--color-success);
}

.tracker__rail {
  position: relative;
  display: grid;
  grid-template-columns: repeat(var(--steps), 1fr);
  margin: 18px 0 4px;
}

/* La barre relie le centre de la première pastille au centre de la dernière. */
.tracker__track {
  position: absolute;
  top: 15px;
  left: calc(100% / var(--steps) / 2);
  right: calc(100% / var(--steps) / 2);
  height: 4px;
  border-radius: 4px;
  background: var(--color-neutral-700);
  overflow: hidden;
}

.tracker__fill {
  height: 100%;
  border-radius: 4px;
  background: linear-gradient(90deg, var(--color-success), var(--color-primary));
  transition: width 0.6s ease;
}

.tracker__step {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.tracker__node {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  border: 2px solid var(--color-neutral-600);
  background: var(--color-neutral-900);
  color: var(--color-neutral-500);
  transition: all 0.3s ease;
}

.tracker__step.is-done .tracker__node {
  border-color: var(--color-success);
  background: var(--color-success);
  color: #fff;
}

.tracker__step.is-current .tracker__node {
  border-color: var(--color-primary);
  background: var(--color-primary);
  color: #fff;
  box-shadow: 0 0 0 5px var(--color-primary-100);
}

.tracker__label {
  font-size: 11px;
  font-weight: 600;
  text-align: center;
  color: var(--color-neutral-500);
  line-height: 1.2;
}

.tracker__step.is-done .tracker__label {
  color: var(--color-neutral-300);
}

.tracker__step.is-current .tracker__label {
  color: var(--color-primary-300);
  font-weight: 800;
}

.tracker--done .tracker__fill {
  background: var(--color-success);
}

.tracker__toggle {
  margin-top: 8px;
  padding: 4px 0;
  border: 0;
  background: none;
  color: var(--color-primary-300);
  font-size: 12.5px;
  font-weight: 700;
  cursor: pointer;
}

.tracker__log {
  list-style: none;
  margin: 6px 0 0;
  padding: 0;
}

.tracker__log li {
  position: relative;
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 0 0 12px 18px;
  font-size: 13px;
}

.tracker__log li::before {
  content: '';
  position: absolute;
  left: 4px;
  top: 12px;
  bottom: -2px;
  width: 2px;
  background: var(--color-neutral-700);
}

.tracker__log li:last-child::before {
  display: none;
}

.tracker__log-dot {
  position: absolute;
  left: 0;
  top: 4px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--color-success);
}

.tracker__log li:first-child .tracker__log-dot {
  background: var(--color-primary);
}

.tracker__log-dot--cancel {
  background: var(--color-error) !important;
}

.tracker__log-label {
  flex: 1;
  font-weight: 600;
}

.tracker__log-when {
  color: var(--color-neutral-400);
  font-size: 12px;
}

@media (prefers-reduced-motion: reduce) {
  .tracker__hero-icon--live::after {
    animation: none;
  }
}
</style>
