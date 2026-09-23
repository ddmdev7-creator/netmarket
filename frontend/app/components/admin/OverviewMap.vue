<script setup lang="ts">
/**
 * Carte d'ensemble admin : boutiques, points de retrait, livreurs… sur un
 * même fond, avec repères distincts par type (voir utils/mapPins.ts),
 * regroupement des repères proches en grappes numérotées, fiche détaillée de
 * l'élément sélectionné, légende, recherche de lieu et plein écran.
 * Utilisée par /admin/carte et par la vue « Carte » des écrans vendeurs,
 * livreurs et points de retrait.
 *
 * Les tracés (prop lines, ex. boutique → destination d'une livraison en
 * cours) sont, eux, une vraie couche GeoJSON : setStyle() l'efface, d'où
 * addLineLayers() rappelé à chaque 'style.load'. Un tracé touchant
 * l'élément sélectionné passe en surbrillance.
 *
 * Le regroupement est fait ici plutôt que par une couche GeoJSON MapLibre :
 * les repères sont des éléments DOM (icônes Phosphor) qui survivent aux
 * changements de style (thème clair/sombre) sans réenregistrer d'images ni
 * de couches, et l'effectif attendu (dizaines à quelques centaines de
 * points) ne justifie pas un index spatial. Deux éléments sont regroupés
 * quand leurs positions à l'écran sont à moins de CLUSTER_RADIUS_PX ; au-delà
 * de CLUSTER_MAX_ZOOM on ne regroupe plus (deux éléments quasi au même
 * endroit resteraient sinon groupés à l'infini).
 *
 * Mêmes contraintes SSR/WebGL que MapPicker.vue : MapLibre est importé
 * paresseusement dans onMounted.
 */
import type * as MapLibreGL from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { PhArrowSquareOut, PhCopy, PhNavigationArrow, PhStackSimple, PhX } from '@phosphor-icons/vue'
import { MAP_DEFAULT_CENTER, MAP_DEFAULT_ZOOM, getMapStyle, type MapLayerKind } from '~/utils/mapStyle'
import { MAP_PIN_META, createClusterPin, createPin, type MapPinKind, type PinHandle } from '~/utils/mapPins'

export interface OverviewMapItem {
  id: string
  kind: MapPinKind
  name: string
  subtitle: string | null
  lat: number
  lng: number
  /** Repère grisé (inactif, suspendu, rejeté). */
  muted?: boolean
  /** Petit point d'alerte sur le repère (ex. en attente de validation). */
  attention?: boolean
  statusLabel?: string
  statusTone?: 'success' | 'warning' | 'error' | 'neutral'
  details?: { label: string; value: string }[]
  href?: string
  hrefLabel?: string
}

export interface OverviewMapLine {
  id: string
  /** [lng, lat], comme MapLibre. */
  from: [number, number]
  to: [number, number]
  /** Éléments reliés par ce tracé : le sélectionner le met en surbrillance. */
  itemIds: string[]
}

const props = withDefaults(
  defineProps<{
    items: OverviewMapItem[]
    selectedId: string | null
    lines?: OverviewMapLine[]
    legendKinds?: MapPinKind[]
    ariaLabel?: string
    emptyText?: string
  }>(),
  {
    lines: () => [],
    legendKinds: () => ['shop', 'pickup', 'shop_pickup'],
    ariaLabel: 'Carte des boutiques et points de retrait',
    emptyText: 'Aucun élément à afficher avec ces filtres.',
  },
)

const emit = defineEmits<{ select: [id: string | null] }>()

const CLUSTER_RADIUS_PX = 46
const CLUSTER_MAX_ZOOM = 16.5

const { theme } = useAppTheme()
const toast = useToastStore()

const wrap = ref<HTMLDivElement | null>(null)
const mapContainer = ref<HTMLDivElement | null>(null)
const mapFailed = ref(false)
// Plan (clair/sombre selon le thème) par défaut ; satellite sur demande via
// le bouton .om-layer-toggle — voir utils/mapStyle.ts::getMapStyle.
const layerKind = ref<MapLayerKind>('plan')

let maplibregl: typeof MapLibreGL | null = null
let map: MapLibreGL.Map | null = null
let resizeObserver: ResizeObserver | null = null
let liveMarkers: Array<{ marker: MapLibreGL.Marker; pin: PinHandle }> = []

const selectedItem = computed(() => props.items.find((item) => item.id === props.selectedId) ?? null)

function clearMarkers() {
  for (const { marker, pin } of liveMarkers) {
    marker.remove()
    pin.dispose()
  }
  liveMarkers = []
}

function addMarker(pin: PinHandle, lngLat: [number, number], onClick: () => void) {
  if (!maplibregl || !map) return
  const marker = new maplibregl.Marker({ element: pin.el, anchor: 'bottom' }).setLngLat(lngLat).addTo(map)
  pin.el.addEventListener('click', (event) => {
    event.stopPropagation()
    onClick()
  })
  liveMarkers.push({ marker, pin })
}

function boundsOf(items: OverviewMapItem[]): MapLibreGL.LngLatBounds {
  const bounds = new maplibregl!.LngLatBounds()
  for (const item of items) bounds.extend([item.lng, item.lat])
  return bounds
}

/** Regroupe les éléments dont les positions à l'écran sont proches (glouton, O(n²) — n reste petit). */
function groupByProximity(items: OverviewMapItem[]): OverviewMapItem[][] {
  if (!map || map.getZoom() >= CLUSTER_MAX_ZOOM) return items.map((item) => [item])
  const projected = items.map((item) => ({ item, point: map!.project([item.lng, item.lat]) }))
  const taken = new Set<number>()
  const groups: OverviewMapItem[][] = []
  projected.forEach((seed, index) => {
    if (taken.has(index)) return
    const group = [seed.item]
    taken.add(index)
    projected.forEach((other, otherIndex) => {
      if (taken.has(otherIndex)) return
      if (Math.hypot(seed.point.x - other.point.x, seed.point.y - other.point.y) <= CLUSTER_RADIUS_PX) {
        group.push(other.item)
        taken.add(otherIndex)
      }
    })
    groups.push(group)
  })
  return groups
}

function rebuildMarkers() {
  if (!map || !maplibregl) return
  clearMarkers()

  // L'élément sélectionné n'est jamais absorbé dans une grappe : on doit
  // toujours voir où il est.
  const pool = props.items.filter((item) => item.id !== props.selectedId)
  const singles: OverviewMapItem[] = []
  for (const group of groupByProximity(pool)) {
    const [first] = group
    if (group.length === 1 && first) {
      singles.push(first)
      continue
    }
    const lng = group.reduce((sum, item) => sum + item.lng, 0) / group.length
    const lat = group.reduce((sum, item) => sum + item.lat, 0) / group.length
    addMarker(createClusterPin(group.length, `${group.length} éléments — zoomer`), [lng, lat], () => {
      const bounds = boundsOf(group)
      const sameSpot = bounds.getNorthEast().distanceTo(bounds.getSouthWest()) < 5
      if (sameSpot) map?.easeTo({ center: [lng, lat], zoom: (map?.getZoom() ?? 15) + 2 })
      else map?.fitBounds(bounds, { padding: 80, maxZoom: 17 })
    })
  }
  if (selectedItem.value) singles.push(selectedItem.value)

  for (const item of singles) {
    const pin = createPin(item.kind, {
      selected: item.id === props.selectedId,
      muted: item.muted ?? false,
      attention: item.attention ?? false,
      label: `${MAP_PIN_META[item.kind].label} : ${item.name}`,
    })
    addMarker(pin, [item.lng, item.lat], () => emit('select', item.id))
  }
}

function fitToItems() {
  if (!map || !maplibregl || props.items.length === 0) return
  if (props.items.length === 1) {
    const [only] = props.items
    map.easeTo({ center: [only!.lng, only!.lat], zoom: 15 })
    return
  }
  // Marge haute plus grande : la barre de recherche flotte en haut de la carte.
  map.fitBounds(boundsOf(props.items), { padding: { top: 76, bottom: 40, left: 40, right: 40 }, maxZoom: 15 })
}

function onSearchSelect({ lat, lng }: { lat: number; lng: number }) {
  map?.flyTo({ center: [lng, lat], zoom: 15 })
}

const LINE_SOURCE = 'om-lines'

function linesData(): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: props.lines.map((line) => ({
      type: 'Feature',
      properties: { highlighted: props.selectedId !== null && line.itemIds.includes(props.selectedId) },
      geometry: { type: 'LineString', coordinates: [line.from, line.to] },
    })),
  }
}

function addLineLayers() {
  if (!map || map.getSource(LINE_SOURCE)) return
  map.addSource(LINE_SOURCE, { type: 'geojson', data: linesData() })
  map.addLayer({
    id: 'om-lines-base',
    type: 'line',
    source: LINE_SOURCE,
    filter: ['!', ['get', 'highlighted']],
    layout: { 'line-cap': 'round' },
    paint: { 'line-color': '#64748b', 'line-width': 2, 'line-opacity': 0.6, 'line-dasharray': [2, 2] },
  })
  map.addLayer({
    id: 'om-lines-highlight',
    type: 'line',
    source: LINE_SOURCE,
    filter: ['get', 'highlighted'],
    layout: { 'line-cap': 'round' },
    paint: { 'line-color': MAP_PIN_META.courier.color, 'line-width': 4, 'line-opacity': 0.9 },
  })
}

function refreshLines() {
  const source = map?.getSource(LINE_SOURCE) as MapLibreGL.GeoJSONSource | undefined
  source?.setData(linesData())
}

const itemsKey = computed(() => props.items.map((item) => item.id).join('|'))

onMounted(async () => {
  maplibregl = await import('maplibre-gl')
  if (!mapContainer.value) return

  try {
    map = new maplibregl.Map({
      container: mapContainer.value,
      style: getMapStyle(theme.value, layerKind.value),
      center: MAP_DEFAULT_CENTER,
      zoom: MAP_DEFAULT_ZOOM,
      attributionControl: { compact: true },
    })
  } catch (err) {
    console.error('[OverviewMap] échec de création de la carte :', err)
    mapFailed.value = true
    return
  }

  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right')
  map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left')
  if (wrap.value) map.addControl(new maplibregl.FullscreenControl({ container: wrap.value }), 'bottom-right')

  map.on('zoomend', rebuildMarkers)
  map.on('style.load', addLineLayers)
  // Un clic dans le vide referme la fiche.
  map.on('click', () => emit('select', null))
  map.once('load', () => {
    map?.resize()
    rebuildMarkers()
    // Ouverte depuis « Voir sur la carte » : on part de l'élément visé
    // plutôt que de la vue d'ensemble.
    const item = selectedItem.value
    if (item) map?.jumpTo({ center: [item.lng, item.lat], zoom: 15 })
    else fitToItems()
  })

  // Le conteneur change de taille (panneau latéral replié, plein écran,
  // rotation du téléphone) sans que MapLibre le sache.
  resizeObserver = new ResizeObserver(() => map?.resize())
  resizeObserver.observe(mapContainer.value)
})

watch(itemsKey, () => {
  rebuildMarkers()
  fitToItems()
})

watch(
  () => props.selectedId,
  () => {
    rebuildMarkers()
    refreshLines()
    const item = selectedItem.value
    if (item && map) map.easeTo({ center: [item.lng, item.lat], zoom: Math.max(map.getZoom(), 15), duration: 500 })
  },
)

// Le contenu d'un élément peut changer sans que la liste d'ids change (statut).
watch(() => props.items, rebuildMarkers, { deep: false })
watch(() => props.lines, refreshLines)

// Un seul style à la fois dépend des deux (voir getMapStyle) : la satellite
// n'a pas de variante claire/sombre, mais garder theme dans le tableau
// couvre aussi le cas où l'admin change de thème pendant qu'il est en
// satellite (rien à faire, un simple recalcul suffit).
watch([theme, layerKind], ([themeValue, layerValue]) => {
  map?.setStyle(getMapStyle(themeValue, layerValue))
})

function toggleLayer() {
  layerKind.value = layerKind.value === 'plan' ? 'satellite' : 'plan'
}

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  clearMarkers()
  map?.remove()
  map = null
})

const directionsUrl = computed(() =>
  selectedItem.value
    ? `https://www.google.com/maps/dir/?api=1&destination=${selectedItem.value.lat},${selectedItem.value.lng}`
    : '#',
)

async function copyCoordinates() {
  if (!selectedItem.value) return
  const text = `${selectedItem.value.lat.toFixed(6)}, ${selectedItem.value.lng.toFixed(6)}`
  try {
    await navigator.clipboard.writeText(text)
    toast.success('Coordonnées copiées.')
  } catch {
    toast.error('Impossible de copier les coordonnées.')
  }
}

const legend = computed(() => props.legendKinds.map((kind) => ({ kind, ...MAP_PIN_META[kind] })))
</script>

<template>
  <div v-if="mapFailed" class="om-failed">
    Carte indisponible sur cet appareil (WebGL requis). La liste reste utilisable.
  </div>
  <div v-else ref="wrap" class="om-wrap">
    <div ref="mapContainer" class="om-map" role="application" :aria-label="ariaLabel" />

    <div class="om-search">
      <CommonMapSearchBox @select="onSearchSelect" />
    </div>

    <button
      type="button"
      class="om-layer-toggle"
      :aria-pressed="layerKind === 'satellite'"
      :aria-label="layerKind === 'plan' ? 'Passer en vue satellite' : 'Revenir au plan'"
      :title="layerKind === 'plan' ? 'Vue satellite' : 'Revenir au plan'"
      @click="toggleLayer"
    >
      <PhStackSimple :size="16" weight="bold" />
      {{ layerKind === 'plan' ? 'Satellite' : 'Plan' }}
    </button>

    <ul class="om-legend" aria-label="Légende">
      <li v-for="entry in legend" :key="entry.kind">
        <span class="om-legend__dot" :style="{ background: entry.color }">
          <component :is="entry.icon" :size="10" weight="fill" color="#fff" />
        </span>
        {{ entry.label }}
      </li>
    </ul>

    <div v-if="items.length === 0" class="om-empty">{{ emptyText }}</div>

    <Transition name="om-card">
      <aside v-if="selectedItem" class="om-card" :aria-label="`Détails : ${selectedItem.name}`">
        <button type="button" class="om-card__close" aria-label="Fermer la fiche" @click="emit('select', null)">
          <PhX :size="16" />
        </button>
        <span class="om-card__kind" :style="{ '--pin-color': MAP_PIN_META[selectedItem.kind].color }">
          <component :is="MAP_PIN_META[selectedItem.kind].icon" :size="13" weight="fill" />
          {{ MAP_PIN_META[selectedItem.kind].label }}
        </span>
        <h3 class="om-card__name">{{ selectedItem.name }}</h3>
        <p v-if="selectedItem.subtitle" class="om-card__subtitle">{{ selectedItem.subtitle }}</p>
        <span
          v-if="selectedItem.statusLabel"
          class="om-card__status"
          :class="`om-card__status--${selectedItem.statusTone ?? 'neutral'}`"
        >
          {{ selectedItem.statusLabel }}
        </span>
        <dl v-if="selectedItem.details?.length" class="om-card__details">
          <template v-for="detail in selectedItem.details" :key="detail.label">
            <dt>{{ detail.label }}</dt>
            <dd>{{ detail.value }}</dd>
          </template>
        </dl>
        <div class="om-card__actions">
          <NuxtLink v-if="selectedItem.href" :to="selectedItem.href" class="om-card__btn om-card__btn--primary">
            <PhArrowSquareOut :size="15" />
            {{ selectedItem.hrefLabel ?? 'Voir la fiche' }}
          </NuxtLink>
          <a :href="directionsUrl" target="_blank" rel="noopener" class="om-card__btn">
            <PhNavigationArrow :size="15" />
            Itinéraire
          </a>
          <button type="button" class="om-card__btn" @click="copyCoordinates">
            <PhCopy :size="15" />
            Coordonnées
          </button>
        </div>
      </aside>
    </Transition>
  </div>
</template>

<style scoped>
.om-wrap {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 420px;
  border-radius: var(--radius-lg);
  overflow: hidden;
  border: 1px solid var(--color-divider-strong);
  box-shadow: var(--shadow-md);
  background: var(--color-neutral-800);
}

.om-map {
  position: absolute;
  inset: 0;
}

.om-failed {
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 24px;
  min-height: 160px;
  font-size: 13px;
  color: var(--color-neutral-400);
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-lg);
}

.om-search {
  position: absolute;
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  width: calc(100% - 24px);
  max-width: 420px;
  z-index: 2;
}

.om-layer-toggle {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 9px 12px;
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider-strong);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-md);
  color: var(--color-neutral-200);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.om-layer-toggle:hover {
  background: var(--color-neutral-800);
}

.om-layer-toggle[aria-pressed='true'] {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.om-legend {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 2;
  list-style: none;
  margin: 0;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider-strong);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-md);
  font-size: 11.5px;
  color: var(--color-neutral-300);
}

.om-legend li {
  display: flex;
  align-items: center;
  gap: 7px;
}

.om-legend__dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  flex-shrink: 0;
}

.om-empty {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  z-index: 2;
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider-strong);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-md);
  padding: 10px 16px;
  font-size: 13px;
  color: var(--color-neutral-300);
  text-align: center;
}

.om-card {
  position: absolute;
  z-index: 4;
  left: 12px;
  right: 12px;
  bottom: 40px;
  max-width: 380px;
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider-strong);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  padding: 14px 16px 14px;
}

.om-card__close {
  position: absolute;
  top: 8px;
  right: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--color-neutral-400);
  cursor: pointer;
}

.om-card__close:hover {
  background: var(--color-neutral-700);
  color: var(--color-neutral-200);
}

.om-card__kind {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  color: var(--pin-color);
}

.om-card__name {
  margin: 4px 28px 0 0;
  font-family: var(--font-heading);
  font-size: 16px;
  font-weight: 700;
  color: var(--color-neutral-200);
  overflow-wrap: anywhere;
}

.om-card__subtitle {
  margin: 2px 0 0;
  font-size: 12.5px;
  color: var(--color-neutral-400);
}

.om-card__status {
  display: inline-block;
  margin-top: 8px;
  padding: 2px 9px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
}

.om-card__status--success {
  background: color-mix(in srgb, var(--color-success) 16%, transparent);
  color: var(--color-success);
}

.om-card__status--warning {
  background: rgba(224, 130, 46, 0.16);
  color: #b3651a;
}

.om-card__status--error {
  background: color-mix(in srgb, var(--color-error) 14%, transparent);
  color: var(--color-error);
}

.om-card__status--neutral {
  background: var(--color-neutral-700);
  color: var(--color-neutral-400);
}

.om-card__details {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 4px 12px;
  margin: 10px 0 0;
  font-size: 12.5px;
}

.om-card__details dt {
  color: var(--color-neutral-400);
}

.om-card__details dd {
  margin: 0;
  color: var(--color-neutral-200);
  overflow-wrap: anywhere;
}

.om-card__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
}

.om-card__btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 7px 11px;
  border: 1px solid var(--color-divider-strong);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-neutral-300);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  text-decoration: none;
}

.om-card__btn:hover {
  background: var(--color-neutral-700);
}

.om-card__btn--primary {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: #fff;
}

.om-card__btn--primary:hover {
  background: var(--color-primary-darken-1);
}

.om-card-enter-active,
.om-card-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.om-card-enter-from,
.om-card-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

@media (max-width: 599px) {
  .om-legend {
    display: none;
  }

  /* Pas assez de place à côté de la recherche centrée sur un petit écran —
     la vue satellite reste accessible en agrandissant la fenêtre plutôt que
     de faire chevaucher les deux. */
  .om-layer-toggle {
    display: none;
  }

  .om-card {
    max-width: none;
  }
}
</style>
