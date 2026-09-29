<script setup lang="ts">
import {
  PhArrowLeft,
  PhCaretLeft,
  PhCaretRight,
  PhEnvelopeSimple,
  PhIdentificationCard,
  PhMapPin,
  PhMotorcycle,
  PhPhone,
  PhStar,
  PhTruck,
  PhUserCircle,
  PhWallet,
} from '@phosphor-icons/vue'
import type { AdminCourierProfile, CourierDetailRead, CourierStatus } from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const route = useRoute()
const toast = useToastStore()
const { apiFetch, apiFetchBlob } = useApi()
const courierId = route.params.id as string

const { data: profile, error, refresh } = await useAsyncData(`admin-courier-${courierId}`, () =>
  apiFetch<AdminCourierProfile>(`/admin/couriers/${courierId}/profile`),
)
const courier = computed(() => profile.value?.courier ?? null)

const STATUS: Record<CourierStatus, { label: string; tone: string }> = {
  pending: { label: 'En attente de validation', tone: 'warning' },
  approved: { label: 'Approuvé', tone: 'success' },
  rejected: { label: 'Rejeté', tone: 'error' },
  suspended: { label: 'Suspendu', tone: 'error' },
}
const VEHICLES: Record<string, string> = { moto: 'Moto', taxi: 'Taxi', voiture: 'Voiture' }
const ID_DOCS: Record<string, string> = { cni_biometrique: "Carte d'identité biométrique", passeport: 'Passeport' }

function formatDate(iso: string | null, withTime = false) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('fr-FR', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    ...(withTime ? { hour: '2-digit', minute: '2-digit' } : {}),
  })
}

// --- Documents (non publics : chargés en blob) ---------------------------------------

interface DocEntry { label: string; key: string }
const docs = computed<DocEntry[]>(() => {
  const c = courier.value
  if (!c) return []
  const list: DocEntry[] = []
  if (c.face_photo_key) list.push({ label: 'Photo de visage', key: c.face_photo_key })
  if (c.id_document_front_key) list.push({ label: `${ID_DOCS[c.id_document_type ?? ''] ?? 'Pièce'} (recto)`, key: c.id_document_front_key })
  if (c.id_document_back_key) list.push({ label: 'Pièce (verso)', key: c.id_document_back_key })
  c.vehicle_photo_keys.forEach((key, i) => list.push({ label: `Engin — photo ${i + 1}`, key }))
  return list
})
const urls = reactive<Record<string, string>>({})
onMounted(async () => {
  for (const { key } of docs.value) {
    try {
      urls[key] = URL.createObjectURL(await apiFetchBlob(`/couriers/${courierId}/documents/${key}`))
    } catch {
      // Vignette absente : la case reste sur son libellé.
    }
  }
})
onBeforeUnmount(() => Object.values(urls).forEach((u) => URL.revokeObjectURL(u)))

const viewerIndex = ref<number | null>(null)
const viewerDoc = computed(() => (viewerIndex.value === null ? null : docs.value[viewerIndex.value] ?? null))

// --- Statut ------------------------------------------------------------------------

const updating = ref(false)
const rejectOpen = ref(false)
const rejectNote = ref('')
async function setStatus(status: CourierStatus, adminNote?: string) {
  updating.value = true
  try {
    await apiFetch<CourierDetailRead>(`/admin/couriers/${courierId}`, {
      method: 'PATCH',
      body: { status, ...(adminNote ? { admin_note: adminNote } : {}) },
    })
    rejectOpen.value = false
    await refresh()
    toast.success('Statut mis à jour.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de mettre à jour ce livreur.'))
  } finally {
    updating.value = false
  }
}

// --- Édition ------------------------------------------------------------------------

const editOpen = ref(false)
const saving = ref(false)
const form = ref({ first_name: '', last_name: '', email: '', vehicle_type: 'moto', vehicle_name: '', vehicle_plate_number: '', zone: '' })
function openEdit() {
  const p = profile.value!
  const [first = '', ...rest] = (p.courier.full_name ?? '').split(' ')
  form.value = {
    first_name: first,
    last_name: rest.join(' '),
    email: p.email ?? '',
    vehicle_type: p.courier.vehicle_type,
    vehicle_name: p.courier.vehicle_name ?? '',
    vehicle_plate_number: p.courier.vehicle_plate_number ?? '',
    zone: p.courier.zone ?? '',
  }
  editOpen.value = true
}
async function save() {
  const f = form.value
  saving.value = true
  try {
    await apiFetch(`/admin/users/${profile.value!.courier.user_id}`, {
      method: 'PATCH',
      body: { first_name: f.first_name, last_name: f.last_name, email: f.email.trim() || null },
    })
    await apiFetch(`/admin/couriers/${courierId}`, {
      method: 'PATCH',
      body: {
        vehicle_type: f.vehicle_type,
        vehicle_name: f.vehicle_name.trim() || null,
        vehicle_plate_number: f.vehicle_plate_number.trim() || null,
        zone: f.zone.trim() || null,
      },
    })
    editOpen.value = false
    await refresh()
    toast.success('Fiche livreur mise à jour.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible d’enregistrer.'))
  } finally {
    saving.value = false
  }
}

const toggling = ref(false)
async function toggleAccount() {
  toggling.value = true
  try {
    await apiFetch(`/admin/users/${profile.value!.courier.user_id}`, {
      method: 'PATCH',
      body: { is_active: !profile.value!.user_is_active },
    })
    await refresh()
    toast.success(profile.value!.user_is_active ? 'Compte réactivé.' : 'Compte désactivé.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de changer le statut du compte.'))
  } finally {
    toggling.value = false
  }
}
</script>

<template>
  <div class="dashboard-shell">
    <CommonEmptyState v-if="error" title="Livreur introuvable" message="Cette fiche n'existe plus." />
    <template v-else-if="profile && courier">
      <header class="pf-head">
        <NuxtLink to="/admin/livreurs" class="pf-back" aria-label="Retour aux livreurs"><PhArrowLeft :size="18" /></NuxtLink>
        <span class="pf-avatar pf-avatar--photo" style="--hue: 30">
          <img v-if="courier.face_photo_key && urls[courier.face_photo_key]" :src="urls[courier.face_photo_key]" alt="" />
          <PhUserCircle v-else :size="26" />
        </span>
        <div class="pf-title">
          <h1 class="text-h6">{{ courier.full_name ?? courier.phone }}</h1>
          <div class="pf-tags">
            <span class="pf-tag" :class="`pf-tag--${STATUS[courier.status].tone}`">{{ STATUS[courier.status].label }}</span>
            <span class="pf-tag" :class="courier.is_online ? 'pf-tag--success' : ''">{{ courier.is_online ? 'En ligne' : 'Hors ligne' }}</span>
            <span v-if="!profile.user_is_active" class="pf-tag pf-tag--error">Compte désactivé</span>
            <span v-if="courier.review_count" class="pf-tag">
              <PhStar :size="12" weight="fill" color="var(--color-accent)" /> {{ courier.average_rating?.toFixed(1) }} ({{ courier.review_count }} avis)
            </span>
          </div>
        </div>
        <div class="pf-actions">
          <v-btn variant="tonal" color="primary" @click="openEdit">Modifier</v-btn>
          <template v-if="courier.status === 'pending'">
            <v-btn color="primary" :loading="updating" @click="setStatus('approved')">Approuver</v-btn>
            <v-btn color="error" variant="outlined" @click="rejectOpen = true">Rejeter</v-btn>
          </template>
          <v-btn v-else-if="courier.status === 'approved'" color="error" variant="outlined" :loading="updating" @click="setStatus('suspended')">Suspendre</v-btn>
          <v-btn v-else color="primary" variant="outlined" :loading="updating" @click="setStatus('approved')">Réactiver</v-btn>
          <v-btn variant="text" :color="profile.user_is_active ? 'warning' : 'success'" :loading="toggling" @click="toggleAccount">
            {{ profile.user_is_active ? 'Désactiver le compte' : 'Réactiver le compte' }}
          </v-btn>
        </div>
      </header>

      <div class="pf-stats">
        <div class="pf-stat"><strong>{{ profile.stats.delivered }}</strong><span>Livraisons réussies</span></div>
        <div class="pf-stat"><strong>{{ profile.stats.delivered_30d }}</strong><span>Sur 30 jours</span></div>
        <div class="pf-stat"><strong>{{ profile.stats.in_progress }}</strong><span>En cours</span></div>
        <div class="pf-stat"><strong>{{ profile.stats.cancelled }}</strong><span>Annulées</span></div>
        <div v-if="profile.wallet" class="pf-stat">
          <strong>{{ formatGnf(profile.wallet.available) }}</strong><span>Gains disponibles</span>
        </div>
      </div>

      <div class="pf-grid">
        <section class="pf-card">
          <h2 class="pf-card__title">Identité et contact</h2>
          <dl class="pf-kv">
            <dt><PhPhone :size="14" /> Téléphone</dt>
            <dd><a :href="`tel:${courier.phone}`">{{ courier.phone }}</a></dd>
            <dt><PhEnvelopeSimple :size="14" /> E-mail</dt>
            <dd>{{ profile.email ?? '—' }}</dd>
            <dt><PhIdentificationCard :size="14" /> Pièce</dt>
            <dd>{{ ID_DOCS[courier.id_document_type ?? ''] ?? '—' }}</dd>
            <dt>Inscrit le</dt>
            <dd>{{ formatDate(profile.created_at) }}</dd>
            <dt>Compte utilisateur</dt>
            <dd><NuxtLink :to="`/admin/utilisateurs/${courier.user_id}`">Voir la fiche utilisateur</NuxtLink></dd>
          </dl>
          <p v-if="courier.admin_note" class="pf-note">Note admin : {{ courier.admin_note }}</p>
        </section>

        <section class="pf-card">
          <h2 class="pf-card__title"><span><PhMotorcycle :size="16" /> Engin et zone</span></h2>
          <dl class="pf-kv">
            <dt>Type</dt>
            <dd>{{ VEHICLES[courier.vehicle_type] ?? courier.vehicle_type }}</dd>
            <dt>Modèle</dt>
            <dd>{{ courier.vehicle_name ?? '—' }}</dd>
            <dt>Immatriculation</dt>
            <dd>{{ courier.vehicle_plate_number ?? '—' }}</dd>
            <dt><PhMapPin :size="14" /> Zone</dt>
            <dd>{{ courier.zone ?? '—' }}</dd>
            <dt><PhWallet :size="14" /> En attente</dt>
            <dd>{{ profile.wallet ? formatGnf(profile.wallet.pending) : '—' }}</dd>
          </dl>
        </section>

        <section class="pf-card">
          <h2 class="pf-card__title">Documents</h2>
          <div v-if="docs.length" class="pf-docs">
            <button v-for="(doc, i) in docs" :key="doc.key" type="button" class="pf-doc" @click="viewerIndex = i">
              <img v-if="urls[doc.key]" :src="urls[doc.key]" :alt="doc.label" />
              <span>{{ doc.label }}</span>
            </button>
          </div>
          <p v-else class="pf-empty">Aucun document fourni.</p>
        </section>

        <section class="pf-card">
          <h2 class="pf-card__title"><span><PhTruck :size="16" /> Dernières courses</span></h2>
          <ul class="pf-list">
            <NuxtLink v-for="d in profile.recent_deliveries" :key="d.sub_order_id" :to="`/admin/commandes/${d.order_id}`" class="pf-row">
              <span class="pf-row__main">
                <OrderNumber :id="d.order_id" />
                <small>{{ d.shop_name }} · {{ d.delivery_type === 'pickup_point' ? 'Point de retrait' : 'Domicile' }} · {{ formatDate(d.updated_at, true) }}</small>
              </span>
              <strong>{{ formatGnf(d.delivery_fee) }}</strong>
              <StatusBadge :status="d.status" />
            </NuxtLink>
            <li v-if="!profile.recent_deliveries.length" class="pf-empty">Aucune course pour l'instant.</li>
          </ul>
        </section>
      </div>

      <v-dialog :model-value="viewerIndex !== null" max-width="560" @update:model-value="(v) => !v && (viewerIndex = null)">
        <v-card v-if="viewerDoc" class="pa-3">
          <div class="d-flex justify-space-between align-center mb-2">
            <strong style="font-size: 13px">{{ viewerDoc.label }}</strong>
            <span class="text-muted" style="font-size: 12px">{{ (viewerIndex ?? 0) + 1 }} / {{ docs.length }}</span>
          </div>
          <img v-if="urls[viewerDoc.key]" :src="urls[viewerDoc.key]" :alt="viewerDoc.label" class="pf-viewer" />
          <div class="d-flex ga-2 mt-3">
            <v-btn variant="outlined" class="flex-grow-1" :disabled="!viewerIndex" @click="viewerIndex = (viewerIndex ?? 1) - 1"><PhCaretLeft :size="16" /></v-btn>
            <v-btn variant="outlined" class="flex-grow-1" :disabled="(viewerIndex ?? 0) >= docs.length - 1" @click="viewerIndex = (viewerIndex ?? 0) + 1"><PhCaretRight :size="16" /></v-btn>
            <v-btn variant="text" @click="viewerIndex = null">Fermer</v-btn>
          </div>
        </v-card>
      </v-dialog>

      <v-dialog v-model="rejectOpen" max-width="420">
        <v-card class="pa-5">
          <h2 class="text-subtitle-1 mb-3">Motif du rejet</h2>
          <v-textarea v-model="rejectNote" label="Visible par le livreur" rows="3" counter="300" maxlength="300" />
          <div class="d-flex ga-2 mt-2">
            <v-btn variant="outlined" class="flex-grow-1" @click="rejectOpen = false">Annuler</v-btn>
            <v-btn color="error" class="flex-grow-1" :disabled="!rejectNote.trim()" :loading="updating" @click="setStatus('rejected', rejectNote.trim())">Rejeter</v-btn>
          </div>
        </v-card>
      </v-dialog>

      <v-dialog v-model="editOpen" max-width="520">
        <v-card class="pa-5">
          <h2 class="text-subtitle-1 mb-4">Modifier la fiche livreur</h2>
          <div class="pf-form">
            <v-text-field v-model="form.first_name" label="Prénom" hide-details />
            <v-text-field v-model="form.last_name" label="Nom" hide-details />
            <v-text-field v-model="form.email" label="E-mail" type="email" hide-details class="pf-form__full" />
            <v-select
              v-model="form.vehicle_type"
              label="Type d'engin"
              :items="[{ title: 'Moto', value: 'moto' }, { title: 'Taxi', value: 'taxi' }, { title: 'Voiture', value: 'voiture' }]"
              hide-details
            />
            <v-text-field v-model="form.vehicle_name" label="Modèle" hide-details />
            <v-text-field v-model="form.vehicle_plate_number" label="Immatriculation" hide-details />
            <v-text-field v-model="form.zone" label="Zone" hide-details />
          </div>
          <div class="d-flex ga-2 mt-4">
            <v-btn variant="outlined" class="flex-grow-1" @click="editOpen = false">Annuler</v-btn>
            <v-btn color="primary" class="flex-grow-1" :loading="saving" @click="save">Enregistrer</v-btn>
          </div>
        </v-card>
      </v-dialog>
    </template>
  </div>
</template>
