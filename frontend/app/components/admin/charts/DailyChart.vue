<script setup lang="ts">
/**
 * Série journalière (tableau de bord admin) : barres pour un comptage,
 * courbe pour un montant. Une seule série, une seule échelle — deux mesures
 * d'unités différentes vont dans deux graphiques distincts, jamais sur un
 * double axe. Survol : colonne mise en évidence + infobulle.
 */
const props = withDefaults(
  defineProps<{
    points: { date: string; value: number }[]
    kind?: 'bar' | 'line'
    label: string
    format?: (value: number) => string
  }>(),
  { kind: 'bar', format: (value: number) => value.toLocaleString('fr-FR') },
)

const W = 600
const H = 170
const PAD_L = 8
const PAD_R = 8
const PAD_TOP = 14
const PAD_BOTTOM = 22
const innerW = W - PAD_L - PAD_R
const innerH = H - PAD_TOP - PAD_BOTTOM
const baseline = PAD_TOP + innerH

// Maximum arrondi à une valeur « ronde » pour les repères horizontaux.
const niceMax = computed(() => {
  const max = Math.max(...props.points.map((p) => p.value), 0)
  if (max === 0) return 1
  const magnitude = 10 ** Math.floor(Math.log10(max))
  const step = [1, 2, 2.5, 5, 10].find((s) => s * magnitude >= max) ?? 10
  return step * magnitude
})

const slot = computed(() => innerW / Math.max(props.points.length, 1))
const columns = computed(() =>
  props.points.map((p, i) => {
    const x = PAD_L + i * slot.value
    const h = (p.value / niceMax.value) * innerH
    return { ...p, i, x, cx: x + slot.value / 2, y: baseline - h, h }
  }),
)

// Barre : largeur de colonne moins un écart de 2 px, bout supérieur arrondi (4 px).
function barPath(c: { x: number; h: number }) {
  const gap = 2
  const w = Math.max(slot.value - gap, 1)
  const x = c.x + gap / 2
  if (c.h <= 0) return ''
  const r = Math.min(4, w / 2, c.h)
  const top = baseline - c.h
  return `M ${x} ${baseline} V ${top + r} Q ${x} ${top} ${x + r} ${top} H ${x + w - r} Q ${x + w} ${top} ${x + w} ${top + r} V ${baseline} Z`
}

const linePath = computed(() => columns.value.map((c, i) => `${i ? 'L' : 'M'} ${c.cx} ${c.y}`).join(' '))
const areaPath = computed(() => {
  const first = columns.value[0]
  const last = columns.value[columns.value.length - 1]
  if (!first || !last) return ''
  return `${linePath.value} L ${last.cx} ${baseline} L ${first.cx} ${baseline} Z`
})

const gridLines = computed(() => [0.5, 1].map((f) => ({ y: baseline - f * innerH, value: niceMax.value * f })))

// Repères de dates clairsemés : une étiquette par jour se chevaucherait.
const xLabels = computed(() => {
  const n = columns.value.length
  if (!n) return []
  const idxs = [0, Math.round((n - 1) / 3), Math.round((2 * (n - 1)) / 3), n - 1]
  return [...new Set(idxs)].flatMap((i) => columns.value[i] ?? [])
})

function formatDay(iso: string) {
  const [y = 1970, m = 1, d = 1] = iso.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })
}

const hovered = ref<number | null>(null)
const active = computed(() => (hovered.value === null ? null : (columns.value[hovered.value] ?? null)))
const tooltipStyle = computed(() => {
  if (!active.value) return {}
  const pct = (active.value.cx / W) * 100
  return { left: `${Math.min(Math.max(pct, 12), 88)}%` }
})
</script>

<template>
  <div class="daily" role="img" :aria-label="label">
    <svg :viewBox="`0 0 ${W} ${H}`" preserveAspectRatio="none" class="daily__svg" @pointerleave="hovered = null">
      <g class="daily__grid">
        <line v-for="g in gridLines" :key="g.y" :x1="PAD_L" :x2="W - PAD_R" :y1="g.y" :y2="g.y" />
        <line class="daily__baseline" :x1="PAD_L" :x2="W - PAD_R" :y1="baseline" :y2="baseline" />
      </g>

      <template v-if="kind === 'bar'">
        <path
          v-for="c in columns"
          :key="c.date"
          :d="barPath(c)"
          class="daily__bar"
          :class="{ 'daily__bar--dim': hovered !== null && hovered !== c.i }"
        />
      </template>
      <template v-else>
        <path :d="areaPath" class="daily__area" />
        <path :d="linePath" class="daily__line" fill="none" />
        <line v-if="active" class="daily__cursor" :x1="active.cx" :x2="active.cx" :y1="PAD_TOP" :y2="baseline" />
        <circle v-if="active" :cx="active.cx" :cy="active.y" r="5" class="daily__marker" />
      </template>

      <!-- Zones de survol : toute la colonne, plus large que la marque. -->
      <rect
        v-for="c in columns"
        :key="`hit-${c.date}`"
        :x="c.x"
        :y="0"
        :width="slot"
        :height="H"
        fill="transparent"
        @pointerenter="hovered = c.i"
      />
    </svg>

    <div class="daily__ylabels" aria-hidden="true">
      <span v-for="g in gridLines" :key="g.y" :style="{ top: `${(g.y / H) * 100}%` }">{{ format(g.value) }}</span>
    </div>
    <div class="daily__xlabels" aria-hidden="true">
      <span v-for="c in xLabels" :key="c.date" :style="{ left: `${(c.cx / W) * 100}%` }">{{ formatDay(c.date) }}</span>
    </div>

    <div v-if="active" class="daily__tooltip" :style="tooltipStyle">
      <div class="daily__tooltip-date">{{ formatDay(active.date) }}</div>
      <div class="daily__tooltip-value">{{ format(active.value) }}</div>
    </div>
  </div>
</template>

<style scoped>
.daily {
  --chart-series: #2a78d6;
  --chart-grid: #e7e6e1;
  --chart-axis: #c3c2b7;
  position: relative;
  padding-bottom: 18px;
}

:root[data-theme='dark'] .daily {
  --chart-series: #3987e5;
  --chart-grid: #2a2a28;
  --chart-axis: #383835;
}

.daily__svg {
  display: block;
  width: 100%;
  height: 170px;
  overflow: visible;
}

.daily__grid line {
  stroke: var(--chart-grid);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.daily__grid .daily__baseline {
  stroke: var(--chart-axis);
}

.daily__bar {
  fill: var(--chart-series);
  transition: opacity 0.15s;
}

.daily__bar--dim {
  opacity: 0.45;
}

.daily__area {
  fill: var(--chart-series);
  opacity: 0.12;
}

.daily__line {
  stroke: var(--chart-series);
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
  stroke-linejoin: round;
}

.daily__cursor {
  stroke: var(--chart-axis);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.daily__marker {
  fill: var(--chart-series);
  stroke: var(--color-neutral-900);
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
}

.daily__ylabels span {
  position: absolute;
  left: 4px;
  transform: translateY(-115%);
  font-size: 10.5px;
  color: var(--color-neutral-500);
  font-variant-numeric: tabular-nums;
  pointer-events: none;
}

.daily__xlabels span {
  position: absolute;
  bottom: 0;
  transform: translateX(-50%);
  font-size: 10.5px;
  color: var(--color-neutral-500);
  white-space: nowrap;
}

.daily__tooltip {
  position: absolute;
  top: 0;
  transform: translateX(-50%);
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider);
  box-shadow: var(--shadow-md);
  pointer-events: none;
  white-space: nowrap;
  z-index: 2;
}

.daily__tooltip-date {
  font-size: 11px;
  color: var(--color-neutral-400);
}

.daily__tooltip-value {
  font-size: 13.5px;
  font-weight: 800;
  color: var(--color-neutral-200);
  font-variant-numeric: tabular-nums;
}
</style>
