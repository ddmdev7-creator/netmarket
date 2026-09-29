<script setup lang="ts">
/**
 * Numéro de commande mis en forme : « #GN- » discret, code en couleur de la
 * marque — même rendu dans la liste des commandes et sur le suivi.
 */
const props = withDefaults(defineProps<{ id: string; size?: 'sm' | 'lg' }>(), { size: 'sm' })
const code = computed(() => props.id.slice(0, 5).toUpperCase())
</script>

<template>
  <span class="onum" :class="`onum--${size}`" :aria-label="`Commande numéro GN-${code}`">
    <span class="onum__hash">#</span><span class="onum__prefix">GN-</span><span class="onum__code">{{ code }}</span>
  </span>
</template>

<style scoped>
.onum {
  display: inline-flex;
  align-items: baseline;
  font-family: var(--font-heading);
  font-weight: 800;
  letter-spacing: 0.01em;
  white-space: nowrap;
}

.onum__hash {
  color: var(--color-accent);
}

.onum__prefix {
  color: var(--color-neutral-400);
}

.onum__code {
  background: linear-gradient(120deg, var(--color-primary), #7c3aed);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.onum--sm {
  font-size: 15px;
}

.onum--lg {
  font-size: inherit;
}
</style>
