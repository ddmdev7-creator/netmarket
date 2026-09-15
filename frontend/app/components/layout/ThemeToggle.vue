<script setup lang="ts">
import { PhMoon, PhSun } from '@phosphor-icons/vue'

const { theme, toggle } = useAppTheme()
</script>

<template>
  <button
    type="button"
    class="theme-toggle"
    :aria-label="theme === 'dark' ? 'Passer au mode clair' : 'Passer au mode sombre'"
    @click="toggle"
  >
    <PhSun v-if="theme === 'dark'" :size="18" weight="fill" color="var(--color-neutral-300)" />
    <PhMoon v-else :size="18" weight="fill" color="var(--color-neutral-300)" />
  </button>
</template>

<style scoped>
.theme-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  border: none;
  background: none;
  color: inherit;
  cursor: pointer;
}
</style>
