/**
 * Style MapLibre partagé par tous les composants carte (MapPicker,
 * PickupPointsMap...).
 *
 * Tuiles raster Esri "Light/Dark Gray Canvas" (services.arcgisonline.com) —
 * gratuites, sans clé API, utilisables en production sans compte ArcGIS.
 * Remplace les tuiles CARTO utilisées précédemment : CARTO a fait évoluer sa
 * politique d'usage de son CDN de basemaps anonyme (`basemaps.cartocdn.com`)
 * vers un compte + clé API pour un usage en dehors de CARTO Builder, ce que
 * l'app signalait déjà à l'utilisateur — Esri évite complètement ce risque.
 *
 * Chaque style combine deux couches : le fond gris ("Base") puis les
 * libellés/routes/frontières par-dessus ("Reference") — c'est le découpage
 * standard de ce basemap chez Esri, une seule couche ne suffit pas à lire la
 * carte (aucun nom de lieu/rue dessus).
 *
 * Deux variantes (claire/sombre) plutôt qu'une carte toujours sombre : avant
 * ce changement, la carte restait figée sur des tuiles sombres même sous le
 * thème clair (par défaut de l'app), ce qui la faisait trancher sur le reste
 * de l'UI — voir getMapRasterStyle(), appelé avec le thème courant par les
 * composants carte et réappliqué (map.setStyle) au changement de thème.
 *
 * `maxzoom: 16` sur les deux sources — au-delà, Esri ne couvre pas la
 * Guinée à cette échelle et renvoie une tuile "Map data not yet available"
 * (texte incrusté dans l'image, vérifié par échantillonnage sur Conakry,
 * Kankan et Labé) plutôt qu'une 404 : sans ce plafond, zoomer à fond sur la
 * carte (molette/pincement, ou les boutons +/- du NavigationControl)
 * affichait ce message en boucle. Avec `maxzoom`, MapLibre arrête de
 * demander des tuiles au-delà du niveau 16 et agrandit la dernière tuile
 * valide à la place (légèrement flou en zoom extrême, mais jamais ce
 * placeholder).
 */
import type * as MapLibreGL from 'maplibre-gl'
import type { AppThemeName } from '~/composables/useAppTheme'

function esriCanvasStyle(variant: 'Light' | 'Dark'): MapLibreGL.StyleSpecification {
  const base = `https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_${variant}_Gray_Base/MapServer/tile/{z}/{y}/{x}`
  const reference = `https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_${variant}_Gray_Reference/MapServer/tile/{z}/{y}/{x}`
  return {
    version: 8,
    sources: {
      'esri-gray-base': {
        type: 'raster',
        tiles: [base],
        tileSize: 256,
        maxzoom: 16,
        attribution: 'Esri, HERE, Garmin, FAO, NOAA, USGS',
      },
      'esri-gray-reference': {
        type: 'raster',
        tiles: [reference],
        tileSize: 256,
        maxzoom: 16,
      },
    },
    layers: [
      { id: 'esri-gray-base', type: 'raster', source: 'esri-gray-base' },
      { id: 'esri-gray-reference', type: 'raster', source: 'esri-gray-reference' },
    ],
  }
}

const MAP_RASTER_STYLE_LIGHT = esriCanvasStyle('Light')
const MAP_RASTER_STYLE_DARK = esriCanvasStyle('Dark')

export function getMapRasterStyle(theme: AppThemeName): MapLibreGL.StyleSpecification {
  return theme === 'dark' ? MAP_RASTER_STYLE_DARK : MAP_RASTER_STYLE_LIGHT
}

// Conakry — centre par défaut tant qu'aucune position/point n'oriente encore
// la carte.
export const MAP_DEFAULT_CENTER: [number, number] = [-13.5784, 9.6412]
export const MAP_DEFAULT_ZOOM = 13
