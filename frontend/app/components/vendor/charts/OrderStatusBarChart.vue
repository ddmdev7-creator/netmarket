<script setup lang="ts">
const props = defineProps<{ active: number; delivered: number; cancelled: number }>()

// Validated categorical slots 1/2/3 (dark-mode steps) — passes CVD + normal-vision
// checks all-pairs against this app's card surface (#1a1a1d); see
// dataviz skill scripts/validate_palette.js. Not the StatusBadge colors: those are
// single semantic chips shown one at a time, never validated as an adjacent set.
const rows = computed(() => [
  { key: 'active', label: 'Actives', value: props.active, color: '#3987e5' },
  { key: 'delivered', label: 'Livrées', value: props.delivered, color: '#199e70' },
  { key: 'cancelled', label: 'Annulées', value: props.cancelled, color: '#d95926' },
])

const max = computed(() => Math.max(props.active, props.delivered, props.cancelled, 1))
function pct(value: number) {
  return (value / max.value) * 100
}
</script>

<template>
  <div class="bar-chart" role="img" aria-label="Répartition des commandes par statut">
    <div v-for="row in rows" :key="row.key" class="bar-row" tabindex="0" :aria-label="`${row.label} : ${row.value}`">
      <span class="bar-row__label">{{ row.label }}</span>
      <div class="bar-row__track">
        <div class="bar-row__fill" :style="{ width: pct(row.value) + '%', background: row.color }" />
      </div>
      <span class="bar-row__value">{{ row.value }}</span>
    </div>
  </div>
</template>

<style scoped>
.bar-chart {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.bar-row {
  display: grid;
  grid-template-columns: 60px 1fr 28px;
  align-items: center;
  gap: 10px;
  border-radius: var(--radius-sm);
}

.bar-row:focus-visible {
  outline: 1px solid var(--color-primary);
  outline-offset: 2px;
}

.bar-row__label {
  font-size: 12px;
  color: var(--color-neutral-400);
}

.bar-row__track {
  height: 14px;
  background: var(--color-neutral-800);
  border-radius: 4px;
  overflow: hidden;
}

.bar-row__fill {
  height: 100%;
  min-width: 3px;
  border-radius: 0 4px 4px 0;
  transition: filter 0.15s ease;
}

.bar-row:hover .bar-row__fill,
.bar-row:focus-visible .bar-row__fill {
  filter: brightness(1.2);
}

.bar-row__value {
  font-size: 12.5px;
  font-weight: 600;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
</style>
