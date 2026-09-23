import type { ReviewableProductRead, ReviewRead } from '~/types/api'

/**
 * Produits reçus par l'acheteur connecté, notés ou non (GET /reviews/mine) —
 * partagé par « Mes commandes », le détail d'une commande et la fiche
 * produit (même clé useAsyncData : un seul appel, et un avis publié depuis
 * l'un se voit aussitôt dans les autres via `applyReview`).
 *
 * Chargé côté client seulement : la liste dépend du compte, et n'a aucun
 * intérêt pour un visiteur non connecté (liste vide).
 */
export function useReviewableProducts() {
  const { apiFetch } = useApi()
  const auth = useAuthStore()

  const { data, pending, refresh } = useAsyncData(
    'my-reviewable-products',
    () => (auth.isAuthenticated ? apiFetch<ReviewableProductRead[]>('/reviews/mine') : Promise.resolve([])),
    { default: () => [] as ReviewableProductRead[], server: false, watch: [() => auth.isAuthenticated] },
  )

  const byProduct = computed(() => new Map(data.value.map((p) => [p.product_id, p])))
  const toReview = computed(() => data.value.filter((p) => !p.review))

  /** Met à jour la liste locale après une création/modification d'avis, sans rappel réseau. */
  function applyReview(review: ReviewRead) {
    data.value = data.value.map((p) => (p.product_id === review.product_id ? { ...p, review } : p))
  }

  return { products: data, pending, refresh, byProduct, toReview, applyReview }
}
