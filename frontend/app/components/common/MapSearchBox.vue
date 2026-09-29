<script setup lang="ts">
/**
 * Barre de recherche de lieu par nom (geocoding) — utilisée au-dessus de
 * n'importe quelle carte MapLibre pour y naviguer rapidement, plutôt que de
 * devoir zoomer/glisser manuellement jusqu'au bon quartier.
 *
 * Nominatim (OpenStreetMap) : gratuit, sans clé, même logique open-source
 * que les tuiles. Sa politique d'usage déconseille l'auto-complétion
 * déclenchée à chaque frappe — on attend donc une pause de frappe (600ms) ET
 * au moins 3 caractères avant d'interroger, ce qui reste réactif pour
 * l'utilisateur sans bombarder le service public à chaque touche.
 */
import { PhMagnifyingGlass, PhSpinner } from '@phosphor-icons/vue'

export interface LocalSearchResult {
  id: string
  label: string
  sub: string | null
  color: string
  lat: number
  lng: number
}

// localSearch : résultats Netmarket (boutiques, points, livreurs…) affichés
// tout de suite, avant les lieux trouvés par Nominatim.
const props = withDefaults(defineProps<{ localSearch?: (q: string) => LocalSearchResult[]; placeholder?: string }>(), {
  localSearch: undefined,
  placeholder: 'Rechercher un quartier, un lieu...',
})
const emit = defineEmits<{ select: [value: { label: string; lat: number; lng: number; id?: string }] }>()

interface NominatimResult {
  display_name: string
  lat: string
  lon: string
}

const query = ref('')
const localResults = computed(() => {
  const text = query.value.trim()
  if (!props.localSearch || text.length < 2) return []
  return props.localSearch(text).slice(0, 6)
})
const results = ref<NominatimResult[]>([])
const loading = ref(false)
const open = ref(false)
const root = ref<HTMLElement | null>(null)

let debounceTimer: ReturnType<typeof setTimeout> | undefined
let requestId = 0

async function runSearch(text: string) {
  const currentRequestId = ++requestId
  loading.value = true
  try {
    const data = await $fetch<NominatimResult[]>('https://nominatim.openstreetmap.org/search', {
      params: { format: 'jsonv2', q: text, limit: 5, countrycodes: 'gn' },
    })
    // Ignore une réponse arrivée après une frappe plus récente — sinon un
    // résultat lent pour "Cona" pourrait remplacer celui, déjà arrivé, de
    // "Conakry" tapé juste après.
    if (currentRequestId !== requestId) return
    results.value = data
    open.value = true
  } catch {
    if (currentRequestId !== requestId) return
    results.value = []
  } finally {
    if (currentRequestId === requestId) loading.value = false
  }
}

watch(query, (text) => {
  clearTimeout(debounceTimer)
  open.value = localResults.value.length > 0
  if (text.trim().length < 3) {
    results.value = []
    return
  }
  debounceTimer = setTimeout(() => runSearch(text.trim()), 600)
})

function pick(result: NominatimResult) {
  query.value = result.display_name
  open.value = false
  results.value = []
  emit('select', { label: result.display_name, lat: Number(result.lat), lng: Number(result.lon) })
}

function pickLocal(result: LocalSearchResult) {
  query.value = result.label
  open.value = false
  emit('select', { label: result.label, lat: result.lat, lng: result.lng, id: result.id })
}

function onClickOutside(event: MouseEvent) {
  if (root.value && !root.value.contains(event.target as Node)) open.value = false
}

onMounted(() => document.addEventListener('mousedown', onClickOutside))
onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onClickOutside)
  clearTimeout(debounceTimer)
})
</script>

<template>
  <div ref="root" class="map-search">
    <div class="map-search__field">
      <PhMagnifyingGlass :size="16" class="map-search__icon" />
      <input
        v-model="query"
        type="text"
        :placeholder="placeholder"
        class="map-search__input"
        @focus="open = results.length > 0 || localResults.length > 0"
      />
      <PhSpinner v-if="loading" :size="14" class="map-search__spinner" />
    </div>
    <div v-if="open && (localResults.length || results.length)" class="map-search__results">
      <template v-if="localResults.length">
        <div class="map-search__section">Sur Netmarket</div>
        <button
          v-for="r in localResults"
          :key="r.id"
          type="button"
          class="map-search__local"
          @mousedown.prevent="pickLocal(r)"
        >
          <span class="map-search__dot" :style="{ background: r.color }" />
          <span class="map-search__local-text">
            <strong>{{ r.label }}</strong>
            <span v-if="r.sub">{{ r.sub }}</span>
          </span>
        </button>
      </template>
      <template v-if="results.length">
        <div class="map-search__section">Lieux</div>
        <ul class="map-search__places">
          <li v-for="result in results" :key="result.display_name" @mousedown.prevent="pick(result)">
            {{ result.display_name }}
          </li>
        </ul>
      </template>
    </div>
    <div v-else-if="open && !loading && query.trim().length >= 3" class="map-search__results map-search__results--empty">
      Aucun résultat.
    </div>
  </div>
</template>

<style scoped>
.map-search {
  position: relative;
  width: 100%;
}

.map-search__field {
  display: flex;
  align-items: center;
  gap: 6px;
  /* var() plutôt qu'un rgba(...) fixe : ce composant flotte au-dessus de la
     carte dans les deux thèmes, il doit donc suivre --color-neutral-900
     (blanc en clair, quasi-noir en sombre) comme le reste de l'UI plutôt que
     de rester figé en sombre. */
  background: var(--color-neutral-900);
  backdrop-filter: blur(6px);
  border: 1px solid var(--color-divider-strong);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  padding: 8px 12px;
}

.map-search__icon {
  color: var(--color-neutral-400);
  flex-shrink: 0;
}

.map-search__input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: var(--color-neutral-200);
  font-size: 13px;
  min-width: 0;
}

.map-search__input::placeholder {
  color: var(--color-neutral-500);
}

.map-search__spinner {
  color: var(--color-primary);
  flex-shrink: 0;
  animation: map-search-spin 0.8s linear infinite;
}

@keyframes map-search-spin {
  to {
    transform: rotate(360deg);
  }
}

.map-search__results {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  right: 0;
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider-strong);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  max-height: 360px;
  overflow-y: auto;
  list-style: none;
  margin: 0;
  padding: 4px;
  z-index: 5;
}

.map-search__results li {
  padding: 8px 10px;
  font-size: 12.5px;
  color: var(--color-neutral-300);
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.map-search__results li:hover {
  background: var(--color-neutral-800);
  color: var(--color-neutral-200);
}

.map-search__results--empty {
  padding: 10px;
  font-size: 12px;
  color: var(--color-neutral-500);
}

.map-search__section {
  padding: 8px 12px 4px;
  font-size: 10.5px;
  font-weight: 800;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-neutral-500);
}

.map-search__local {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 12px;
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.map-search__local:hover {
  background: var(--color-neutral-800);
}

.map-search__dot {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
  border-radius: 50%;
  box-shadow: 0 0 0 3px var(--color-neutral-900), 0 0 0 4px var(--color-divider-strong);
}

.map-search__local-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  font-size: 13px;
}

.map-search__local-text span {
  font-size: 12px;
  color: var(--color-neutral-400);
}

.map-search__places {
  margin: 0;
  padding: 0;
  list-style: none;
}
</style>
