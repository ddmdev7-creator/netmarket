<script setup lang="ts">
import { PhCaretRight, PhConfetti } from '@phosphor-icons/vue'
import type { Component } from 'vue'

export interface TodoItem {
  key: string
  /** Chiffre mis en avant (omis pour une carte purement informative). */
  count?: number
  /** Chiffre déjà formaté (ex. un montant) — remplace count à l'affichage. */
  countLabel?: string
  title: string
  text: string
  icon: Component
  hue: number
  /** Liseré de couleur : demande une action rapide. */
  urgent?: boolean
  /** Lien ; sinon la carte émet `select` avec sa clé. */
  to?: string
  /** Carte « active » (filtre en cours sur la page). */
  active?: boolean
}

/**
 * Section « À faire » des espaces vendeur, livreur et point de retrait :
 * ce qui attend une action, chaque carte menant à la liste concernée.
 */
defineProps<{ items: TodoItem[]; emptyText?: string }>()
const emit = defineEmits<{ select: [key: string] }>()
</script>

<template>
  <div v-if="items.length" class="todo-grid">
    <component
      :is="item.to ? resolveComponent('NuxtLink') : 'button'"
      v-for="item in items"
      :key="item.key"
      :to="item.to"
      :type="item.to ? undefined : 'button'"
      class="todo-card"
      :class="{ 'todo-card--urgent': item.urgent, 'todo-card--active': item.active }"
      :style="{ '--hue': item.hue }"
      :aria-pressed="item.to ? undefined : !!item.active"
      @click="!item.to && emit('select', item.key)"
    >
      <span class="todo-card__icon"><component :is="item.icon" :size="20" weight="duotone" /></span>
      <span class="todo-card__body">
        <span class="todo-card__title">
          <strong v-if="item.countLabel || item.count !== undefined">{{ item.countLabel ?? item.count }}</strong>
          {{ item.title }}
        </span>
        <span class="todo-card__text">{{ item.text }}</span>
      </span>
      <PhCaretRight :size="16" class="todo-card__go" />
    </component>
  </div>
  <div v-else-if="emptyText" class="todo-clear">
    <PhConfetti :size="22" weight="duotone" />
    <span>{{ emptyText }}</span>
  </div>
</template>

<style scoped>
.todo-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 8px;
}

.todo-card {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 12px 14px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-divider);
  background: var(--color-neutral-900);
  color: inherit;
  text-align: left;
  text-decoration: none;
  font: inherit;
  cursor: pointer;
  transition: border-color 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease;
}

.todo-card:hover {
  border-color: hsl(var(--hue) 60% 50%);
  transform: translateY(-1px);
}

.todo-card--urgent {
  border-left: 4px solid hsl(var(--hue) 70% 52%);
}

.todo-card--active {
  border-color: hsl(var(--hue) 65% 50%);
  box-shadow: 0 0 0 3px hsl(var(--hue) 70% var(--tint-bg));
}

.todo-card__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  border-radius: 12px;
  background: hsl(var(--hue) 70% var(--tint-bg));
  color: hsl(var(--hue) 60% var(--tint-fg));
}

.todo-card__body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.todo-card__title {
  font-size: 14px;
  color: var(--color-neutral-200);
}

.todo-card__title strong {
  font-family: var(--font-heading);
  font-size: 16px;
  font-weight: 800;
}

.todo-card__text {
  font-size: 12px;
  color: var(--color-neutral-400);
}

.todo-card__go {
  flex-shrink: 0;
  color: var(--color-neutral-500);
}

.todo-clear {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px;
  border-radius: var(--radius-md);
  background: hsl(150 70% var(--tint-bg-soft));
  color: hsl(150 55% var(--tint-fg));
  font-size: 13px;
}
</style>
