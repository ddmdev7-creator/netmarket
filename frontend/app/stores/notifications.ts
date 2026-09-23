import { defineStore } from 'pinia'
import type { NotificationList, NotificationRead } from '~/types/api'

/**
 * In-app notification feed + live WebSocket push. Connection lifecycle is
 * driven by plugins/notifications.client.ts (watches auth state) rather than
 * by whichever layout happens to mount LayoutTopBar, so there's exactly one
 * socket per session regardless of which page/layout is active.
 */
export const useNotificationStore = defineStore('notifications', () => {
  const items = ref<NotificationRead[]>([])
  const unreadCount = ref(0)
  // Offre de livraison en cours (dispatch séquentiel par distance — voir
  // app/orders/service.py::start_dispatch côté backend) : une modale dédiée
  // (LayoutDeliveryRequestModal) l'affiche plutôt que le toast générique,
  // pour l'urgence façon VTC. Une seule à la fois — un livreur peut en
  // théorie être candidat sur deux sous-commandes en même temps, la plus
  // récente écrase juste l'affichage, cohérent avec le reste du design
  // volontairement simple de cette fonctionnalité.
  const pendingDeliveryRequest = ref<NotificationRead | null>(null)
  // Signal silencieux « relis tes colis » (backend notifications.push_refresh,
  // jamais affiché) : les écrans livreur / point de retrait surveillent ce
  // compteur pour se rafraîchir en direct.
  const deliveriesTick = ref(0)
  let socket: WebSocket | null = null
  let reconnectTimeout: ReturnType<typeof setTimeout> | null = null
  let reconnectDelay = 1000

  async function fetchInitial() {
    const { apiFetch } = useApi()
    try {
      const data = await apiFetch<NotificationList>('/notifications')
      items.value = data.items
      unreadCount.value = data.unread_count
    } catch {
      // Best-effort — le badge reste simplement à son état précédent (ou vide).
    }
  }

  function handleIncoming(notification: NotificationRead | { type: 'refresh'; scope: string }) {
    if (notification.type === 'refresh') {
      deliveriesTick.value += 1
      return
    }
    items.value = [notification, ...items.value].slice(0, 50)
    unreadCount.value += 1
    if (notification.type === 'delivery_request') {
      pendingDeliveryRequest.value = notification
    } else {
      useToastStore().info(notification.title)
    }
  }

  function clearDeliveryRequest() {
    pendingDeliveryRequest.value = null
  }

  async function markRead(id: string) {
    const target = items.value.find((n) => n.id === id)
    if (!target || target.read_at) return
    target.read_at = new Date().toISOString()
    unreadCount.value = Math.max(0, unreadCount.value - 1)
    const { apiFetch } = useApi()
    try {
      await apiFetch(`/notifications/${id}/read`, { method: 'PATCH' })
    } catch {
      // Optimistic update left in place — a stale unread badge is harmless
      // and will self-correct on the next fetchInitial().
    }
  }

  async function markAllRead() {
    const hadUnread = unreadCount.value > 0
    items.value = items.value.map((n) => ({ ...n, read_at: n.read_at ?? new Date().toISOString() }))
    unreadCount.value = 0
    if (!hadUnread) return
    const { apiFetch } = useApi()
    try {
      await apiFetch('/notifications/read-all', { method: 'POST' })
    } catch {
      // Same rationale as markRead.
    }
  }

  // Le jeton d'accès (30 min) n'est vérifié qu'à l'ouverture du socket : une
  // reconnexion après une coupure réseau (fréquente sur mobile) avec un jeton
  // expiré serait refusée en boucle. On le renouvelle d'abord s'il expire.
  function tokenExpiresSoon(token: string): boolean {
    try {
      const payload = JSON.parse(atob(token.split('.')[1]!.replace(/-/g, '+').replace(/_/g, '/')))
      return typeof payload.exp !== 'number' || payload.exp * 1000 < Date.now() + 60_000
    } catch {
      return true
    }
  }

  let connecting = false
  async function connect() {
    if (socket || connecting) return
    const auth = useAuthStore()
    if (!auth.accessToken) return
    if (tokenExpiresSoon(auth.accessToken)) {
      connecting = true
      try {
        const refreshed = await auth.tryRefresh()
        if (!refreshed || !auth.accessToken || socket) return
      } finally {
        connecting = false
      }
    }

    const wsBase = useApiBase().replace(/^http/, 'ws')
    socket = new WebSocket(`${wsBase}/notifications/ws/notifications?token=${encodeURIComponent(auth.accessToken)}`)

    socket.onmessage = (event) => {
      try {
        handleIncoming(JSON.parse(event.data))
      } catch {
        // Message malformé — ignoré plutôt que de faire planter le socket.
      }
    }
    socket.onclose = () => {
      socket = null
      // Reconnexion avec backoff (réseau mobile instable) — plafonnée à 30s,
      // et abandonnée si l'utilisateur s'est déconnecté entre-temps.
      if (!useAuthStore().accessToken) return
      reconnectTimeout = setTimeout(() => {
        reconnectDelay = Math.min(reconnectDelay * 2, 30000)
        connect()
      }, reconnectDelay)
    }
    socket.onopen = () => {
      reconnectDelay = 1000
      // Reconnecté : ce qui a changé pendant la coupure est relu tout de suite.
      deliveriesTick.value += 1
    }
  }

  // Retour au premier plan ou du réseau : reconnexion immédiate plutôt que
  // d'attendre la fin du délai de reconnexion.
  function reconnectNow() {
    if (socket || !useAuthStore().accessToken) return
    if (reconnectTimeout) {
      clearTimeout(reconnectTimeout)
      reconnectTimeout = null
    }
    reconnectDelay = 1000
    connect()
  }

  function disconnect() {
    if (reconnectTimeout) {
      clearTimeout(reconnectTimeout)
      reconnectTimeout = null
    }
    reconnectDelay = 1000
    if (socket) {
      socket.onclose = null
      socket.close()
      socket = null
    }
    items.value = []
    unreadCount.value = 0
    pendingDeliveryRequest.value = null
  }

  return {
    items,
    unreadCount,
    pendingDeliveryRequest,
    deliveriesTick,
    reconnectNow,
    fetchInitial,
    markRead,
    markAllRead,
    clearDeliveryRequest,
    connect,
    disconnect,
  }
})
