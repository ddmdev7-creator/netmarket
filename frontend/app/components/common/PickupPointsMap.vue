<script setup lang="ts">
/**
 * Carte affichant tous les points de retrait actifs — alternative visuelle à
 * la simple liste déroulante pour les repérer sur le terrain avant de
 * choisir. Un tap sur un repère affiche ses détails dans une fiche ancrée en
 * bas de la carte (plus fiable qu'une popup positionnée au pixel près, qui se
 * désynchronise au moindre pan/zoom) ; la barre de recherche ne fait que
 * déplacer la vue vers un lieu, elle ne pose pas de repère (les seuls points
 * sélectionnables sont ceux de la liste, gérée par l'admin).
 *
 * Mêmes contraintes SSR/WebGL que MapPicker.vue — voir ce fichier pour le
 * détail des gotchas (import paresseux, style raster Esri par thème).
 */
import type * as MapLibreGL from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { MAP_DEFAULT_CENTER, MAP_DEFAULT_ZOOM, getMapRasterStyle } from '~/utils/mapStyle'
import type { PickupPointRead } from '~/types/api'

const props = defineProps<{
  points: PickupPointRead[]
  modelValue: string | null
}>()

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const { theme } = useAppTheme()

const mapContainer = ref<HTMLDivElement | null>(null)
const mapFailed = ref(false)
const previewPoint = ref<PickupPointRead | null>(null)

let maplibregl: typeof MapLibreGL | null = null
let map: MapLibreGL.Map | null = null
const markerByPointId = new Map<string, { marker: MapLibreGL.Marker; el: HTMLElement }>()

const locatablePoints = computed(() => props.points.filter((p) => p.latitude !== null && p.longitude !== null))

function markerElement(selected: boolean): HTMLElement {
  const el = document.createElement('div')
  el.className = selected ? 'pp-marker pp-marker--selected' : 'pp-marker'
  return el
}

function refreshSelectedStyles() {
  for (const [id, { el }] of markerByPointId) {
    el.classList.toggle('pp-marker--selected', id === props.modelValue)
  }
}

function buildMarkers() {
  if (!maplibregl || !map) return
  for (const point of locatablePoints.value) {
    const el = markerElement(point.id === props.modelValue)
    const marker = new maplibregl.Marker({ element: el })
      .setLngLat([point.longitude!, point.latitude!])
      .addTo(map)
    el.addEventListener('click', (event) => {
      event.stopPropagation()
      previewPoint.value = point
    })
    markerByPointId.set(point.id, { marker, el })
  }
}

function fitToPoints() {
  if (!maplibregl || !map || locatablePoints.value.length === 0) return
  if (locatablePoints.value.length === 1) {
    const [only] = locatablePoints.value
    map.setCenter([only!.longitude!, only!.latitude!])
    map.setZoom(15)
    return
  }
  const bounds = new maplibregl.LngLatBounds()
  for (const point of locatablePoints.value) bounds.extend([point.longitude!, point.latitude!])
  map.fitBounds(bounds, { padding: 48, maxZoom: 16 })
}

function choosePreview() {
  if (!previewPoint.value) return
  emit('update:modelValue', previewPoint.value.id)
  previewPoint.value = null
}

function onSearchSelect({ lat, lng }: { lat: number; lng: number }) {
  map?.flyTo({ center: [lng, lat], zoom: 15 })
}

onMounted(async () => {
  maplibregl = await import('maplibre-gl')
  if (!mapContainer.value) return

  try {
    map = new maplibregl.Map({
      container: mapContainer.value,
      style: getMapRasterStyle(theme.value),
      center: MAP_DEFAULT_CENTER,
      zoom: MAP_DEFAULT_ZOOM,
      attributionControl: { compact: true },
    })
  } catch (err) {
    console.error('[PickupPointsMap] échec de création de la carte :', err)
    mapFailed.value = true
    return
  }

  map.once('load', () => map?.resize())
  // 'bottom-right' plutôt que 'top-right' — la barre de recherche occupe déjà
  // toute la largeur en haut de la carte et masquerait les boutons +/-.
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right')

  buildMarkers()
  fitToPoints()
})

// Un point sélectionné depuis l'extérieur (ex. adresse déjà enregistrée en
// édition) doit ressortir visuellement sur la carte sans que l'acheteur
// n'ait besoin de retaper dessus.
watch(() => props.modelValue, refreshSelectedStyles)

// Bascule le fond de carte au changement de thème — voir MapPicker.vue pour
// le même mécanisme et pourquoi les marqueurs n'ont pas besoin d'être
// recréés après setStyle().
watch(theme, (value) => {
  map?.setStyle(getMapRasterStyle(value))
})

onBeforeUnmount(() => {
  map?.remove()
  map = null
  markerByPointId.clear()
})
</script>

<template>
  <div v-if="mapFailed" class="pp-map pp-map--failed">
    Carte indisponible sur cet appareil — utilise la liste ci-dessous pour choisir un point de retrait.
  </div>
  <div v-else class="pp-map-wrap">
    <div ref="mapContainer" class="pp-map" role="application" aria-label="Choisir un point de retrait sur la carte" />
    <div class="pp-map__search">
      <CommonMapSearchBox @select="onSearchSelect" />
    </div>
    <Transition name="pp-sheet">
      <div v-if="previewPoint" class="pp-sheet">
        <div class="pp-sheet__body">
          <p class="pp-sheet__name">{{ previewPoint.name }}</p>
          <p class="pp-sheet__zone">{{ previewPoint.zone }}</p>
        </div>
        <div class="pp-sheet__actions">
          <button type="button" class="pp-sheet__close" @click="previewPoint = null">Fermer</button>
          <button type="button" class="pp-sheet__choose" @click="choosePreview">Choisir ce point</button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.pp-map-wrap {
  position: relative;
}

.pp-map {
  height: 280px;
  border-radius: var(--radius-lg);
  overflow: hidden;
  border: 1px solid var(--color-divider-strong);
  box-shadow: var(--shadow-md);
}

.pp-map__search {
  position: absolute;
  top: 10px;
  left: 10px;
  right: 10px;
  z-index: 2;
}

.pp-map--failed {
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 16px;
  font-size: 12px;
  color: var(--color-neutral-400);
  background: var(--color-neutral-900);
  height: 120px;
  border-radius: var(--radius-lg);
}

/* Fiche ancrée en bas — plus fiable qu'une popup au pixel près qui se
   désynchronise au pan/zoom, et plus confortable au pouce sur mobile. */
.pp-sheet {
  position: absolute;
  left: 10px;
  right: 10px;
  bottom: 10px;
  z-index: 3;
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider-strong);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-dock);
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.pp-sheet__name {
  margin: 0;
  font-size: 13.5px;
  font-weight: 700;
  color: var(--color-neutral-200);
}

.pp-sheet__zone {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--color-neutral-400);
}

.pp-sheet__actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.pp-sheet__close,
.pp-sheet__choose {
  border: none;
  border-radius: var(--radius-sm);
  padding: 7px 12px;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
}

.pp-sheet__close {
  background: transparent;
  color: var(--color-neutral-400);
}

.pp-sheet__close:hover {
  color: var(--color-neutral-200);
}

.pp-sheet__choose {
  background: var(--color-primary);
  /* Blanc plutôt que primary-800 : --color-primary est un bleu moyennement
     saturé (pas aussi clair que l'ancien orange), un texte foncé dessus
     manquait de contraste — blanc est le pairing standard sur un bouton
     bleu plein. */
  color: #ffffff;
}

.pp-sheet__choose:hover {
  filter: brightness(1.08);
}

.pp-sheet-enter-active,
.pp-sheet-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.pp-sheet-enter-from,
.pp-sheet-leave-to {
  opacity: 0;
  transform: translateY(6px);
}
</style>

<style>
/* Repère personnalisé — non scoped car injecté par MapLibre en dehors du DOM
   scoped du composant. Forme "pin" classique (rond + pointe) plutôt que le
   teardrop par défaut de MapLibre, pour un rendu plus soigné. */
.pp-marker {
  width: 26px;
  height: 26px;
  border-radius: 50% 50% 50% 0;
  background: var(--color-primary);
  border: 2px solid var(--color-primary-800);
  transform: rotate(-45deg);
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  transition: transform 0.12s ease, box-shadow 0.12s ease;
}

.pp-marker:hover {
  transform: rotate(-45deg) scale(1.12);
}

.pp-marker--selected {
  background: var(--color-primary-300);
  box-shadow: 0 0 0 4px rgba(10, 102, 245, 0.28), var(--shadow-md);
}
</style>
