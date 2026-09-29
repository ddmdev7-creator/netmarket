<script setup lang="ts">
/**
 * Carte de suivi en direct d'un colis en route : boutique de départ,
 * destination (domicile ou point de retrait) et livreur, dont la position
 * arrive en temps réel (message WebSocket « courier_position », voir
 * stores/notifications.ts) avec une relecture périodique en secours.
 */
import type * as MapLibreGL from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { PhClock, PhMapPin, PhMotorcycle } from '@phosphor-icons/vue'
import { createPin, type MapPinKind, type PinHandle } from '~/utils/mapPins'
import { MAP_DEFAULT_CENTER, MAP_DEFAULT_ZOOM, getNavigationStyle } from '~/utils/mapStyle'
import type { SubOrderTrackingRead } from '~/types/api'

const props = defineProps<{ subOrderId: string }>()

const { apiFetch } = useApi()
const notifications = useNotificationStore()
const { theme } = useAppTheme()

const tracking = ref<SubOrderTrackingRead | null>(null)
const mapContainer = ref<HTMLElement | null>(null)
const mapFailed = ref(false)
const now = ref(Date.now())

let maplibregl: typeof MapLibreGL | null = null
let map: MapLibreGL.Map | null = null
let courierMarker: MapLibreGL.Marker | null = null
let courierPin: PinHandle | null = null
const staticPins: PinHandle[] = []
let fitted = false

let lastLoad = 0
async function load() {
  lastLoad = Date.now()
  try {
    tracking.value = await apiFetch<SubOrderTrackingRead>(`/orders/sub-orders/${props.subOrderId}/tracking`)
  } catch {
    // Carte masquée tant que le suivi n'est pas disponible.
  }
}

// --- Trajet routier ------------------------------------------------------------

const routeGeoJson = computed(() => {
  const coords = tracking.value?.route?.coordinates
  return {
    type: 'FeatureCollection' as const,
    features: coords?.length
      ? [{ type: 'Feature' as const, properties: {}, geometry: { type: 'LineString' as const, coordinates: coords } }]
      : [],
  }
})

// Copie brute (sans proxy réactif Vue) : MapLibre transmet les données à son
// worker par clonage structuré, qui refuse les proxys — le tracé serait
// ignoré sans erreur visible.
function plainRouteGeoJson() {
  return JSON.parse(JSON.stringify(routeGeoJson.value))
}

function ensureRouteLayer() {
  if (!map || map.getSource('route')) return
  map.addSource('route', { type: 'geojson', data: plainRouteGeoJson() })
  map.addLayer({
    id: 'route-casing',
    type: 'line',
    source: 'route',
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': '#ffffff', 'line-width': 9, 'line-opacity': 0.95 },
  })
  map.addLayer({
    id: 'route-line',
    type: 'line',
    source: 'route',
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': '#0a66f5', 'line-width': 5 },
  })
}

function refreshRoute() {
  const source = map?.getSource('route') as MapLibreGL.GeoJSONSource | undefined
  source?.setData(plainRouteGeoJson())
}

// Position la plus récente : message temps réel s'il est plus frais que la dernière lecture.
const courier = computed(() => {
  const live = notifications.courierPositions[props.subOrderId]
  const t = tracking.value
  const fromApi =
    t?.courier_latitude != null && t.courier_longitude != null && t.courier_position_at
      ? { latitude: t.courier_latitude, longitude: t.courier_longitude, at: t.courier_position_at }
      : null
  if (live && (!fromApi || live.at > fromApi.at)) return live
  return fromApi
})

const destination = computed(() =>
  tracking.value?.destination_latitude != null && tracking.value.destination_longitude != null
    ? { lat: tracking.value.destination_latitude, lng: tracking.value.destination_longitude }
    : null,
)
const origin = computed(() =>
  tracking.value?.origin_latitude != null && tracking.value.origin_longitude != null
    ? { lat: tracking.value.origin_latitude, lng: tracking.value.origin_longitude }
    : null,
)

// Distance et arrivée recalculées côté client à chaque nouvelle position.
function haversineKm(a: { lat: number; lng: number }, b: { lat: number; lng: number }) {
  const rad = Math.PI / 180
  const dLat = (b.lat - a.lat) * rad
  const dLng = (b.lng - a.lng) * rad
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLng / 2) ** 2
  return 6371 * 2 * Math.asin(Math.sqrt(h))
}
// Distance et durée par la route quand le trajet est connu, sinon à vol d'oiseau.
const distanceKm = computed(() => {
  if (!courier.value || !destination.value) return null
  if (tracking.value?.route && tracking.value.courier_latitude != null) return tracking.value.route.distance_km
  return haversineKm({ lat: courier.value.latitude, lng: courier.value.longitude }, destination.value)
})
const etaMinutes = computed(() => {
  if (distanceKm.value === null) return null
  if (tracking.value?.route && tracking.value.courier_latitude != null) return tracking.value.eta_minutes
  return Math.max(2, Math.round((distanceKm.value / 18) * 60))
})
const secondsAgo = computed(() => (courier.value ? Math.max(0, Math.round((now.value - Date.parse(courier.value.at)) / 1000)) : null))
const agoLabel = computed(() => {
  const s = secondsAgo.value
  if (s === null) return ''
  if (s < 60) return "à l'instant"
  return `il y a ${Math.round(s / 60)} min`
})

function fitAll() {
  if (!maplibregl || !map) return
  const points: [number, number][] = []
  if (origin.value) points.push([origin.value.lng, origin.value.lat])
  if (destination.value) points.push([destination.value.lng, destination.value.lat])
  if (courier.value) points.push([courier.value.longitude, courier.value.latitude])
  for (const c of tracking.value?.route?.coordinates ?? []) points.push(c)
  if (!points.length) return
  const bounds = new maplibregl.LngLatBounds(points[0], points[0])
  for (const p of points) bounds.extend(p)
  map.fitBounds(bounds, { padding: 50, maxZoom: 15, duration: fitted ? 600 : 0 })
  fitted = true
}

function placeStatic() {
  if (!maplibregl || !map) return
  for (const pin of staticPins.splice(0)) pin.dispose()
  const add = (kind: MapPinKind, at: { lat: number; lng: number }, label: string) => {
    const pin = createPin(kind, { selected: false, muted: false, attention: false, label, small: kind === 'shop' })
    new maplibregl!.Marker({ element: pin.el, anchor: 'bottom' }).setLngLat([at.lng, at.lat]).addTo(map!)
    staticPins.push(pin)
  }
  if (origin.value) add('shop', origin.value, 'Boutique')
  if (destination.value) {
    add(tracking.value?.delivery_type === 'pickup_point' ? 'pickup' : 'home', destination.value, 'Destination')
  }
}

function placeCourier() {
  if (!maplibregl || !map || !courier.value) return
  const at: [number, number] = [courier.value.longitude, courier.value.latitude]
  if (!courierMarker) {
    courierPin = createPin('courier', { selected: false, muted: false, attention: false, label: 'Livreur', live: true })
    courierMarker = new maplibregl.Marker({ element: courierPin.el, anchor: 'bottom' }).setLngLat(at).addTo(map)
    fitAll()
  } else {
    courierMarker.setLngLat(at)
  }
}

let poller: ReturnType<typeof setInterval> | undefined
let ticker: ReturnType<typeof setInterval> | undefined

onMounted(async () => {
  await load()
  poller = setInterval(() => {
    if (!document.hidden) load()
  }, 30_000)
  ticker = setInterval(() => (now.value = Date.now()), 15_000)

  maplibregl = await loadMapLibre()
  if (!mapContainer.value) return
  try {
    map = new maplibregl.Map({
      container: mapContainer.value,
      style: getNavigationStyle(theme.value),
      center: MAP_DEFAULT_CENTER,
      zoom: MAP_DEFAULT_ZOOM,
      attributionControl: { compact: true },
      cooperativeGestures: true,
    })
  } catch {
    mapFailed.value = true
    return
  }
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right')
  map.on('style.load', () => {
    ensureRouteLayer()
    refreshRoute()
  })
  map.once('load', () => map?.resize())
  placeStatic()
  placeCourier()
  fitAll()
})

watch(courier, (value, previous) => {
  placeCourier()
  // Le livreur a bougé : trajet recalculé (au plus toutes les 20 s).
  if (value && previous && value.at !== previous.at && Date.now() - lastLoad > 20_000) load()
})
watch(routeGeoJson, () => {
  refreshRoute()
  if (!fitted) fitAll()
})
watch([origin, destination], () => {
  placeStatic()
  fitAll()
})
watch(theme, (value) => map?.setStyle(getNavigationStyle(value)))

onBeforeUnmount(() => {
  clearInterval(poller)
  clearInterval(ticker)
  for (const pin of staticPins) pin.dispose()
  courierPin?.dispose()
  map?.remove()
  map = null
})
</script>

<template>
  <div class="live">
    <div class="live__bar">
      <span class="live__badge" :class="{ 'live__badge--on': courier }">
        <span class="live__dot" />
        {{ courier ? 'En direct' : 'En attente de position' }}
      </span>
      <span v-if="courier && etaMinutes !== null" class="live__eta">
        <PhClock :size="14" weight="bold" /> Arrivée estimée ~{{ etaMinutes }} min
      </span>
    </div>

    <div v-if="mapFailed" class="live__failed">Carte indisponible sur cet appareil.</div>
    <div v-else ref="mapContainer" class="live__map" role="img" aria-label="Carte du trajet du livreur" />

    <div class="live__foot">
      <template v-if="courier">
        <span>
          <PhMotorcycle :size="14" /> Livreur à {{ distanceKm!.toFixed(1).replace('.', ',') }} km
          <template v-if="tracking?.route && tracking.courier_latitude != null"> par la route</template>
        </span>
        <span class="live__ago">Mis à jour {{ agoLabel }}</span>
      </template>
      <span v-else>
        <PhMapPin :size="14" />
        <template v-if="tracking?.route">Trajet prévu : {{ tracking.route.distance_km.toString().replace('.', ',') }} km depuis la boutique. </template>
        La position du livreur apparaîtra dès qu'il ouvrira son application.
      </span>
    </div>
  </div>
</template>

<style scoped>
.live {
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-md);
  overflow: hidden;
  background: var(--color-neutral-900);
}

.live__bar,
.live__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 12px;
  font-size: 12.5px;
  color: var(--color-neutral-400);
}

.live__foot span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.live__badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--color-neutral-800);
  font-weight: 700;
  font-size: 11.5px;
}

.live__badge--on {
  background: hsl(355 80% var(--tint-bg));
  color: hsl(355 65% var(--tint-fg));
}

.live__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-neutral-500);
}

.live__badge--on .live__dot {
  background: #e5484d;
  animation: live-blink 1.4s ease-in-out infinite;
}

@keyframes live-blink {
  50% {
    opacity: 0.25;
  }
}

.live__eta {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-weight: 800;
  color: var(--color-success);
}

.live__map {
  height: 260px;
}

@media (min-width: 960px) {
  .live__map {
    height: 340px;
  }
}

.live__failed {
  padding: 24px 12px;
  text-align: center;
  font-size: 13px;
  color: var(--color-neutral-400);
}

.live__ago {
  color: var(--color-neutral-500);
}
</style>
