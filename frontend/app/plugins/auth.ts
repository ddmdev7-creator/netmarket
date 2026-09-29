/**
 * Recharge le profil de l'utilisateur connecté une fois au démarrage (rendu
 * serveur compris) : la barre du haut, le numéro prérempli au paiement…
 * disposent ainsi de auth.user dès le premier affichage.
 */
export default defineNuxtPlugin(async () => {
  await useAuthStore().restoreSession()
})
