<script setup lang="ts">
import { PhCheckCircle, PhInfo, PhX, PhXCircle } from '@phosphor-icons/vue'

const toast = useToastStore()

const icons: Record<string, typeof PhCheckCircle> = { success: PhCheckCircle, error: PhXCircle, info: PhInfo }

// Un vrai <div> par toast plutôt qu'un unique v-snackbar réutilisé : Vuetify
// ne réarme son timer interne que sur une transition false→true de
// model-value — avec un seul composant partagé, fermer le toast n°1 fait
// juste passer "current" au n°2 sans jamais repasser par false, donc le
// timer ne se réarmait jamais pour les toasts suivants d'une même rafale.
// Ici chaque toast a son propre setTimeout, indépendant des autres, et
// s'affiche vraiment empilé (pas un seul à la fois).
const timers = new Map<number, ReturnType<typeof setTimeout>>()

watch(
  () => toast.queue.map((t) => t.id),
  (ids) => {
    for (const id of ids) {
      if (timers.has(id)) continue
      timers.set(
        id,
        setTimeout(() => toast.dismiss(id), 4000),
      )
    }
    for (const id of timers.keys()) {
      if (!ids.includes(id)) {
        clearTimeout(timers.get(id))
        timers.delete(id)
      }
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  for (const timer of timers.values()) clearTimeout(timer)
  timers.clear()
})
</script>

<template>
  <div class="toast-host">
    <TransitionGroup name="toast">
      <div v-for="item in toast.queue" :key="item.id" class="toast-item" :class="`toast-item--${item.type}`">
        <component :is="icons[item.type]" :size="18" weight="fill" class="toast-item__icon" />
        <span class="toast-item__message">{{ item.message }}</span>
        <button type="button" class="toast-item__close" aria-label="Fermer" @click="toast.dismiss(item.id)">
          <PhX :size="14" />
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
/* Toujours au-dessus de la barre du haut / bottom nav, quel que soit le
   layout — voir components/layout/TopBar.vue et BottomNav.vue. */
.toast-host {
  position: fixed;
  top: calc(12px + env(safe-area-inset-top, 0px));
  left: 50%;
  transform: translateX(-50%);
  z-index: 20;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 0 16px;
  pointer-events: none;
}

.toast-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  max-width: 340px;
  padding: 12px 14px;
  border-radius: var(--radius-md);
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider);
  box-shadow: var(--shadow-lg);
  pointer-events: auto;
}

.toast-item__icon {
  flex: none;
}

.toast-item--success .toast-item__icon {
  color: var(--color-success);
}

.toast-item--error .toast-item__icon {
  color: var(--color-error);
}

.toast-item--info .toast-item__icon {
  color: var(--color-primary);
}

.toast-item__message {
  flex: 1 1 auto;
  font-size: 13.5px;
  line-height: 1.35;
}

.toast-item__close {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  color: var(--color-neutral-400);
  padding: 4px;
  margin: -4px;
  cursor: pointer;
}

.toast-enter-active,
.toast-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.toast-enter-from {
  opacity: 0;
  transform: translateY(-8px);
}

.toast-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

.toast-leave-active {
  position: absolute;
}
</style>
