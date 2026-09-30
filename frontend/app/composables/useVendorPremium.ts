import type { VendorSubscriptionRead } from '~/types/api'

/**
 * Statut Premium du vendeur connecté — clé useAsyncData partagée : tous les
 * sélecteurs de photos d'un même formulaire (produit + variantes) réutilisent
 * la même requête.
 */
export function useVendorPremium() {
  const { apiFetch } = useApi()
  const { data: subscription } = useAsyncData(
    'vendor-premium-status',
    () => apiFetch<VendorSubscriptionRead | null>('/subscriptions/me'),
    { default: () => null },
  )
  const isPremium = computed(() => subscription.value?.status === 'active')
  return { subscription, isPremium }
}
