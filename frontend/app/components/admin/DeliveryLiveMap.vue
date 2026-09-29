<script setup lang="ts">
/**
 * Vue « Carte » du suivi des livraisons (admin) : le trajet routier de chaque
 * livraison filtrée (couleur de son étape), la boutique de départ, la
 * destination et le livreur, dont la position arrive en direct pendant la
 * course (message WebSocket « courier_position », voir stores/notifications.ts).
 * Les filtres (étapes, alertes, recherche) sont ceux de la page.
 */
import type * as MapLibreGL from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import {
  PhArrowSquareOut,
  PhArrowsOut,
  PhClock,
  PhGlobeHemisphereWest,
  PhListBullets,
  PhMapTrifold,
  PhMotorcycle,
  PhPath,
  PhUser,
  PhWarningCircle,
  PhX,
} from '@phosphor-icons/vue'
import { createPin, type MapPinKind, type PinHandle } from '~/utils/mapPins'
import { MAP_DEFAULT_CENTER, MAP_DEFAULT_ZOOM, getMapStyle, getNavigationStyle } from '~/utils/mapStyle'
import type { DeliveryMonitorEntry } from '~/types/api'

interface MapRow {
  entry: DeliveryMonitorEntry
  stage: string
  late: boolean
  stale: boolean
}

const props = defineProps<{ rows: MapRow[]; stageMeta: Record<string, { label: string; color: string }> }>()

const notifications = useNotificationStore()
const { theme } = useAppTheme()

const mapContainer = ref<HTMLElement | null>(null)
const mapFailed = ref(false)
const layer = ref<'plan' | 'satellite'>('plan')
const selectedId = ref<string | null>(null)
const listOpen = ref(false)

let maplibregl: typeof MapLibreGL | null = null
let map: MapLibreGL.Map | null = null
const markers = new Map<string, { marker: MapLibreGL.Marker; pin: PinHandle }>()
let fitted = false

// Livraisons affichables (on écarte les livrées : plus rien à suivre).
const mapped = computed(() => props.rows.filter((r) => r.stage !== 'delivered'))

// Position la plus récente du livreur : message temps réel s'il est plus frais.
function courierPos(e: DeliveryMonitorEntry): { lat: number; lng: number } | null {
  const live = notifications.courierPositions[e.sub_order_id]
  if (live && (!e.courier_position_at || live.at > e.courier_position_at)) return { lat: live.latitude, lng: live.longitude }
  if (e.courier_live && e.courier_latitude != null && e.courier_longitude != null) {
    return { lat: e.courier_latitude, lng: e.courier_longitude }
  }
  return null
}

function hasDest(e: DeliveryMonitorEntry) {
  return e.destination_latitude != null && e.destination_longitude != null
}

function routeCoordinates(e: DeliveryMonitorEntry): [number, number][] | null {
  if (e.route?.coordinates?.length) return e.route.coordinates
  if (!hasDest(e)) return null
  const start = courierPos(e) ?? (e.origin_latitude != null ? { lat: e.origin_latitude, lng: e.origin_longitude! } : null)
  if (!start) return null
  return [
    [start.lng, start.lat],
    [e.destination_longitude!, e.destination_latitude!],
  ]
}

const routesGeoJson = computed(() => ({
  type: 'FeatureCollection' as const,
  features: mapped.value.flatMap((r) => {
    const coordinates = routeCoordinates(r.entry)
    if (!coordinates) return []
    return [
      {
        type: 'Feature' as const,
        properties: {
          id: r.entry.sub_order_id,
          color: props.stageMeta[r.stage]?.color ?? '#3d7bd9',
          // Trajet réel (route) vs repli à vol d'oiseau (pointillés).
          exact: r.entry.route ? 1 : 0,
          selected: r.entry.sub_order_id === selectedId.value ? 1 : 0,
          moving: r.stage === 'in_transit' ? 1 : 0,
        },
        geometry: { type: 'LineString' as const, coordinates },
      },
    ]
  }),
}))

// Copie brute (sans proxy réactif Vue) : MapLibre transmet les données à son
// worker par clonage structuré, qui refuse les proxys — le tracé serait
// ignoré sans erreur visible.
function plainRoutesGeoJson() {
  return JSON.parse(JSON.stringify(routesGeoJson.value))
}

function ensureRouteLayers() {
  if (!map || map.getSource('routes')) return
  map.addSource('routes', { type: 'geojson', data: plainRoutesGeoJson() })
  map.addLayer({
    id: 'routes-casing',
    type: 'line',
    source: 'routes',
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: {
      'line-color': '#ffffff',
      'line-width': ['case', ['==', ['get', 'selected'], 1], 11, 7],
      'line-opacity': 0.9,
    },
  })
  // Deux couches plutôt qu'un pointillé piloté par les données (non pris en
  // charge par MapLibre) : trajet routier exact en trait plein, repli à vol
  // d'oiseau en pointillés.
  const paint: MapLibreGL.LineLayerSpecification['paint'] = {
    'line-color': ['get', 'color'],
    'line-width': ['case', ['==', ['get', 'selected'], 1], 7, 4],
    'line-opacity': ['case', ['==', ['get', 'moving'], 1], 1, 0.75],
  }
  map.addLayer({
    id: 'routes-line',
    type: 'line',
    source: 'routes',
    filter: ['==', ['get', 'exact'], 1],
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { ...paint },
  })
  map.addLayer({
    id: 'routes-estimated',
    type: 'line',
    source: 'routes',
    filter: ['==', ['get', 'exact'], 0],
    layout: { 'line-cap': 'butt', 'line-join': 'round' },
    paint: { ...paint, 'line-dasharray': [2, 1.5] },
  })
  for (const layerId of ['routes-line', 'routes-estimated']) {
    map.on('click', layerId, (ev) => {
      const id = ev.features?.[0]?.properties?.id
      if (id) select(String(id), false)
    })
    map.on('mouseenter', layerId, () => map && (map.getCanvas().style.cursor = 'pointer'))
    map.on('mouseleave', layerId, () => map && (map.getCanvas().style.cursor = ''))
  }
}

function refreshRoutes() {
  const source = map?.getSource('routes') as MapLibreGL.GeoJSONSource | undefined
  source?.setData(plainRoutesGeoJson())
}

function addMarker(id: string, kind: MapPinKind, at: { lat: number; lng: number }, label: string, opts: { live?: boolean; small?: boolean; onClick?: () => void } = {}) {
  if (!maplibregl || !map) return
  const existing = markers.get(id)
  if (existing) {
    existing.marker.setLngLat([at.lng, at.lat])
    return
  }
  const pin = createPin(kind, { selected: false, muted: false, attention: false, label, live: opts.live, small: opts.small })
  if (opts.onClick) pin.el.addEventListener('click', (ev) => {
    ev.stopPropagation()
    opts.onClick!()
  })
  const marker = new maplibregl.Marker({ element: pin.el, anchor: 'bottom' }).setLngLat([at.lng, at.lat]).addTo(map)
  markers.set(id, { marker, pin })
}

function syncMarkers() {
  if (!map) return
  const wanted = new Set<string>()
  for (const r of mapped.value) {
    const e = r.entry
    if (e.origin_latitude != null && e.origin_longitude != null) {
      const id = `shop:${e.vendor_id}`
      wanted.add(id)
      addMarker(id, 'shop', { lat: e.origin_latitude, lng: e.origin_longitude }, e.shop_name, { small: true })
    }
    if (hasDest(e)) {
      const id =
        e.delivery_type === 'pickup_point'
          ? `pickup:${e.destination_latitude},${e.destination_longitude}`
          : `home:${e.order_id}`
      wanted.add(id)
      addMarker(id, e.delivery_type === 'pickup_point' ? 'pickup' : 'home', { lat: e.destination_latitude!, lng: e.destination_longitude! }, 'Destination', {
        onClick: () => select(e.sub_order_id, false),
      })
    }
    const pos = courierPos(e)
    if (pos) {
      const id = `courier:${e.sub_order_id}`
      wanted.add(id)
      addMarker(id, 'courier', pos, e.courier_name ?? 'Livreur', { live: true, onClick: () => select(e.sub_order_id, false) })
    }
  }
  for (const [id, { marker, pin }] of markers) {
    if (!wanted.has(id)) {
      marker.remove()
      pin.dispose()
      markers.delete(id)
    }
  }
}

function boundsOf(rows: MapRow[]) {
  if (!maplibregl) return null
  let bounds: MapLibreGL.LngLatBounds | null = null
  const extend = (lng: number, lat: number) => {
    bounds = bounds ? bounds.extend([lng, lat]) : new maplibregl!.LngLatBounds([lng, lat], [lng, lat])
  }
  for (const r of rows) {
    for (const [lng, lat] of routeCoordinates(r.entry) ?? []) extend(lng, lat)
    if (r.entry.origin_latitude != null) extend(r.entry.origin_longitude!, r.entry.origin_latitude)
  }
  return bounds
}

// Marge de cadrage : sur ordinateur, le panneau de liste couvre la gauche de la carte.
function mapPadding(base = 60) {
  const wide = (mapContainer.value?.clientWidth ?? 0) > 900
  return { top: base, bottom: base, right: base, left: wide ? 330 + base / 2 : base }
}

function fitAll(animate = true) {
  const bounds = boundsOf(mapped.value)
  if (bounds && map) map.fitBounds(bounds, { padding: mapPadding(), maxZoom: 15, duration: animate ? 600 : 0 })
}

const selected = computed(() => mapped.value.find((r) => r.entry.sub_order_id === selectedId.value) ?? null)

function select(id: string | null, focus = true) {
  selectedId.value = id
  listOpen.value = false
  refreshRoutes()
  if (focus && id) {
    const row = mapped.value.find((r) => r.entry.sub_order_id === id)
    const bounds = row ? boundsOf([row]) : null
    if (bounds && map) map.fitBounds(bounds, { padding: mapPadding(80), maxZoom: 16, duration: 600 })
  }
}

function styleFor() {
  return layer.value === 'satellite' ? getMapStyle(theme.value, 'satellite') : getNavigationStyle(theme.value)
}

function applyStyle() {
  if (!map) return
  map.setStyle(styleFor())
  // Les sources/couches des trajets sont réinstallées après chargement du style.
}

onMounted(async () => {
  maplibregl = await loadMapLibre()
  if (!mapContainer.value) return
  try {
    map = new maplibregl.Map({
      container: mapContainer.value,
      style: styleFor(),
      center: MAP_DEFAULT_CENTER,
      zoom: MAP_DEFAULT_ZOOM,
      attributionControl: { compact: true },
    })
  } catch {
    mapFailed.value = true
    return
  }
  map.addControl(new maplibregl.NavigationControl({ showCompass: true, visualizePitch: true }), 'bottom-right')
  map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left')
  map.on('style.load', () => {
    ensureRouteLayers()
    refreshRoutes()
    syncMarkers()
    if (!fitted) {
      map?.resize()
      fitAll(false)
      fitted = true
    }
  })
})

watch(
  () => [props.rows, notifications.courierPositions] as const,
  () => {
    refreshRoutes()
    syncMarkers()
  },
  { deep: false },
)
watch(selectedId, refreshRoutes)
watch([theme, layer], applyStyle)

onBeforeUnmount(() => {
  for (const { marker, pin } of markers.values()) {
    marker.remove()
    pin.dispose()
  }
  markers.clear()
  map?.remove()
  map = null
})

function shortId(id: string) {
  return `#GN-${id.slice(0, 5).toUpperCase()}`
}
function destinationLabel(e: DeliveryMonitorEntry) {
  if (e.delivery_type === 'pickup_point') return e.pickup_point_name ?? 'Point de retrait'
  return e.delivery_zone || e.delivery_address
}
const withoutPosition = computed(() => mapped.value.filter((r) => !hasDest(r.entry)).length)
</script>

<template>
  <div class="dlm">
    <div v-if="mapFailed" class="dlm__failed">Carte indisponible sur cet appareil.</div>
    <div v-else ref="mapContainer" class="dlm__map" role="application" aria-label="Carte des livraisons en cours" />

    <!-- Liste des livraisons (panneau sur ordinateur, tiroir sur téléphone) -->
    <aside class="dlm__panel" :class="{ 'dlm__panel--open': listOpen }">
      <header class="dlm__panel-head">
        <strong>{{ mapped.length }} livraison{{ mapped.length > 1 ? 's' : '' }}</strong>
        <span v-if="withoutPosition" class="dlm__muted">{{ withoutPosition }} sans position</span>
        <button type="button" class="dlm__close" aria-label="Fermer la liste" @click="listOpen = false"><PhX :size="16" /></button>
      </header>
      <p v-if="!mapped.length" class="dlm__empty">Aucune livraison en cours pour ce filtre.</p>
      <button
        v-for="r in mapped"
        :key="r.entry.sub_order_id"
        type="button"
        class="dlm-item"
        :class="{ 'is-selected': r.entry.sub_order_id === selectedId }"
        :style="{ '--stage': stageMeta[r.stage]?.color }"
        @click="select(r.entry.sub_order_id)"
      >
        <span class="dlm-item__top">
          <span class="dlm-item__id">{{ shortId(r.entry.order_id) }}</span>
          <span class="dlm-item__stage">
            <span v-if="courierPos(r.entry)" class="dlm-live" />
            {{ stageMeta[r.stage]?.label }}
          </span>
        </span>
        <span class="dlm-item__route">{{ r.entry.shop_name }} → {{ destinationLabel(r.entry) }}</span>
        <span class="dlm-item__meta">
          <span><PhMotorcycle :size="13" /> {{ r.entry.courier_name ?? 'Aucun livreur' }}</span>
          <span v-if="r.entry.route"><PhPath :size="13" /> {{ r.entry.route.distance_km.toString().replace('.', ',') }} km · {{ r.entry.route.duration_min }} min</span>
          <span v-if="r.late || r.stale" class="dlm-item__alert"><PhWarningCircle :size="13" weight="fill" /> À surveiller</span>
        </span>
      </button>
    </aside>

    <!-- Outils -->
    <div class="dlm__tools">
      <button type="button" class="dlm-tool dlm-tool--list" @click="listOpen = !listOpen">
        <PhListBullets :size="17" /> Liste ({{ mapped.length }})
      </button>
      <div class="dlm-seg" role="group" aria-label="Fond de carte">
        <button type="button" :class="{ 'is-active': layer === 'plan' }" @click="layer = 'plan'"><PhMapTrifold :size="16" /> Plan</button>
        <button type="button" :class="{ 'is-active': layer === 'satellite' }" @click="layer = 'satellite'"><PhGlobeHemisphereWest :size="16" /> Satellite</button>
      </div>
      <button type="button" class="dlm-tool" aria-label="Tout afficher" title="Tout afficher" @click="fitAll()"><PhArrowsOut :size="17" /></button>
    </div>

    <!-- Légende -->
    <div class="dlm__legend">
      <span v-for="(meta, key) in stageMeta" v-show="key !== 'delivered'" :key="key"><i :style="{ background: meta.color }" />{{ meta.label }}</span>
      <span><i class="dlm__legend-dash" />Trajet estimé</span>
    </div>

    <!-- Fiche de la livraison sélectionnée -->
    <transition name="dlm-pop">
      <div v-if="selected" class="dlm__card" :style="{ '--stage': stageMeta[selected.stage]?.color }">
        <button type="button" class="dlm__close" aria-label="Fermer" @click="select(null, false)"><PhX :size="16" /></button>
        <div class="dlm__card-top">
          <span class="dlm-item__id">{{ shortId(selected.entry.order_id) }}</span>
          <span class="dlm__stage-chip">{{ stageMeta[selected.stage]?.label }}</span>
        </div>
        <div class="dlm__card-route">
          <span><i class="dot dot--start" /> {{ selected.entry.shop_name }}</span>
          <span><i class="dot dot--end" /> {{ destinationLabel(selected.entry) }}</span>
        </div>
        <div class="dlm__card-facts">
          <span v-if="selected.entry.route"><PhPath :size="14" /> {{ selected.entry.route.distance_km.toString().replace('.', ',') }} km · ~{{ selected.entry.route.duration_min }} min {{ courierPos(selected.entry) ? 'restantes' : 'de trajet' }}</span>
          <span><PhMotorcycle :size="14" /> {{ selected.entry.courier_name ?? 'Aucun livreur' }}<template v-if="selected.entry.courier_phone"> · {{ selected.entry.courier_phone }}</template></span>
          <span><PhUser :size="14" /> {{ selected.entry.buyer_name ?? 'Client' }}<template v-if="selected.entry.buyer_phone"> · {{ selected.entry.buyer_phone }}</template></span>
          <span v-if="courierPos(selected.entry)" class="dlm__live-line"><span class="dlm-live" /> Position du livreur en direct</span>
          <span v-else-if="selected.stage === 'in_transit'" class="dlm__muted"><PhClock :size="14" /> Position du livreur non partagée pour l'instant</span>
        </div>
        <NuxtLink :to="`/admin/commandes/${selected.entry.order_id}`" class="dlm__open">
          Ouvrir la commande <PhArrowSquareOut :size="14" />
        </NuxtLink>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.dlm {
  position: relative;
  height: calc(100dvh - 250px);
  min-height: 480px;
  border-radius: var(--radius-lg);
  overflow: hidden;
  border: 1px solid var(--color-divider);
  background: var(--color-neutral-800);
}

.dlm__map {
  position: absolute;
  inset: 0;
}

.dlm__failed {
  padding: 48px 16px;
  text-align: center;
  color: var(--color-neutral-400);
}

/* --- Panneau liste --- */
.dlm__panel {
  position: absolute;
  top: 12px;
  left: 12px;
  bottom: 56px;
  z-index: 3;
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 300px;
  padding: 10px;
  overflow-y: auto;
  border-radius: var(--radius-lg);
  background: color-mix(in srgb, var(--color-neutral-900) 94%, transparent);
  backdrop-filter: blur(8px);
  box-shadow: var(--shadow-lg);
}

.dlm__panel-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 2px 4px 6px;
  font-size: 13px;
}

.dlm__panel-head .dlm__close {
  display: none;
  margin-left: auto;
}

.dlm__muted {
  font-size: 12px;
  color: var(--color-neutral-400);
}

.dlm__empty {
  margin: 8px 4px;
  font-size: 13px;
  color: var(--color-neutral-400);
}

.dlm-item {
  display: flex;
  flex-direction: column;
  gap: 3px;
  width: 100%;
  padding: 9px 10px 9px 12px;
  border: 1px solid var(--color-divider);
  border-left: 4px solid var(--stage);
  border-radius: var(--radius-md);
  background: var(--color-neutral-900);
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: box-shadow 0.15s ease;
}

.dlm-item:hover,
.dlm-item.is-selected {
  box-shadow: 0 0 0 2px var(--stage);
}

.dlm-item__top {
  display: flex;
  justify-content: space-between;
  gap: 6px;
}

.dlm-item__id {
  font-family: var(--font-heading);
  font-weight: 800;
  font-size: 13.5px;
  color: var(--color-primary-300);
}

.dlm-item__stage {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11.5px;
  font-weight: 700;
  color: var(--stage);
}

.dlm-item__route {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--color-neutral-200);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dlm-item__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  font-size: 11.5px;
  color: var(--color-neutral-400);
}

.dlm-item__meta span {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.dlm-item__alert {
  color: var(--color-error);
  font-weight: 700;
}

.dlm-live {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #e5484d;
  animation: dlm-blink 1.4s ease-in-out infinite;
}

@keyframes dlm-blink {
  50% {
    opacity: 0.25;
  }
}

/* --- Outils --- */
.dlm__tools {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 3;
  display: flex;
  gap: 8px;
}

.dlm-tool,
.dlm-seg {
  display: flex;
  align-items: center;
  border-radius: 999px;
  background: var(--color-neutral-900);
  box-shadow: var(--shadow-md);
}

.dlm-tool {
  gap: 6px;
  height: 38px;
  min-width: 38px;
  justify-content: center;
  padding: 0 12px;
  border: 0;
  color: var(--color-neutral-300);
  font: inherit;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}

.dlm-tool--list {
  display: none;
}

.dlm-seg {
  padding: 3px;
}

.dlm-seg button {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 11px;
  border: 0;
  border-radius: 999px;
  background: none;
  color: var(--color-neutral-400);
  font: inherit;
  font-size: 12.5px;
  font-weight: 700;
  cursor: pointer;
}

.dlm-seg button.is-active {
  background: var(--color-primary);
  color: #fff;
}

/* --- Légende --- */
.dlm__legend {
  position: absolute;
  left: 324px;
  bottom: 12px;
  z-index: 2;
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  max-width: calc(100% - 440px);
  padding: 7px 12px;
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--color-neutral-900) 92%, transparent);
  box-shadow: var(--shadow-sm);
  font-size: 11.5px;
  color: var(--color-neutral-300);
}

.dlm__legend span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.dlm__legend i {
  display: inline-block;
  width: 16px;
  height: 4px;
  border-radius: 4px;
}

.dlm__legend-dash {
  background: repeating-linear-gradient(90deg, var(--color-neutral-400) 0 4px, transparent 4px 7px);
}

/* --- Fiche sélection --- */
.dlm__card {
  position: absolute;
  top: 62px;
  right: 12px;
  z-index: 4;
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 320px;
  padding: 14px;
  border-radius: var(--radius-lg);
  border-top: 4px solid var(--stage);
  background: var(--color-neutral-900);
  box-shadow: var(--shadow-lg);
}

.dlm__card .dlm__close {
  position: absolute;
  top: 8px;
  right: 8px;
}

.dlm__close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: 0;
  border-radius: 50%;
  background: var(--color-neutral-800);
  color: var(--color-neutral-300);
  cursor: pointer;
}

.dlm__card-top {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dlm__stage-chip {
  padding: 2px 9px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--stage) 16%, transparent);
  color: var(--stage);
  font-size: 11.5px;
  font-weight: 800;
}

.dlm__card-route {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  font-weight: 600;
}

.dlm__card-route span {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dot {
  width: 10px;
  height: 10px;
  flex-shrink: 0;
  border-radius: 50%;
}

.dot--start {
  background: #7c3aed;
}

.dot--end {
  background: #db2777;
}

.dlm__card-facts {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12.5px;
  color: var(--color-neutral-400);
}

.dlm__card-facts span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.dlm__live-line {
  color: #e5484d;
  font-weight: 700;
}

.dlm__open {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  background: var(--color-primary);
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  text-decoration: none;
}

.dlm-pop-enter-active,
.dlm-pop-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.dlm-pop-enter-from,
.dlm-pop-leave-to {
  opacity: 0;
  transform: translateY(6px);
}

/* --- Tablette et téléphone : la liste devient un tiroir, la fiche passe en bas --- */
@media (max-width: 900px) {
  .dlm {
    height: calc(100dvh - 300px);
    min-height: 420px;
  }

  .dlm__panel {
    top: auto;
    left: 0;
    right: 0;
    bottom: 0;
    width: auto;
    max-height: 60%;
    border-radius: var(--radius-lg) var(--radius-lg) 0 0;
    transform: translateY(105%);
    transition: transform 0.25s ease;
  }

  .dlm__panel--open {
    transform: none;
  }

  .dlm__panel-head .dlm__close {
    display: flex;
  }

  .dlm-tool--list {
    display: flex;
  }

  .dlm__tools {
    left: 12px;
    flex-wrap: wrap;
  }

  .dlm__legend {
    display: none;
  }

  .dlm__card {
    top: auto;
    left: 12px;
    right: 12px;
    bottom: 12px;
    width: auto;
  }
}
</style>
