<script setup lang="ts">
import {
  PhArrowLeft,
  PhArrowsClockwise,
  PhBellSlash,
  PhCheckCircle,
  PhMotorcycle,
  PhPackage,
  PhWarningCircle,
  PhXCircle,
} from '@phosphor-icons/vue'
import type { Component } from 'vue'
import type { NotificationRead, NotificationType } from '~/types/api'

definePageMeta({ middleware: 'auth', layout: 'blank' })

const router = useRouter()
const auth = useAuthStore()
const notifications = useNotificationStore()

onMounted(() => {
  notifications.fetchInitial()
})

// Icône + teinte par type de notification — un aperçu du "quoi" avant même
// de lire le titre, plutôt que des lignes de texte toutes identiques
// visuellement quel que soit l'événement.
const ICON_BY_TYPE: Record<NotificationType, Component> = {
  order_received: PhPackage,
  order_status_changed: PhArrowsClockwise,
  courier_verification_approved: PhCheckCircle,
  courier_verification_rejected: PhXCircle,
  delivery_request: PhMotorcycle,
  delivery_request_accepted: PhCheckCircle,
  delivery_no_courier_found: PhWarningCircle,
}

const TONE_BY_TYPE: Record<NotificationType, 'primary' | 'success' | 'error'> = {
  order_received: 'primary',
  order_status_changed: 'primary',
  courier_verification_approved: 'success',
  courier_verification_rejected: 'error',
  delivery_request: 'primary',
  delivery_request_accepted: 'success',
  delivery_no_courier_found: 'error',
}

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

    <div class="px-4 detail-card">
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
        <div class="notification-row__icon" :class="`notification-row__icon--${TONE_BY_TYPE[n.type]}`">
          <component :is="ICON_BY_TYPE[n.type]" :size="19" weight="bold" />
        </div>
        <div class="notification-row__content">
          <div class="d-flex justify-space-between align-center mb-1 ga-2">
            <span class="notification-row__title">{{ n.title }}</span>
            <span class="text-muted text-fine" style="flex: none">{{ formatDate(n.created_at) }}</span>
          </div>
          <div class="text-muted text-meta">{{ n.body }}</div>
        </div>
      </button>
    </div>
  </div>
</template>

<style scoped>
.notification-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
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
  border-left: 3px solid var(--color-primary);
  background: color-mix(in srgb, var(--color-primary) 6%, transparent);
}

.notification-row__icon {
  flex: none;
  width: 38px;
  height: 38px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.notification-row__icon--primary {
  background: color-mix(in srgb, var(--color-primary) 14%, transparent);
  color: var(--color-primary);
}

.notification-row__icon--success {
  background: color-mix(in srgb, var(--color-success) 14%, transparent);
  color: var(--color-success);
}

.notification-row__icon--error {
  background: color-mix(in srgb, var(--color-error) 14%, transparent);
  color: var(--color-error);
}

.notification-row__content {
  flex: 1 1 auto;
  min-width: 0;
}

.notification-row__title {
  font-size: 13.5px;
  font-weight: 600;
}
</style>
