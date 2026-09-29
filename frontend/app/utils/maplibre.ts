import type * as MapLibreGL from 'maplibre-gl'

let loaded: Promise<typeof MapLibreGL> | null = null

/**
 * Charge MapLibre (côté client uniquement) en lui indiquant où trouver son
 * worker — publié sous /maplibre par nuxt.config.ts (nitro.publicAssets).
 * Toutes les cartes de l'app passent par ici plutôt que par import() direct.
 */
export function loadMapLibre(): Promise<typeof MapLibreGL> {
  if (!loaded) {
    loaded = import('maplibre-gl').then((lib) => {
      lib.setWorkerUrl('/maplibre/maplibre-gl-worker.mjs')
      return lib
    })
  }
  return loaded
}
