<script setup lang="ts">
import { PhArrowLeft, PhBellSlash, PhCheckCircle } from '@phosphor-icons/vue'
import type { NotificationRead } from '~/types/api'

definePageMeta({ middleware: 'auth', layout: 'blank' })

const router = useRouter()
const auth = useAuthStore()
const notifications = useNotificationStore()

onMounted(() => {
  notifications.fetchInitial()
})

function targetPath(notification: NotificationRead): string | null {
  if (!notification.order_id) return null
  return auth.user?.role === 'vendor'
    ? `/vendeur/commandes?highlight=${notification.order_id}`
    : `/commandes/${notification.order_id}`
}

async function open(notification: NotificationRead) {
  await notifications.markRead(notification.id)
  const path = targetPath(notification)
  if (path) router.push(path)
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <div class="app-shell" style="padding-bottom: 32px">
    <div class="d-flex align-center pa-2 ga-2">
      <v-btn icon variant="text" @click="router.back()">
        <PhArrowLeft :size="20" />
      </v-btn>
      <h1 class="text-h6">Notifications</h1>
      <v-btn
        v-if="notifications.unreadCount > 0"
        variant="text"
        size="small"
        class="ml-auto"
        @click="notifications.markAllRead()"
      >
        <PhCheckCircle :size="16" class="mr-1" />
        Tout marquer lu
      </v-btn>
      <LayoutHomeLink v-else />
    </div>

    <div class="px-4">
      <CommonEmptyState
        v-if="notifications.items.length === 0"
        message="Aucune notification pour l'instant."
        :icon="PhBellSlash"
      />

      <button
        v-for="n in notifications.items"
        :key="n.id"
        type="button"
        class="notification-row"
        :class="{ 'notification-row--unread': !n.read_at }"
        @click="open(n)"
      >
        <div class="d-flex justify-space-between align-center mb-1">
          <span class="notification-row__title">{{ n.title }}</span>
          <span class="text-muted text-fine">{{ formatDate(n.created_at) }}</span>
        </div>
        <div class="text-muted text-meta">{{ n.body }}</div>
      </button>
    </div>
  </div>
</template>

<style scoped>
.notification-row {
  display: block;
  width: 100%;
  text-align: left;
  padding: 12px 10px;
  border-radius: var(--radius-sm);
  border: none;
  background: transparent;
  border-bottom: 1px solid var(--color-divider);
  cursor: pointer;
}

.notification-row--unread {
  /* Léger lavis teinté primary plutôt qu'un fallback blanc qui ne se voyait
     déjà quasiment plus (--color-accent-900 référencé ici n'a jamais existé
     comme token — cette règle utilisait donc toujours son fallback). */
  background: rgba(10, 102, 245, 0.08);
}

.notification-row__title {
  font-size: 13.5px;
  font-weight: 600;
}

.notification-row--unread .notification-row__title::before {
  content: '';
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: var(--color-primary);
  margin-right: 6px;
}
</style>
