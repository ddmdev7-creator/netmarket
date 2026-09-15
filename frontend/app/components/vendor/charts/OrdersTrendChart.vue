<script setup lang="ts">
import type { DailyOrderCount } from '~/types/api'

const props = defineProps<{ points: DailyOrderCount[] }>()

const W = 320
const H = 100
const PAD_X = 4
const PAD_TOP = 10
const PAD_BOTTOM = 18

const maxCount = computed(() => Math.max(...props.points.map((p) => p.order_count), 1))

const coords = computed(() => {
  const n = props.points.length
  const innerW = W - PAD_X * 2
  const innerH = H - PAD_TOP - PAD_BOTTOM
  return props.points.map((p, i) => ({
    x: n > 1 ? PAD_X + (i / (n - 1)) * innerW : PAD_X + innerW / 2,
    y: PAD_TOP + innerH - (p.order_count / maxCount.value) * innerH,
    ...p,
  }))
})

const linePath = computed(() => coords.value.map((c, i) => `${i === 0 ? 'M' : 'L'} ${c.x} ${c.y}`).join(' '))
const areaPath = computed(() => {
  if (coords.value.length === 0) return ''
  const first = coords.value[0]
  const last = coords.value[coords.value.length - 1]
  const baseline = PAD_TOP + (H - PAD_TOP - PAD_BOTTOM)
  return `${linePath.value} L ${last.x} ${baseline} L ${first.x} ${baseline} Z`
})

// Sparse: first, middle, last — a label per day would collide on a 320px axis.
const xLabels = computed(() => {
  const n = coords.value.length
  if (n === 0) return []
  const idxs = n > 2 ? [0, Math.floor((n - 1) / 2), n - 1] : [0, n - 1]
  return [...new Set(idxs)].map((i) => coords.value[i])
})

function formatDay(iso: string) {
  return new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })
}

const hovered = ref<number | null>(null)
const svgEl = ref<SVGSVGElement | null>(null)

function onPointerMove(event: PointerEvent) {
  const svg = svgEl.value
  if (!svg || coords.value.length === 0) return
  const rect = svg.getBoundingClientRect()
  const x = ((event.clientX - rect.left) / rect.width) * W
  let nearest = 0
  let bestDist = Infinity
  coords.value.forEach((c, i) => {
    const d = Math.abs(c.x - x)
    if (d < bestDist) {
      bestDist = d
      nearest = i
    }
  })
  hovered.value = nearest
}
function onPointerLeave() {
  hovered.value = null
}

const active = computed(() => (hovered.value !== null ? coords.value[hovered.value] : null))
const tooltipStyle = computed(() => {
  if (!active.value) return {}
  const leftPct = (active.value.x / W) * 100
  return { left: `${leftPct}%` }
})
</script>

<template>
  <div class="trend" role="img" aria-label="Commandes reçues par jour, 14 derniers jours">
    <svg
      ref="svgEl"
      :viewBox="`0 0 ${W} ${H}`"
      preserveAspectRatio="none"
      class="trend__svg"
      @pointermove="onPointerMove"
      @pointerleave="onPointerLeave"
    >
      <line
        v-for="frac in [0, 0.5, 1]"
        :key="frac"
        :x1="PAD_X"
        :x2="W - PAD_X"
        :y1="PAD_TOP + (H - PAD_TOP - PAD_BOTTOM) * frac"
        :y2="PAD_TOP + (H - PAD_TOP - PAD_BOTTOM) * frac"
        class="trend__grid"
      />

      <path :d="areaPath" class="trend__area" />
      <path :d="linePath" class="trend__line" />

      <line
        v-if="active"
        :x1="active.x"
        :x2="active.x"
        :y1="PAD_TOP"
        :y2="H - PAD_BOTTOM"
        class="trend__crosshair"
      />
      <circle
        v-for="(c, i) in coords"
        :key="c.day"
        :cx="c.x"
        :cy="c.y"
        :r="i === coords.length - 1 || hovered === i ? 4 : 2.5"
        class="trend__dot"
        :class="{ 'trend__dot--active': hovered === i }"
      />

      <text
        v-for="lab in xLabels"
        :key="lab.day"
        :x="lab.x"
        :y="H - 4"
        class="trend__axis-label"
        :text-anchor="lab.x < 20 ? 'start' : lab.x > W - 20 ? 'end' : 'middle'"
      >
        {{ formatDay(lab.day) }}
      </text>
    </svg>

    <div v-if="active" class="trend__tooltip" :style="tooltipStyle">
      <div class="trend__tooltip-value">{{ active.order_count }} commande{{ active.order_count > 1 ? 's' : '' }}</div>
      <div class="trend__tooltip-date">{{ formatDay(active.day) }}</div>
    </div>

    <table class="visually-hidden">
      <caption>Commandes reçues par jour</caption>
      <tbody>
        <tr v-for="p in points" :key="p.day">
          <th scope="row">{{ formatDay(p.day) }}</th>
          <td>{{ p.order_count }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.trend {
  position: relative;
}

.trend__svg {
  width: 100%;
  height: 110px;
  display: block;
  touch-action: none;
}

.trend__grid {
  stroke: var(--color-divider);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.trend__area {
  fill: var(--color-primary);
  opacity: 0.1;
  stroke: none;
}

.trend__line {
  fill: none;
  stroke: var(--color-primary);
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
  stroke-linejoin: round;
  stroke-linecap: round;
}

.trend__crosshair {
  stroke: var(--color-neutral-500);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.trend__dot {
  fill: var(--color-primary);
  stroke: var(--color-neutral-900);
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
}

.trend__dot--active {
  /* primary-100 est un ton très clair pensé pour du texte sur un fond foncé
     (badges) — quasi invisible ici, posé directement sur la surface de la
     carte (blanche en thème clair). primary-darken-1 reste visible dans les
     deux thèmes. */
  fill: var(--color-primary-darken-1);
}

.trend__axis-label {
  fill: var(--color-neutral-500);
  font-size: 7.5px;
}

.trend__tooltip {
  position: absolute;
  top: 0;
  transform: translateX(-50%);
  background: var(--color-neutral-800);
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-sm);
  padding: 4px 8px;
  pointer-events: none;
  white-space: nowrap;
}

.trend__tooltip-value {
  font-size: 12px;
  font-weight: 600;
}

.trend__tooltip-date {
  font-size: 10.5px;
  color: var(--color-neutral-400);
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
</style>
