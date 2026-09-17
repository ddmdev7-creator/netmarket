<script setup lang="ts">
import { PhBell, PhUserCircle } from '@phosphor-icons/vue'

const auth = useAuthStore()
const notifications = useNotificationStore()

const roleLabel = computed(() => {
  switch (auth.user?.role) {
    case 'vendor':
      return 'Vendeur'
    case 'admin':
      return 'Admin'
    default:
      return 'Acheteur'
  }
})

const displayIdentity = computed(() => {
  const user = auth.user
  if (!user) return ''
  if (user.first_name && user.last_name) {
    return `${user.first_name[0].toUpperCase()}. ${user.last_name}`
  }
  return user.phone
})
</script>

<template>
  <div v-if="auth.user" class="top-bar">
    <slot name="leading" />
    <NuxtLink to="/profil" class="top-bar__identity">
      <PhUserCircle :size="18" color="var(--color-neutral-400)" />
      <span class="top-bar__phone">{{ displayIdentity }}</span>
    </NuxtLink>
    <span class="top-bar__role">{{ roleLabel }}</span>
    <LayoutThemeToggle />
    <NuxtLink to="/notifications" class="top-bar__bell" aria-label="Notifications">
      <PhBell :size="19" color="var(--color-neutral-300)" />
      <span v-if="notifications.unreadCount > 0" class="top-bar__badge">
        {{ notifications.unreadCount > 9 ? '9+' : notifications.unreadCount }}
      </span>
    </NuxtLink>
  </div>
</template>

<style scoped>
.top-bar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 8px;
  /* The notch/status-bar offset itself now lives on `.v-main` (main.css) —
     applying it here too would double it up. */
  padding: 8px 16px 8px;
  background: var(--color-neutral-900);
  border-bottom: 1px solid var(--color-divider);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
  color: var(--color-neutral-200);
  font-size: 13px;
}

.top-bar__identity {
  display: flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
  color: inherit;
  min-width: 0;
}

.top-bar__phone {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.top-bar__role {
  margin-left: auto;
  color: var(--color-neutral-400);
  font-size: 11.5px;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-sm);
  padding: 2px 8px;
  flex-shrink: 0;
}

.top-bar__bell {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  color: inherit;
}

.top-bar__badge {
  position: absolute;
  top: 0;
  right: 0;
  min-width: 15px;
  height: 15px;
  padding: 0 3px;
  border-radius: 999px;
  background: var(--color-error);
  color: #fff;
  font-size: 9.5px;
  font-weight: 700;
  line-height: 15px;
  text-align: center;
}
</style>
