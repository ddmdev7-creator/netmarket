<script setup lang="ts">
/**
 * Champ de recherche détaché du fond : surface claire, bordure, ombre
 * légère et contour coloré au focus — pour les listes admin (utilisateurs,
 * suivi des livraisons…) où un champ « outlined » se fondait dans le fond gris.
 */
import { PhMagnifyingGlass, PhX } from '@phosphor-icons/vue'

const model = defineModel<string | null>({ default: '' })
withDefaults(defineProps<{ placeholder?: string; count?: number | null }>(), {
  placeholder: 'Rechercher…',
  count: null,
})
</script>

<template>
  <label class="search-bar">
    <PhMagnifyingGlass :size="19" class="search-bar__icon" />
    <input v-model="model" type="search" class="search-bar__input" :placeholder="placeholder" :aria-label="placeholder" />
    <span v-if="count !== null && (model ?? '').trim()" class="search-bar__count">{{ count }} résultat{{ count > 1 ? 's' : '' }}</span>
    <button v-if="(model ?? '').length" type="button" class="search-bar__clear" aria-label="Effacer la recherche" @click="model = ''">
      <PhX :size="15" weight="bold" />
    </button>
  </label>
</template>

<style scoped>
.search-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  max-width: 560px;
  height: 48px;
  padding: 0 12px 0 16px;
  border: 1px solid var(--color-divider);
  border-radius: 14px;
  background: var(--color-neutral-900);
  box-shadow: var(--shadow-sm);
  cursor: text;
  transition:
    border-color 0.15s,
    box-shadow 0.15s;
}

.search-bar:focus-within {
  border-color: var(--color-primary);
  box-shadow:
    0 0 0 3px color-mix(in srgb, var(--color-primary) 18%, transparent),
    var(--shadow-sm);
}

.search-bar__icon {
  flex: none;
  color: var(--color-primary);
}

.search-bar__input {
  flex: 1;
  min-width: 0;
  height: 100%;
  border: none;
  outline: none;
  background: transparent;
  font-size: 14.5px;
  color: var(--color-neutral-200);
}

.search-bar__input::placeholder {
  color: var(--color-neutral-500);
}

/* Croix native du champ « search » remplacée par la nôtre. */
.search-bar__input::-webkit-search-cancel-button {
  display: none;
}

.search-bar__count {
  flex: none;
  padding: 3px 8px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-primary) 12%, transparent);
  font-size: 12px;
  font-weight: 700;
  color: var(--color-primary);
  white-space: nowrap;
}

.search-bar__clear {
  flex: none;
  display: flex;
  padding: 6px;
  border: none;
  border-radius: 50%;
  background: var(--color-neutral-800);
  color: var(--color-neutral-400);
  cursor: pointer;
}
</style>
