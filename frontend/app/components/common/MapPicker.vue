<script setup lang="ts">
/**
 * Interactive pin-drop map — tap or drag to set a lat/lng, or use the search
 * box to jump to a named place. Built on MapLibre GL (open-source Mapbox GL
 * fork) with Esri's free raster basemap tiles (see mapStyle.ts — switched
 * from OpenFreeMap vector tiles after vector rendering silently produced a
 * blank map with maplibre-gl@6.4.0, with no errors firing; raster tiles use
 * a much simpler textured-quad pipeline and render reliably).
 *
 * MapLibre touches `window`/WebGL at import time, so it's loaded lazily
 * inside onMounted (client-only) rather than as a static top-level import —
 * a static import would crash Nuxt's SSR render of any page using this
 * component.
 */
import type * as MapLibreGL from 'maplibre-gl'
// Import CSS statiquement (sans effet sur `window`, donc sûr en SSR) — seul
// le JS de la lib doit être chargé paresseusement, voir onMounted ci-dessous.
import 'maplibre-gl/dist/maplibre-gl.css'
import { MAP_DEFAULT_CENTER, MAP_DEFAULT_ZOOM, getMapRasterStyle } from '~/utils/mapStyle'

const { theme } = useAppTheme()

const props = withDefaults(
  defineProps<{
    latitude: number | null
    longitude: number | null
    zoom?: number
  }>(),
  // 16 donne une vue nette au niveau de la rue/du bâtiment une fois une
  // position posée — sans ça la carte reste trop dézoomée pour bien voir où
  // on est exactement.
  { zoom: 16 },
)

const emit = defineEmits<{
  'update:latitude': [value: number]
  'update:longitude': [value: number]
}>()

const mapContainer = ref<HTMLDivElement | null>(null)
const mapFailed = ref(false)
// Diagnostic visible à l'écran plutôt que seulement en console — utile pour
// distinguer un vrai échec réseau (tuiles injoignables depuis la Guinée,
// connectivité mobile lente/coûteuse — cf. cahier des charges §1) d'un
// souci d'affichage, sans avoir besoin des outils de développement.
const tileErrorCount = ref(0)
const firstTileErrorMessage = ref('')

let maplibregl: typeof MapLibreGL | null = null
let map: MapLibreGL.Map | null = null
let marker: MapLibreGL.Marker | null = null

function setPosition(lat: number, lng: number) {
  emit('update:latitude', lat)
  emit('update:longitude', lng)
}

// Pose le repère s'il n'existe pas encore, sinon le déplace — un seul
// endroit qui sait comment créer un marqueur (couleur, draggable, handler),
// utilisé au montage, au clic, et quand la position change depuis
// l'extérieur (props), plutôt que de dupliquer cette logique trois fois.
function placeMarker(lngLat: [number, number]) {
  if (!maplibregl || !map) return
  if (marker) {
    marker.setLngLat(lngLat)
    return
  }
  marker = new maplibregl.Marker({ draggable: true, color: 'var(--color-primary)' }).setLngLat(lngLat).addTo(map)
  marker.on('dragend', () => {
    const { lat, lng } = marker!.getLngLat()
    setPosition(lat, lng)
  })
}

onMounted(async () => {
  maplibregl = await import('maplibre-gl')
  if (!mapContainer.value) return

  const hasPosition = props.latitude !== null && props.longitude !== null
  const center: [number, number] = hasPosition ? [props.longitude!, props.latitude!] : MAP_DEFAULT_CENTER

  try {
    map = new maplibregl.Map({
      container: mapContainer.value,
      style: getMapRasterStyle(theme.value),
      center,
      zoom: hasPosition ? props.zoom : MAP_DEFAULT_ZOOM,
      attributionControl: { compact: true },
    })
  } catch (err) {
    // Le cas le plus courant : WebGL indisponible (matériel/pilote,
    // certains environnements de bureau à distance/VM) — MapLibre ne peut
    // alors rien dessiner du tout. Sans ce filet, la carte reste juste vide,
    // sans aucune indication de ce qui s'est passé.
    console.error('[MapPicker] échec de création de la carte :', err)
    mapFailed.value = true
    return
  }

  map.on('error', (event) => {
    console.error('[MapPicker] erreur de chargement :', event.error)
    if (tileErrorCount.value === 0) firstTileErrorMessage.value = event.error?.message ?? 'Erreur inconnue'
    tileErrorCount.value++
  })

  // Filet contre un conteneur dont la taille n'était pas encore stabilisée
  // au moment de la création de la carte (ex. carte insérée dans un
  // v-card/v-dialog Vuetify dont la mise en page finit de s'appliquer juste
  // après le montage) — sans ça, la carte peut se dessiner avec un canevas
  // de mauvaise taille et paraître vide tant qu'on ne redimensionne pas la
  // fenêtre manuellement.
  map.once('load', () => map?.resize())

  // 'bottom-right' plutôt que 'top-right' — la barre de recherche occupe déjà
  // toute la largeur en haut de la carte et masquerait les boutons +/-.
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right')

  if (hasPosition) placeMarker(center)

  // Un tap n'importe où pose (ou déplace) le repère — pas besoin de viser un
  // bouton précis, important sur un petit écran de téléphone.
  map.on('click', (event) => {
    const { lat, lng } = event.lngLat
    placeMarker([lng, lat])
    setPosition(lat, lng)
  })
})

// Un résultat de recherche pose le repère au même titre qu'un tap direct sur
// la carte — mêmes règles (setPosition + placeMarker), pour ne pas dupliquer
// la logique de sélection.
function onSearchSelect({ lat, lng }: { lat: number; lng: number }) {
  if (!map) return
  placeMarker([lng, lat])
  setPosition(lat, lng)
  map.flyTo({ center: [lng, lat], zoom: Math.max(map.getZoom(), props.zoom) })
}

// Recentre/déplace le repère si la position change depuis l'extérieur (ex.
// "Utiliser ma position actuelle" côté formulaire) plutôt que seulement au
// prochain montage — sans ça, cliquer ce bouton après avoir déjà ouvert la
// carte ne bougerait pas visuellement le repère.
watch(
  () => [props.latitude, props.longitude],
  ([lat, lng]) => {
    if (!map || lat === null || lng === null) return
    const lngLat: [number, number] = [lng, lat]
    placeMarker(lngLat)
    map.flyTo({ center: lngLat, zoom: Math.max(map.getZoom(), props.zoom) })
  },
)

// Bascule le fond de carte quand l'utilisateur change de thème — les
// marqueurs (Marker MapLibre) sont de simples overlays DOM en dehors du
// style, ils survivent donc à setStyle() sans qu'on ait besoin de les
// recréer.
watch(theme, (value) => {
  map?.setStyle(getMapRasterStyle(value))
})

onBeforeUnmount(() => {
  map?.remove()
  map = null
  marker = null
})
</script>

<template>
  <div v-if="mapFailed" class="map-picker map-picker--failed">
    Carte indisponible sur cet appareil — utilise « Utiliser ma position actuelle » ou décris l'endroit ci-dessous.
  </div>
  <div v-else class="map-picker-wrap">
    <div ref="mapContainer" class="map-picker" role="application" aria-label="Choisir une position sur la carte" />
    <div class="map-picker__search">
      <CommonMapSearchBox @select="onSearchSelect" />
    </div>
    <p v-if="tileErrorCount > 0" class="map-picker__error">
      La carte ne charge pas correctement ({{ tileErrorCount }} ressource(s) en échec — connexion instable ?).
      Détail : {{ firstTileErrorMessage }}
    </p>
  </div>
</template>

<style scoped>
.map-picker-wrap {
  position: relative;
}

.map-picker {
  height: 260px;
  border-radius: var(--radius-lg);
  overflow: hidden;
  border: 1px solid var(--color-divider-strong);
  box-shadow: var(--shadow-md);
}

.map-picker__search {
  position: absolute;
  top: 10px;
  left: 10px;
  right: 10px;
  z-index: 2;
}

.map-picker--failed {
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 16px;
  font-size: 12px;
  color: var(--color-neutral-400);
  background: var(--color-neutral-900);
}

.map-picker__error {
  margin-top: 6px;
  font-size: 11px;
  color: var(--color-error, #e5484d);
}
</style>
