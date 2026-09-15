<script setup lang="ts">
const props = defineProps<{ net: number; commission: number }>()

const total = computed(() => props.net + props.commission)
const netPct = computed(() => (total.value > 0 ? (props.net / total.value) * 100 : 50))
const commissionPct = computed(() => (total.value > 0 ? (props.commission / total.value) * 100 : 50))
</script>

<template>
  <div class="composition">
    <div class="composition__legend">
      <span class="legend-item">
        <span class="legend-item__dot" style="background: var(--color-primary)" />
        Revenu net · {{ formatGnf(net) }}
      </span>
      <span class="legend-item">
        <span class="legend-item__dot" style="background: var(--color-neutral-500)" />
        Commission · {{ formatGnf(commission) }}
      </span>
    </div>

    <div v-if="total > 0" class="composition__bar" role="img" :aria-label="`Revenu net ${formatGnf(net)}, commission ${formatGnf(commission)}`">
      <div class="composition__segment" :style="{ width: netPct + '%', background: 'var(--color-primary)' }" />
      <div class="composition__segment" :style="{ width: commissionPct + '%', background: 'var(--color-neutral-500)' }" />
    </div>
    <div v-else class="composition__bar composition__bar--empty" />
  </div>
</template>

<style scoped>
.composition__legend {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-bottom: 10px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-neutral-400);
}

.legend-item__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: none;
}

.composition__bar {
  display: flex;
  gap: 2px;
  height: 18px;
  border-radius: 4px;
  overflow: hidden;
}

.composition__bar--empty {
  background: var(--color-neutral-800);
}

.composition__segment {
  height: 100%;
  min-width: 2px;
}
</style>
