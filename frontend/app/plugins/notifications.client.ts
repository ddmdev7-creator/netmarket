/**
 * Owns the notification WebSocket's lifecycle for the whole session — one
 * connection regardless of which layout (buyer/vendor/admin) is mounted,
 * rather than connecting from LayoutTopBar (shared by several layouts,
 * which would reconnect on every layout switch).
 */
export default defineNuxtPlugin(() => {
  const auth = useAuthStore()
  const notifications = useNotificationStore()

  watch(
    () => auth.isAuthenticated,
    (isAuthenticated) => {
      if (isAuthenticated) {
        notifications.fetchInitial()
        notifications.connect()
      } else {
        notifications.disconnect()
      }
    },
    { immediate: true },
  )

  // Mobile : l'appli revient au premier plan ou retrouve le réseau.
  window.addEventListener('online', () => notifications.reconnectNow())
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) notifications.reconnectNow()
  })
})
