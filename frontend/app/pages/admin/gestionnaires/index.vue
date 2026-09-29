<script setup lang="ts">
import { PhArrowsLeftRight, PhIdentificationCard, PhMagnifyingGlass, PhMapPin, PhTrash } from '@phosphor-icons/vue'
import type { AdminManagerOverview, PickupPointRead } from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const { apiFetch } = useApi()
const toast = useToastStore()

const { data: managers, pending, refresh } = await useAsyncData(
  'admin-managers-overview',
  () => apiFetch<AdminManagerOverview[]>('/admin/pickup-point-managers/overview'),
  { default: () => [], getCachedData: hydrateThenRefetch },
)
const { data: points } = await useAsyncData('admin-pickup-points-options', () => apiFetch<PickupPointRead[]>('/admin/pickup-points'), {
  default: () => [],
})

const filter = ref<'all' | 'active' | 'inactive'>('all')
const search = ref<string | null>('')
function normalize(v: string) {
  return v.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
}
const visible = computed(() => {
  const term = normalize((search.value ?? '').trim())
  return managers.value.filter((m) => {
    if (filter.value === 'active' && !m.is_active) return false
    if (filter.value === 'inactive' && m.is_active) return false
    if (!term) return true
    return normalize([m.full_name ?? '', m.phone, m.email ?? '', m.pickup_point_name].join(' ')).includes(term)
  })
})
const counts = computed(() => ({
  all: managers.value.length,
  active: managers.value.filter((m) => m.is_active).length,
  inactive: managers.value.filter((m) => !m.is_active).length,
}))

function initials(m: AdminManagerOverview) {
  const parts = (m.full_name ?? '').split(' ').filter(Boolean)
  return (parts.map((p) => p[0]).join('').slice(0, 2) || m.phone.slice(-2)).toUpperCase()
}

const busyId = ref<string | null>(null)
async function toggleActive(m: AdminManagerOverview) {
  busyId.value = m.id
  try {
    await apiFetch(`/admin/users/${m.user_id}`, { method: 'PATCH', body: { is_active: !m.is_active } })
    await refresh()
    toast.success(m.is_active ? 'Compte désactivé : il ne peut plus se connecter.' : 'Compte réactivé.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de changer le statut de ce compte.'))
  } finally {
    busyId.value = null
  }
}

// Réaffectation à un autre point.
const moveTarget = ref<AdminManagerOverview | null>(null)
const movePointId = ref<string | null>(null)
const pointOptions = computed(() =>
  points.value.map((p) => ({ title: p.is_active ? p.name : `${p.name} (inactif)`, value: p.id, props: { subtitle: p.zone } })),
)
function openMove(m: AdminManagerOverview) {
  moveTarget.value = m
  movePointId.value = m.pickup_point_id
}
async function move() {
  const m = moveTarget.value
  if (!m || !movePointId.value) return
  busyId.value = m.id
  try {
    await apiFetch(`/admin/pickup-point-managers/${m.id}`, { method: 'PATCH', body: { pickup_point_id: movePointId.value } })
    moveTarget.value = null
    await refresh()
    toast.success('Gestionnaire réaffecté.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de réaffecter ce gestionnaire.'))
  } finally {
    busyId.value = null
  }
}

const removeTarget = ref<AdminManagerOverview | null>(null)
async function remove() {
  const m = removeTarget.value
  if (!m) return
  busyId.value = m.id
  try {
    await apiFetch(`/admin/pickup-point-managers/${m.id}`, { method: 'DELETE' })
    removeTarget.value = null
    await refresh()
    toast.success('Gestionnaire retiré : son compte redevient acheteur.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de retirer ce gestionnaire.'))
  } finally {
    busyId.value = null
  }
}
</script>

<template>
  <div class="dashboard-shell">
    <div class="d-flex justify-space-between align-center flex-wrap ga-2 mb-4">
      <div>
        <h1 class="text-h6 mb-0">Gestionnaires de points de retrait</h1>
        <p class="text-muted mb-0" style="font-size: 13px">
          Pour en nommer un nouveau, passez par la fiche du point dans « Points de retrait ».
        </p>
      </div>
      <v-btn to="/admin/points-retrait" variant="tonal" color="primary"><PhMapPin :size="16" class="mr-1" /> Points de retrait</v-btn>
    </div>

    <div class="mg-toolbar mb-4">
      <v-btn-toggle v-model="filter" mandatory density="comfortable" divided>
        <v-btn value="all" size="small">Tous ({{ counts.all }})</v-btn>
        <v-btn value="active" size="small">Actifs ({{ counts.active }})</v-btn>
        <v-btn value="inactive" size="small">Désactivés ({{ counts.inactive }})</v-btn>
      </v-btn-toggle>
      <v-text-field
        v-model="search"
        placeholder="Nom, téléphone, e-mail ou point…"
        density="compact"
        variant="outlined"
        hide-details
        clearable
        class="mg-search"
      >
        <template #prepend-inner><PhMagnifyingGlass :size="16" color="var(--color-neutral-500)" /></template>
      </v-text-field>
    </div>

    <CommonEmptyState v-if="!pending && !managers.length" message="Aucun gestionnaire de point de retrait pour l'instant." />
    <CommonEmptyState v-else-if="!pending && !visible.length" message="Aucun gestionnaire ne correspond." />

    <div class="mg-grid">
      <article v-for="m in visible" :key="m.id" class="mg-card" :class="{ 'mg-card--off': !m.is_active }">
        <div class="mg-card__head">
          <span class="mg-card__avatar">{{ initials(m) }}</span>
          <div class="mg-card__who">
            <NuxtLink :to="`/admin/utilisateurs/${m.user_id}`" class="mg-card__name">{{ m.full_name ?? m.phone }}</NuxtLink>
            <small>{{ m.phone }}<template v-if="m.email"> · {{ m.email }}</template></small>
          </div>
          <span class="pf-tag" :class="m.is_active ? 'pf-tag--success' : 'pf-tag--error'">{{ m.is_active ? 'Actif' : 'Désactivé' }}</span>
          <v-btn icon variant="text" size="x-small" color="error" aria-label="Retirer de ce point" title="Retirer de ce point" @click="removeTarget = m">
            <PhTrash :size="16" />
          </v-btn>
        </div>

        <NuxtLink :to="`/admin/points-retrait/${m.pickup_point_id}`" class="mg-card__point">
          <PhMapPin :size="16" weight="fill" />
          <span>{{ m.pickup_point_name }}</span>
          <span v-if="!m.pickup_point_is_active" class="pf-tag pf-tag--warning">Point inactif</span>
        </NuxtLink>

        <div class="mg-card__stats">
          <span><strong>{{ m.parcels_in_stock }}</strong> en stock</span>
          <span><strong>{{ m.parcels_delivered }}</strong> retirés</span>
          <span>depuis le {{ new Date(m.created_at).toLocaleDateString('fr-FR') }}</span>
        </div>

        <div class="mg-card__actions">
          <v-btn :to="`/admin/utilisateurs/${m.user_id}`" variant="tonal" color="primary" size="small" class="mr-auto">
            <PhIdentificationCard :size="15" class="mr-1" /> Fiche
          </v-btn>
          <v-btn variant="outlined" size="small" @click="openMove(m)"><PhArrowsLeftRight :size="15" class="mr-1" /> Réaffecter</v-btn>
          <v-btn variant="outlined" size="small" :color="m.is_active ? 'warning' : 'success'" :loading="busyId === m.id" @click="toggleActive(m)">
            {{ m.is_active ? 'Désactiver' : 'Activer' }}
          </v-btn>
        </div>
      </article>
    </div>

    <v-dialog :model-value="!!moveTarget" max-width="440" @update:model-value="(v) => !v && (moveTarget = null)">
      <v-card class="pa-5">
        <h2 class="text-subtitle-1 mb-3">Réaffecter {{ moveTarget?.full_name ?? moveTarget?.phone }}</h2>
        <v-select v-model="movePointId" :items="pointOptions" label="Nouveau point de retrait" hide-details />
        <div class="d-flex ga-2 mt-4">
          <v-btn variant="outlined" class="flex-grow-1" @click="moveTarget = null">Annuler</v-btn>
          <v-btn color="primary" class="flex-grow-1" :disabled="!movePointId || movePointId === moveTarget?.pickup_point_id" :loading="!!busyId" @click="move">
            Réaffecter
          </v-btn>
        </div>
      </v-card>
    </v-dialog>

    <v-dialog :model-value="!!removeTarget" max-width="400" @update:model-value="(v) => !v && (removeTarget = null)">
      <v-card class="pa-5">
        <h2 class="text-subtitle-1 mb-2">Retirer ce gestionnaire ?</h2>
        <p class="text-muted mb-4" style="font-size: 13px">
          {{ removeTarget?.full_name ?? removeTarget?.phone }} ne gérera plus « {{ removeTarget?.pickup_point_name }} ». Son compte est
          conservé et redevient acheteur.
        </p>
        <div class="d-flex ga-2">
          <v-btn variant="outlined" class="flex-grow-1" @click="removeTarget = null">Annuler</v-btn>
          <v-btn color="error" class="flex-grow-1" :loading="!!busyId" @click="remove">Retirer</v-btn>
        </div>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.mg-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}

.mg-search {
  flex: 1 1 240px;
  max-width: 420px;
}

.mg-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 380px), 1fr));
  gap: 14px;
}

.mg-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-divider);
  background: var(--color-neutral-900);
  box-shadow: var(--shadow-sm);
}

.mg-card--off {
  opacity: 0.75;
}

.mg-card__head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.mg-card__avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  flex-shrink: 0;
  border-radius: 14px;
  background: linear-gradient(135deg, hsl(270 70% 58%), hsl(300 65% 52%));
  color: #fff;
  font-weight: 800;
}

.mg-card__who {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.mg-card__who small {
  color: var(--color-neutral-400);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mg-card__name {
  font-weight: 700;
  color: inherit;
  text-decoration: none;
}

.mg-card__name:hover {
  color: var(--color-primary);
  text-decoration: underline;
}

.mg-card__point {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  background: var(--color-neutral-800);
  color: inherit;
  font-size: 13.5px;
  font-weight: 700;
  text-decoration: none;
}

.mg-card__point svg {
  color: hsl(270 60% 58%);
}

.mg-card__point:hover {
  color: var(--color-primary);
}

.mg-card__stats {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
  font-size: 12.5px;
  color: var(--color-neutral-400);
}

.mg-card__stats strong {
  color: var(--color-neutral-100);
}

.mg-card__actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
</style>
