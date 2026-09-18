export default defineNuxtRouteMiddleware(async (to) => {
  const auth = useAuthStore()
  if (!auth.isAuthenticated) {
    return navigateTo({ path: '/connexion', query: { redirect: to.fullPath } })
  }
  if (!auth.user) await auth.fetchMe()
  if (!auth.isAuthenticated) {
    return navigateTo({ path: '/connexion', query: { redirect: to.fullPath } })
  }
  // Un vendeur dont la boutique EST un point de retrait peut aussi gérer ce
  // point avec son compte habituel (voir PickupPoint.vendor_id côté backend)
  // — is_pickup_point_manager le signale sans changer son rôle principal.
  if (auth.user?.role !== 'pickup_point_manager' && !auth.user?.is_pickup_point_manager) {
    return navigateTo('/profil')
  }
})
