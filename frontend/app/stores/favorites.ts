import { defineStore } from 'pinia'

/**
 * Ids des produits favoris de l'acheteur connecté — de quoi afficher le cœur
 * plein/vide sur chaque carte sans une requête par produit. Chargé à la
 * demande (premier cœur affiché), vidé à la déconnexion.
 */
export const useFavoritesStore = defineStore('favorites', () => {
  const ids = ref<Set<string>>(new Set())
  const loaded = ref(false)
  let loading: Promise<void> | null = null

  function ensureLoaded(): Promise<void> {
    const auth = useAuthStore()
    if (loaded.value || !auth.isAuthenticated) return Promise.resolve()
    if (!loading) {
      const { apiFetch } = useApi()
      loading = apiFetch<{ product_ids: string[] }>('/favorites/ids')
        .then((res) => {
          ids.value = new Set(res.product_ids)
          loaded.value = true
        })
        .catch(() => {})
        .finally(() => {
          loading = null
        })
    }
    return loading
  }

  function has(productId: string) {
    return ids.value.has(productId)
  }

  /** Bascule optimiste : le cœur change tout de suite, et revient en arrière si l'API refuse. */
  async function toggle(productId: string): Promise<boolean> {
    const { apiFetch } = useApi()
    const adding = !ids.value.has(productId)
    const next = new Set(ids.value)
    if (adding) next.add(productId)
    else next.delete(productId)
    ids.value = next
    try {
      await apiFetch(`/favorites/${productId}`, { method: adding ? 'PUT' : 'DELETE' })
      return adding
    } catch (e) {
      const rollback = new Set(ids.value)
      if (adding) rollback.delete(productId)
      else rollback.add(productId)
      ids.value = rollback
      throw e
    }
  }

  function reset() {
    ids.value = new Set()
    loaded.value = false
  }

  const count = computed(() => ids.value.size)

  // Déconnexion, ou passage d'un compte à un autre : les cœurs de l'ancien
  // compte disparaissent. (Le profil qui finit simplement de se charger,
  // null → id, ne doit rien vider.)
  const auth = useAuthStore()
  watch(
    () => auth.isAuthenticated,
    (authenticated) => {
      if (!authenticated) reset()
    },
  )
  watch(
    () => auth.user?.id,
    (id, previous) => {
      if (previous && id !== previous) reset()
    },
  )

  return { ids, loaded, count, ensureLoaded, has, toggle, reset }
})
