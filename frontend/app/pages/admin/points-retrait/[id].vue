<script setup lang="ts">
import {
  PhArrowLeft,
  PhClock,
  PhIdentificationCard,
  PhMapPin,
  PhPackage,
  PhPhone,
  PhStar,
  PhStorefront,
  PhTrash,
  PhUsers,
  PhWallet,
} from '@phosphor-icons/vue'
import type { AdminPickupPointProfile, ManagerSummary, PickupPointRead } from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const route = useRoute()
const toast = useToastStore()
const { apiFetch } = useApi()
const pointId = route.params.id as string

const { data: profile, error, refresh } = await useAsyncData(`admin-pickup-${pointId}`, () =>
  apiFetch<AdminPickupPointProfile>(`/admin/pickup-points/${pointId}/profile`),
)
const point = computed(() => profile.value?.point ?? null)

function formatDate(iso: string, withTime = false) {
  return new Date(iso).toLocaleDateString('fr-FR', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    ...(withTime ? { hour: '2-digit', minute: '2-digit' } : {}),
  })
}

const PARCEL_STATUS: Record<string, string> = {
  shipped: 'En route vers le point',
  arrived_at_pickup_point: 'En stock',
  delivered: 'Retiré',
}

// --- Point ------------------------------------------------------------------------

const toggling = ref(false)
async function toggleActive() {
  toggling.value = true
  try {
    await apiFetch<PickupPointRead>(`/admin/pickup-points/${pointId}`, { method: 'PATCH', body: { is_active: !point.value!.is_active } })
    await refresh()
    toast.success(point.value!.is_active ? 'Point activé.' : 'Point désactivé : il n’est plus proposé aux acheteurs.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de mettre à jour ce point.'))
  } finally {
    toggling.value = false
  }
}

const editOpen = ref(false)
const saving = ref(false)
const form = ref({ name: '', zone: '', opening_hours: '', latitude: null as number | null, longitude: null as number | null })
function openEdit() {
  const p = point.value!
  form.value = { name: p.name, zone: p.zone, opening_hours: p.opening_hours ?? '', latitude: p.latitude, longitude: p.longitude }
  editOpen.value = true
}
async function save() {
  const f = form.value
  saving.value = true
  try {
    await apiFetch(`/admin/pickup-points/${pointId}`, {
      method: 'PATCH',
      body: {
        name: f.name.trim(),
        zone: f.zone.trim(),
        opening_hours: f.opening_hours.trim() || null,
        latitude: f.latitude,
        longitude: f.longitude,
      },
    })
    editOpen.value = false
    await refresh()
    toast.success('Point mis à jour.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible d’enregistrer ce point.'))
  } finally {
    saving.value = false
  }
}

// --- Gestionnaires ------------------------------------------------------------------

const busyManager = ref<string | null>(null)
async function toggleManager(m: ManagerSummary) {
  busyManager.value = m.id
  try {
    await apiFetch(`/admin/users/${m.user_id}`, { method: 'PATCH', body: { is_active: !m.is_active } })
    await refresh()
    toast.success(m.is_active ? 'Gestionnaire désactivé.' : 'Gestionnaire réactivé.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de changer le statut de ce compte.'))
  } finally {
    busyManager.value = null
  }
}

const removeTarget = ref<ManagerSummary | null>(null)
async function removeManager() {
  const m = removeTarget.value
  if (!m) return
  busyManager.value = m.id
  try {
    await apiFetch(`/admin/pickup-point-managers/${m.id}`, { method: 'DELETE' })
    removeTarget.value = null
    await refresh()
    toast.success('Gestionnaire retiré de ce point.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de retirer ce gestionnaire.'))
  } finally {
    busyManager.value = null
  }
}
</script>

<template>
  <div class="dashboard-shell">
    <CommonEmptyState v-if="error" title="Point introuvable" message="Ce point de retrait n'existe plus." />
    <template v-else-if="profile && point">
      <header class="pf-head">
        <NuxtLink to="/admin/points-retrait" class="pf-back" aria-label="Retour aux points de retrait"><PhArrowLeft :size="18" /></NuxtLink>
        <span class="pf-avatar" style="--hue: 270"><PhMapPin :size="28" weight="fill" /></span>
        <div class="pf-title">
          <h1 class="text-h6">{{ point.name }}</h1>
          <div class="pf-tags">
            <span class="pf-tag" :class="point.is_active ? 'pf-tag--success' : 'pf-tag--error'">{{ point.is_active ? 'Actif' : 'Inactif' }}</span>
            <span v-if="point.vendor_shop_name" class="pf-tag pf-tag--primary"><PhStorefront :size="12" /> {{ point.vendor_shop_name }}</span>
            <span v-if="point.review_count" class="pf-tag">
              <PhStar :size="12" weight="fill" color="var(--color-accent)" /> {{ point.average_rating?.toFixed(1) }} ({{ point.review_count }} avis)
            </span>
            <span v-if="!profile.managers.length" class="pf-tag pf-tag--warning">Sans gestionnaire</span>
          </div>
        </div>
        <div class="pf-actions">
          <v-btn variant="tonal" color="primary" @click="openEdit">Modifier</v-btn>
          <v-btn variant="outlined" :color="point.is_active ? 'warning' : 'success'" :loading="toggling" @click="toggleActive">
            {{ point.is_active ? 'Désactiver' : 'Activer' }}
          </v-btn>
        </div>
      </header>

      <div class="pf-stats">
        <div class="pf-stat"><strong>{{ profile.stats.in_stock }}</strong><span>Colis en stock</span></div>
        <div class="pf-stat"><strong>{{ profile.stats.expected }}</strong><span>Colis attendus</span></div>
        <div class="pf-stat"><strong>{{ profile.stats.delivered }}</strong><span>Colis retirés</span></div>
        <div class="pf-stat"><strong>{{ profile.stats.delivered_30d }}</strong><span>Retirés sur 30 jours</span></div>
        <div v-if="profile.wallet" class="pf-stat"><strong>{{ formatGnf(profile.wallet.available) }}</strong><span>Commissions disponibles</span></div>
      </div>

      <div class="pf-grid">
        <section class="pf-card">
          <h2 class="pf-card__title">Informations</h2>
          <dl class="pf-kv">
            <dt><PhMapPin :size="14" /> Zone / repère</dt>
            <dd>{{ point.zone }}</dd>
            <dt><PhClock :size="14" /> Horaires</dt>
            <dd>{{ point.opening_hours ?? '—' }}</dd>
            <dt>Position GPS</dt>
            <dd>
              <a
                v-if="point.latitude !== null && point.longitude !== null"
                :href="`https://www.openstreetmap.org/?mlat=${point.latitude}&mlon=${point.longitude}#map=17/${point.latitude}/${point.longitude}`"
                target="_blank"
                rel="noopener"
              >{{ point.latitude.toFixed(5) }}, {{ point.longitude.toFixed(5) }}</a>
              <span v-else class="text-warning">Non renseignée</span>
            </dd>
            <dt><PhStorefront :size="14" /> Boutique liée</dt>
            <dd>{{ point.vendor_shop_name ?? 'Aucune (local dédié)' }}</dd>
            <dt><PhWallet :size="14" /> En attente</dt>
            <dd>{{ profile.wallet ? formatGnf(profile.wallet.pending) : '—' }}</dd>
          </dl>
        </section>

        <section class="pf-card">
          <h2 class="pf-card__title">
            <span><PhUsers :size="16" /> Gestionnaires</span>
            <v-btn to="/admin/gestionnaires" variant="text" size="small">Tous les gestionnaires</v-btn>
          </h2>
          <ul class="pf-list">
            <li v-for="m in profile.managers" :key="m.id" class="pf-row">
              <span class="pf-row__main">
                <strong>{{ m.full_name ?? m.phone }}</strong>
                <small><PhPhone :size="11" /> {{ m.phone }}<template v-if="m.email"> · {{ m.email }}</template></small>
              </span>
              <span class="pf-tag" :class="m.is_active ? 'pf-tag--success' : 'pf-tag--error'">{{ m.is_active ? 'Actif' : 'Désactivé' }}</span>
              <v-btn :to="`/admin/utilisateurs/${m.user_id}`" icon variant="text" size="small" aria-label="Fiche">
                <PhIdentificationCard :size="18" />
              </v-btn>
              <v-btn variant="text" size="small" :color="m.is_active ? 'warning' : 'success'" :loading="busyManager === m.id" @click="toggleManager(m)">
                {{ m.is_active ? 'Désactiver' : 'Activer' }}
              </v-btn>
              <v-btn icon variant="text" size="small" color="error" aria-label="Retirer" @click="removeTarget = m">
                <PhTrash :size="18" />
              </v-btn>
            </li>
            <li v-if="!profile.managers.length" class="pf-empty">
              Aucun gestionnaire. Ajoutez-en un depuis la liste des points de retrait.
            </li>
          </ul>
        </section>

        <section class="pf-card pf-card--wide">
          <h2 class="pf-card__title"><span><PhPackage :size="16" /> Derniers colis</span></h2>
          <ul class="pf-list">
            <NuxtLink v-for="c in profile.recent_parcels" :key="c.sub_order_id" :to="`/admin/commandes/${c.order_id}`" class="pf-row">
              <span class="pf-row__main">
                <OrderNumber :id="c.order_id" />
                <small>{{ c.shop_name }} · {{ formatDate(c.updated_at, true) }}</small>
              </span>
              <span
                v-if="PARCEL_STATUS[c.status]"
                class="pf-tag"
                :class="{ 'pf-tag--warning': c.status === 'arrived_at_pickup_point', 'pf-tag--success': c.status === 'delivered' }"
              >
                {{ PARCEL_STATUS[c.status] }}
              </span>
              <StatusBadge v-else :status="c.status" />
            </NuxtLink>
            <li v-if="!profile.recent_parcels.length" class="pf-empty">Aucun colis passé par ce point.</li>
          </ul>
        </section>
      </div>

      <v-dialog v-model="editOpen" max-width="560">
        <v-card class="pa-5">
          <h2 class="text-subtitle-1 mb-4">Modifier le point</h2>
          <v-text-field v-model="form.name" label="Nom du point" class="mb-2" hide-details />
          <v-textarea v-model="form.zone" label="Zone / repère" rows="2" class="mt-3" hide-details />
          <v-text-field v-model="form.opening_hours" label="Horaires (ex. Lun–Sam 8h–19h)" class="mt-3 mb-3" hide-details />
          <CommonMapPicker v-model:latitude="form.latitude" v-model:longitude="form.longitude" />
          <div class="d-flex ga-2 mt-4">
            <v-btn variant="outlined" class="flex-grow-1" @click="editOpen = false">Annuler</v-btn>
            <v-btn color="primary" class="flex-grow-1" :loading="saving" :disabled="form.name.trim().length < 2 || form.zone.trim().length < 3" @click="save">Enregistrer</v-btn>
          </div>
        </v-card>
      </v-dialog>

      <v-dialog :model-value="!!removeTarget" max-width="400" @update:model-value="(v) => !v && (removeTarget = null)">
        <v-card class="pa-5">
          <h2 class="text-subtitle-1 mb-2">Retirer ce gestionnaire ?</h2>
          <p class="text-muted mb-4" style="font-size: 13px">
            {{ removeTarget?.full_name ?? removeTarget?.phone }} ne pourra plus gérer ce point. Son compte est conservé.
          </p>
          <div class="d-flex ga-2">
            <v-btn variant="outlined" class="flex-grow-1" @click="removeTarget = null">Annuler</v-btn>
            <v-btn color="error" class="flex-grow-1" :loading="!!busyManager" @click="removeManager">Retirer</v-btn>
          </div>
        </v-card>
      </v-dialog>
    </template>
  </div>
</template>
