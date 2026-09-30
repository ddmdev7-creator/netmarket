import type { SubscriptionOverview } from '~/types/api'

/**
 * Formule et quotas du vendeur connecté (GET /subscriptions/me/overview) —
 * clé useAsyncData partagée : le formulaire produit, ses sélecteurs de
 * photos et la page abonnement lisent la même requête.
 */
export function useVendorPlan() {
  const { apiFetch } = useApi()
  const { data: overview, refresh } = useAsyncData(
    'vendor-plan-overview',
    () => apiFetch<SubscriptionOverview>('/subscriptions/me/overview'),
    { default: () => null },
  )
  const aiLimit = computed(() => overview.value?.ai_enhancements.limit ?? 0)
  const aiUsed = computed(() => overview.value?.ai_enhancements.used ?? 0)
  // null = illimité.
  const aiLeft = computed(() => (overview.value && aiLimit.value === null ? null : Math.max(0, (aiLimit.value ?? 0) - aiUsed.value)))
  const aiAvailable = computed(() => aiLeft.value === null || aiLeft.value > 0)
  const maxImages = computed(() => overview.value?.max_images_per_product ?? null)
  const planName = computed(() => overview.value?.plan.name ?? '')

  /** Compte localement une amélioration réussie, sans refaire la requête. */
  function countAi(n = 1) {
    if (overview.value) overview.value.ai_enhancements.used += n
  }

  return { overview, refresh, aiLimit, aiUsed, aiLeft, aiAvailable, maxImages, planName, countAi }
}
