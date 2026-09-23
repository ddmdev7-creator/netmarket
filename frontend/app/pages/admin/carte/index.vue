<script setup lang="ts">
import { PhMagnifyingGlass, PhMapPinLine, PhWarningCircle } from '@phosphor-icons/vue'
import type { OverviewMapItem } from '~/components/admin/OverviewMap.vue'
import { MAP_PIN_META, type MapPinKind } from '~/utils/mapPins'
import type { PickupPointRead, VendorRead, VendorStatus } from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const { apiFetch } = useApi()

const { data: vendors, pending: vendorsPending } = await useAsyncData(
  'admin-map-vendors',
  () => apiFetch<VendorRead[]>('/admin/vendors'),
  { default: () => [], getCachedData: hydrateThenRefetch },
)
const { data: points, pending: pointsPending } = await useAsyncData(
  'admin-map-pickup-points',
  () => apiFetch<PickupPointRead[]>('/admin/pickup-points'),
  { default: () => [], getCachedData: hydrateThenRefetch },
)
const loading = computed(() => vendorsPending.value || pointsPending.value)

const vendorStatusMeta: Record<VendorStatus, { label: string; tone: OverviewMapItem['statusTone']; muted: boolean }> = {
  approved: { label: 'Approuvée', tone: 'success', muted: false },
  pending: { label: 'En attente de validation', tone: 'warning', muted: false },
  rejected: { label: 'Rejetée', tone: 'error', muted: true },
  suspended: { label: 'Suspendue', tone: 'error', muted: true },
}

const hasPosition = (entity: { latitude: number | null; longitude: number | null }) =>
  entity.latitude !== null && entity.longitude !== null

// --- Construction des éléments de la carte -----------------------------------

/**
 * Une boutique qui EST aussi un point de retrait (PickupPoint.vendor_id) ne
 * donne qu'UN repère « boutique + point de retrait » : sinon deux repères
 * s'empileraient au même endroit. Une boutique sans position ne peut pas
 * porter ce repère — son point de retrait, s'il a une position, s'affiche
 * alors seul.
 */
interface Built {
  /** Positionnés sur la carte. */
  placed: (OverviewMapItem & { search: string; vendorStatus: VendorStatus | null })[]
  /** À corriger : pas de position, donc invisibles sur la carte. */
  unplaced: { id: string; kind: MapPinKind; name: string; subtitle: string | null; href: string }[]
}

const built = computed<Built>(() => {
  const placed: Built['placed'] = []
  const unplaced: Built['unplaced'] = []

  const vendorsWithPosition = new Set(vendors.value.filter(hasPosition).map((v) => v.id))
  const pointsByVendor = new Map<string, PickupPointRead[]>()
  for (const point of points.value) {
    if (point.vendor_id && vendorsWithPosition.has(point.vendor_id)) {
      pointsByVendor.set(point.vendor_id, [...(pointsByVendor.get(point.vendor_id) ?? []), point])
    }
  }
  const mergedPointIds = new Set([...pointsByVendor.values()].flat().map((p) => p.id))

  for (const vendor of vendors.value) {
    const meta = vendorStatusMeta[vendor.status]
    if (!hasPosition(vendor)) {
      unplaced.push({
        id: `shop:${vendor.id}`,
        kind: 'shop',
        name: vendor.shop_name,
        subtitle: vendor.zone,
        href: '/admin/vendeurs',
      })
      continue
    }
    const linkedPoints = pointsByVendor.get(vendor.id) ?? []
    const details = [
      { label: 'Propriétaire', value: vendor.owner_full_name || vendor.owner_phone || '—' },
      ...(vendor.owner_full_name && vendor.owner_phone ? [{ label: 'Téléphone', value: vendor.owner_phone }] : []),
      { label: 'Commission', value: `${vendor.commission_rate} %` },
      { label: 'Préparation', value: `${vendor.preparation_days} jour${vendor.preparation_days > 1 ? 's' : ''}` },
      ...linkedPoints.map((p) => ({
        label: 'Point de retrait',
        value: `${p.name} (${p.is_active ? 'actif' : 'inactif'})`,
      })),
    ]
    placed.push({
      id: `shop:${vendor.id}`,
      kind: linkedPoints.length ? 'shop_pickup' : 'shop',
      name: vendor.shop_name,
      subtitle: vendor.zone,
      lat: vendor.latitude!,
      lng: vendor.longitude!,
      muted: meta.muted,
      attention: vendor.status === 'pending',
      statusLabel: meta.label,
      statusTone: meta.tone,
      details,
      href: '/admin/vendeurs',
      hrefLabel: 'Voir les vendeurs',
      vendorStatus: vendor.status,
      search: [vendor.shop_name, vendor.zone, vendor.owner_full_name, vendor.owner_phone, ...linkedPoints.map((p) => p.name)]
        .filter(Boolean)
        .join(' '),
    })
  }

  for (const point of points.value) {
    if (mergedPointIds.has(point.id)) continue
    if (!hasPosition(point)) {
      unplaced.push({
        id: `pickup:${point.id}`,
        kind: 'pickup',
        name: point.name,
        subtitle: point.zone,
        href: '/admin/points-retrait',
      })
      continue
    }
    placed.push({
      id: `pickup:${point.id}`,
      kind: 'pickup',
      name: point.name,
      subtitle: point.zone,
      lat: point.latitude!,
      lng: point.longitude!,
      muted: !point.is_active,
      statusLabel: point.is_active ? 'Actif' : 'Inactif',
      statusTone: point.is_active ? 'success' : 'neutral',
      details: point.vendor_shop_name ? [{ label: 'Boutique liée', value: point.vendor_shop_name }] : [],
      href: '/admin/points-retrait',
      hrefLabel: 'Voir les points de retrait',
      vendorStatus: null,
      search: [point.name, point.zone, point.vendor_shop_name].filter(Boolean).join(' '),
    })
  }

  return { placed, unplaced }
})

// --- Filtres -----------------------------------------------------------------

function normalize(text: string): string {
  return text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().trim()
}

const kinds: MapPinKind[] = ['shop', 'pickup', 'shop_pickup']
const activeKinds = ref<Set<MapPinKind>>(new Set(kinds))
const statusFilter = ref<VendorStatus | 'all'>('all')
const statusOptions = [
  { title: 'Toutes les boutiques', value: 'all' },
  { title: 'Approuvées', value: 'approved' },
  { title: 'En attente', value: 'pending' },
  { title: 'Rejetées', value: 'rejected' },
  { title: 'Suspendues', value: 'suspended' },
]
const search = ref('')

function toggleKind(kind: MapPinKind) {
  const next = new Set(activeKinds.value)
  if (next.has(kind)) next.delete(kind)
  else next.add(kind)
  activeKinds.value = next
}

const countByKind = computed(() => {
  const counts: Record<MapPinKind, number> = { shop: 0, pickup: 0, shop_pickup: 0 }
  for (const item of built.value.placed) counts[item.kind]++
  return counts
})

const filtered = computed(() => {
  const term = normalize(search.value)
  return built.value.placed
    .filter((item) => activeKinds.value.has(item.kind))
    .filter((item) => statusFilter.value === 'all' || item.vendorStatus === null || item.vendorStatus === statusFilter.value)
    .filter((item) => !term || normalize(item.search).includes(term))
    .sort((a, b) => a.name.localeCompare(b.name, 'fr'))
})

// --- Sélection ---------------------------------------------------------------

const selectedId = ref<string | null>(null)
// Un filtre qui écarte l'élément sélectionné referme sa fiche.
watch(filtered, (list) => {
  if (selectedId.value && !list.some((item) => item.id === selectedId.value)) selectedId.value = null
})

const showUnplaced = ref(false)
</script>

<template>
  <div class="dashboard-shell">
    <div class="carte-header">
      <div>
        <h1 class="text-h6">Carte</h1>
        <p class="text-muted carte-header__sub">Boutiques et points de retrait de la plateforme.</p>
      </div>
      <div class="carte-stats">
        <span class="carte-stat"><strong>{{ countByKind.shop + countByKind.shop_pickup }}</strong> boutique{{ countByKind.shop + countByKind.shop_pickup > 1 ? 's' : '' }}</span>
        <span class="carte-stat"><strong>{{ countByKind.pickup + countByKind.shop_pickup }}</strong> point{{ countByKind.pickup + countByKind.shop_pickup > 1 ? 's' : '' }} de retrait</span>
        <span v-if="built.unplaced.length" class="carte-stat carte-stat--warn">
          <PhWarningCircle :size="14" weight="fill" /> <strong>{{ built.unplaced.length }}</strong> sans position
        </span>
      </div>
    </div>

    <div class="carte-layout">
      <section class="carte-panel" aria-label="Filtres et liste">
        <div class="carte-search">
          <PhMagnifyingGlass :size="16" class="carte-search__icon" />
          <input
            v-model="search"
            type="search"
            class="carte-search__input"
            placeholder="Nom, zone, propriétaire…"
            aria-label="Rechercher une boutique ou un point de retrait"
          />
        </div>

        <div class="carte-kinds" role="group" aria-label="Types affichés">
          <button
            v-for="kind in kinds"
            :key="kind"
            type="button"
            class="carte-kind"
            :class="{ 'carte-kind--off': !activeKinds.has(kind) }"
            :aria-pressed="activeKinds.has(kind)"
            @click="toggleKind(kind)"
          >
            <span class="carte-kind__dot" :style="{ background: MAP_PIN_META[kind].color }">
              <component :is="MAP_PIN_META[kind].icon" :size="10" weight="fill" color="#fff" />
            </span>
            {{ MAP_PIN_META[kind].label }}
            <span class="carte-kind__count">{{ countByKind[kind] }}</span>
          </button>
        </div>

        <v-select
          v-model="statusFilter"
          :items="statusOptions"
          density="compact"
          hide-details
          aria-label="Statut des boutiques"
          class="carte-status"
        />

        <div class="carte-list" role="list">
          <div v-if="loading" class="carte-list__note">Chargement…</div>
          <div v-else-if="filtered.length === 0" class="carte-list__note">Aucun résultat.</div>
          <button
            v-for="item in filtered"
            :key="item.id"
            type="button"
            role="listitem"
            class="carte-item"
            :class="{ 'carte-item--selected': item.id === selectedId }"
            @click="selectedId = item.id"
          >
            <span class="carte-item__pin" :style="{ background: item.muted ? '#8b8d97' : MAP_PIN_META[item.kind].color }">
              <component :is="MAP_PIN_META[item.kind].icon" :size="14" weight="fill" color="#fff" />
            </span>
            <span class="carte-item__text">
              <span class="carte-item__name">{{ item.name }}</span>
              <span class="carte-item__sub">{{ item.subtitle || MAP_PIN_META[item.kind].label }}</span>
            </span>
            <span v-if="item.statusLabel" class="carte-item__status" :class="`carte-item__status--${item.statusTone}`">
              {{ item.statusLabel === 'En attente de validation' ? 'En attente' : item.statusLabel }}
            </span>
          </button>
        </div>

        <div v-if="built.unplaced.length" class="carte-unplaced">
          <button type="button" class="carte-unplaced__toggle" :aria-expanded="showUnplaced" @click="showUnplaced = !showUnplaced">
            <PhMapPinLine :size="16" />
            {{ built.unplaced.length }} sans position GPS
            <span class="carte-unplaced__chevron">{{ showUnplaced ? '−' : '+' }}</span>
          </button>
          <ul v-if="showUnplaced" class="carte-unplaced__list">
            <li v-for="entry in built.unplaced" :key="entry.id">
              <NuxtLink :to="entry.href">
                <span class="carte-unplaced__kind">{{ MAP_PIN_META[entry.kind].label }}</span>
                {{ entry.name }}
              </NuxtLink>
            </li>
          </ul>
          <p v-if="showUnplaced" class="carte-unplaced__hint">
            Sans position, une boutique est facturée au tarif de livraison le plus élevé.
          </p>
        </div>
      </section>

      <section class="carte-map">
        <AdminOverviewMap :items="filtered" :selected-id="selectedId" @select="selectedId = $event" />
      </section>
    </div>
  </div>
</template>

<style scoped>
.carte-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.carte-header__sub {
  margin: 2px 0 0;
  font-size: 12.5px;
}

.carte-stats {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.carte-stat {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 11px;
  font-size: 12.5px;
  color: var(--color-neutral-300);
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider);
  border-radius: 999px;
}

.carte-stat--warn {
  color: #b3651a;
  border-color: rgba(224, 130, 46, 0.4);
  background: rgba(224, 130, 46, 0.1);
}

.carte-layout {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.carte-map {
  order: -1;
  height: 62dvh;
  min-height: 380px;
}

.carte-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.carte-search {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 42px;
  padding: 0 12px;
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider-strong);
  border-radius: var(--radius-md);
}

.carte-search:focus-within {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(10, 102, 245, 0.14);
}

.carte-search__icon {
  color: var(--color-neutral-400);
  flex-shrink: 0;
}

.carte-search__input {
  flex: 1;
  min-width: 0;
  background: transparent;
  border: none;
  outline: none;
  font-size: 13.5px;
  color: var(--color-neutral-200);
}

.carte-kinds {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.carte-kind {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border: 1px solid var(--color-divider-strong);
  border-radius: var(--radius-md);
  background: var(--color-neutral-900);
  color: var(--color-neutral-200);
  font-size: 12.5px;
  font-weight: 600;
  text-align: left;
  cursor: pointer;
  transition: opacity 0.12s ease, background 0.12s ease;
}

.carte-kind--off {
  opacity: 0.5;
  background: transparent;
}

.carte-kind__dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  flex-shrink: 0;
}

.carte-kind__count {
  margin-left: auto;
  font-size: 11.5px;
  color: var(--color-neutral-400);
  background: var(--color-neutral-700);
  border-radius: 999px;
  padding: 1px 8px;
}

.carte-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 320px;
  overflow-y: auto;
  padding-right: 2px;
}

.carte-list__note {
  padding: 18px 8px;
  text-align: center;
  font-size: 12.5px;
  color: var(--color-neutral-400);
}

.carte-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  background: var(--color-neutral-900);
  text-align: left;
  cursor: pointer;
  transition: background 0.12s ease, border-color 0.12s ease;
}

.carte-item:hover {
  background: var(--color-neutral-800);
}

.carte-item--selected {
  border-color: var(--color-primary);
  background: color-mix(in srgb, var(--color-primary) 7%, var(--color-neutral-900));
}

.carte-item__pin {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  flex-shrink: 0;
}

.carte-item__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.carte-item__name {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-neutral-200);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.carte-item__sub {
  font-size: 11.5px;
  color: var(--color-neutral-400);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.carte-item__status {
  font-size: 10.5px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
  flex-shrink: 0;
  background: var(--color-neutral-700);
  color: var(--color-neutral-400);
}

.carte-item__status--success {
  background: color-mix(in srgb, var(--color-success) 16%, transparent);
  color: var(--color-success);
}

.carte-item__status--warning {
  background: rgba(224, 130, 46, 0.16);
  color: #b3651a;
}

.carte-item__status--error {
  background: color-mix(in srgb, var(--color-error) 14%, transparent);
  color: var(--color-error);
}

.carte-unplaced {
  border: 1px dashed rgba(224, 130, 46, 0.55);
  border-radius: var(--radius-md);
  background: rgba(224, 130, 46, 0.06);
  padding: 4px 10px 8px;
}

.carte-unplaced__toggle {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  padding: 8px 0;
  border: none;
  background: transparent;
  color: #b3651a;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
}

.carte-unplaced__chevron {
  margin-left: auto;
  font-size: 16px;
}

.carte-unplaced__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 160px;
  overflow-y: auto;
}

.carte-unplaced__list a {
  display: block;
  font-size: 12.5px;
  color: var(--color-neutral-200);
  text-decoration: none;
}

.carte-unplaced__list a:hover {
  text-decoration: underline;
}

.carte-unplaced__kind {
  font-size: 10.5px;
  font-weight: 700;
  text-transform: uppercase;
  color: var(--color-neutral-400);
  margin-right: 6px;
}

.carte-unplaced__hint {
  margin: 8px 0 0;
  font-size: 11.5px;
  color: var(--color-neutral-400);
}

@media (min-width: 960px) {
  .carte-layout {
    display: grid;
    grid-template-columns: 340px minmax(0, 1fr);
    align-items: stretch;
    /* La carte occupe la hauteur restante de la fenêtre. */
    height: calc(100dvh - 210px);
    min-height: 560px;
  }

  .carte-map {
    order: 0;
    height: 100%;
    min-height: 0;
  }

  .carte-panel {
    overflow-y: auto;
    padding-right: 4px;
  }

  .carte-list {
    max-height: none;
    flex: 1;
    min-height: 140px;
  }
}
</style>
