import type { NuxtApp } from '#app'

/**
 * getCachedData pour des données qui doivent toujours être fraîches (soldes,
 * listes admin, livraisons…) : à l'hydratation, reprend ce que le rendu
 * serveur vient de charger ; à chaque navigation ensuite, refait la requête.
 *
 * Remplace `getCachedData: hydrateThenRefetch`, qui jetait aussi les données du
 * rendu serveur : après un rechargement complet de la page, la liste restait
 * vide (valeur `default`) tant qu'on ne naviguait pas ailleurs puis revenait.
 */
export function hydrateThenRefetch<T>(key: string, nuxtApp: NuxtApp): T | undefined {
  return nuxtApp.isHydrating ? (nuxtApp.payload.data[key] as T | undefined) : undefined
}
