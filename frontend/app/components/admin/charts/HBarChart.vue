<script setup lang="ts">
/**
 * Barres horizontales (répartitions et classements du tableau de bord admin).
 * Libellé et valeur toujours affichés en clair (jamais la couleur seule) ;
 * `showShare` ajoute la part du total pour une répartition.
 */
const props = withDefaults(
  defineProps<{
    rows: { key: string; label: string; value: number; color?: string }[]
    format?: (value: number) => string
    showShare?: boolean
    label: string
  }>(),
  { format: (value: number) => value.toLocaleString('fr-FR'), showShare: false },
)

const max = computed(() => Math.max(...props.rows.map((r) => r.value), 1))
const total = computed(() => props.rows.reduce((sum, r) => sum + r.value, 0))
const hovered = ref<string | null>(null)

function share(value: number) {
  return total.value ? Math.round((value / total.value) * 100) : 0
}
</script>

<template>
  <ul class="hbar" role="list" :aria-label="label">
    <li
      v-for="row in rows"
      :key="row.key"
      class="hbar__row"
      :class="{ 'hbar__row--dim': hovered !== null && hovered !== row.key }"
      :title="`${row.label} : ${format(row.value)}${showShare ? ` (${share(row.value)} %)` : ''}`"
      @pointerenter="hovered = row.key"
      @pointerleave="hovered = null"
    >
      <div class="hbar__head">
        <span class="hbar__label">{{ row.label }}</span>
        <span class="hbar__value">
          {{ format(row.value) }}<span v-if="showShare" class="hbar__share"> · {{ share(row.value) }} %</span>
        </span>
      </div>
      <div class="hbar__track">
        <div
          class="hbar__fill"
          :style="{ width: `${(row.value / max) * 100}%`, background: row.color ?? 'var(--hbar-series)' }"
        />
      </div>
    </li>
  </ul>
</template>

<style scoped>
.hbar {
  --hbar-series: #2a78d6;
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 10px;
}

:root[data-theme='dark'] .hbar {
  --hbar-series: #3987e5;
}

.hbar__row {
  transition: opacity 0.15s;
}

.hbar__row--dim {
  opacity: 0.5;
}

.hbar__head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
  font-size: 12.5px;
}

.hbar__label {
  color: var(--color-neutral-300);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hbar__value {
  flex: none;
  font-weight: 700;
  color: var(--color-neutral-200);
  font-variant-numeric: tabular-nums;
}

.hbar__share {
  font-weight: 500;
  color: var(--color-neutral-400);
}

.hbar__track {
  height: 8px;
  border-radius: 4px;
  background: var(--color-neutral-800);
  overflow: hidden;
}

.hbar__fill {
  height: 100%;
  border-radius: 4px;
}
</style>
