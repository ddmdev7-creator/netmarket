import type { AdminAttention } from '~/types/api'

/**
 * Compteurs « à traiter » de l'administration, partagés entre le menu
 * latéral (pastilles) et le tableau de bord (section À traiter). Relus toutes
 * les minutes tant qu'une page admin est ouverte.
 */
export function useAdminAttention() {
  const attention = useState<AdminAttention | null>('admin-attention', () => null)
  const { apiFetch } = useApi()

  async function refresh() {
    try {
      attention.value = await apiFetch<AdminAttention>('/admin/attention')
    } catch {
      // Pastilles simplement absentes si l'appel échoue.
    }
  }

  function startPolling() {
    refresh()
    const timer = setInterval(() => {
      if (!document.hidden) refresh()
    }, 60_000)
    onBeforeUnmount(() => clearInterval(timer))
  }

  return { attention, refresh, startPolling }
}
