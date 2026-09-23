<script setup lang="ts">
/**
 * Candidatures gestionnaire de point de retrait : examen des dossiers
 * (pièces, photo d'identité, point proposé, photos du local), décision —
 * valider, renvoyer pour correction (seconde chance) ou refuser
 * définitivement — et invitation d'un acheteur par e-mail.
 * Backend : app/pickup_point_applications.
 */
import {
  PhCheckCircle,
  PhClock,
  PhEnvelopeSimple,
  PhIdentificationCard,
  PhMapPin,
  PhProhibit,
  PhStorefront,
  PhArrowCounterClockwise,
  PhUser,
} from '@phosphor-icons/vue'
import type { AdminPickupApplicationRead, PickupApplicationStatus } from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const { apiFetch, apiFetchBlob } = useApi()
const toast = useToastStore()

const filter = ref<PickupApplicationStatus | 'all'>('submitted')
const { data: applications, pending, refresh } = await useAsyncData(
  'admin-pickup-applications',
  () =>
    apiFetch<AdminPickupApplicationRead[]>('/admin/pickup-point-applications', {
      query: filter.value === 'all' ? {} : { status: filter.value },
    }),
  { default: () => [], getCachedData: hydrateThenRefetch, watch: [filter] },
)

const STATUS_META: Record<PickupApplicationStatus, { label: string; color: string }> = {
  draft: { label: 'Brouillon', color: 'secondary' },
  submitted: { label: 'À examiner', color: 'warning' },
  changes_requested: { label: 'À corriger', color: 'info' },
  approved: { label: 'Validée', color: 'success' },
  rejected: { label: 'Refusée', color: 'error' },
}
const FILTERS: { value: PickupApplicationStatus | 'all'; label: string }[] = [
  { value: 'submitted', label: 'À examiner' },
  { value: 'changes_requested', label: 'À corriger' },
  { value: 'draft', label: 'Brouillons' },
  { value: 'approved', label: 'Validées' },
  { value: 'rejected', label: 'Refusées' },
  { value: 'all', label: 'Toutes' },
]

function fullName(a: AdminPickupApplicationRead) {
  return [a.first_name, a.last_name].filter(Boolean).join(' ') || a.applicant_phone
}
function formatDate(iso: string | null) {
  return iso ? new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'
}
function age(birth: string | null) {
  if (!birth) return null
  const diff = Date.now() - new Date(birth).getTime()
  return Math.floor(diff / (365.25 * 24 * 3600 * 1000))
}

// --- Détail d'un dossier ----------------------------------------------------------

const selected = ref<AdminPickupApplicationRead | null>(null)
const detailOpen = computed({
  get: () => selected.value !== null,
  set: (v: boolean) => {
    if (!v) selected.value = null
  },
})
const images = reactive<Record<string, string>>({})
const zoomed = ref<string | null>(null)

async function open(application: AdminPickupApplicationRead) {
  selected.value = application
  const keys = [
    application.id_document_front_key,
    application.id_document_back_key,
    application.portrait_photo_key,
    ...application.premises_photo_keys,
  ].filter((k): k is string => !!k && !images[k])
  await Promise.all(
    keys.map(async (key) => {
      try {
        const blob = await apiFetchBlob(`/pickup-point-applications/${application.id}/documents/${key}`)
        images[key] = URL.createObjectURL(blob)
      } catch {
        // Document illisible : la vignette reste vide.
      }
    }),
  )
}
onBeforeUnmount(() => Object.values(images).forEach((url) => URL.revokeObjectURL(url)))

// --- Décisions ------------------------------------------------------------------------

const busy = ref(false)
const decision = ref<'approve' | 'changes' | 'reject' | null>(null)
const reason = ref('')
const suggestion = ref('')

function openDecision(kind: 'approve' | 'changes' | 'reject') {
  decision.value = kind
  reason.value = ''
  suggestion.value = ''
}

async function decide() {
  if (!selected.value || !decision.value) return
  const id = selected.value.id
  const path = { approve: 'approve', changes: 'request-changes', reject: 'reject' }[decision.value]
  const body =
    decision.value === 'approve'
      ? undefined
      : decision.value === 'changes'
        ? { reason: reason.value.trim(), suggestion: suggestion.value.trim() || null }
        : { reason: reason.value.trim() }
  busy.value = true
  try {
    const updated = await apiFetch<AdminPickupApplicationRead>(`/admin/pickup-point-applications/${id}/${path}`, {
      method: 'POST',
      body,
    })
    toast.success(
      {
        approve: selected.value.target_pickup_point_id
          ? 'Candidature validée : le compte gère maintenant ce point.'
          : 'Candidature validée : le point de retrait est créé.',
        changes: 'Dossier renvoyé pour correction.',
        reject: 'Candidature refusée définitivement.',
      }[decision.value],
    )
    selected.value = updated
    decision.value = null
    await refresh()
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Action impossible.'))
  } finally {
    busy.value = false
  }
}

// --- Invitation -------------------------------------------------------------------------

const inviteOpen = ref(false)
const inviteEmail = ref('')
const inviteMessage = ref('')
const inviting = ref(false)

async function invite() {
  inviting.value = true
  try {
    await apiFetch('/admin/pickup-point-applications/invite', {
      method: 'POST',
      body: { email: inviteEmail.value.trim(), message: inviteMessage.value.trim() || null },
    })
    toast.success('Invitation envoyée par e-mail et notification.')
    inviteOpen.value = false
    inviteEmail.value = ''
    inviteMessage.value = ''
    filter.value = 'draft'
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'envoyer l'invitation."))
  } finally {
    inviting.value = false
  }
}

const mapUrl = (a: AdminPickupApplicationRead) =>
  `https://www.openstreetmap.org/?mlat=${a.latitude}&mlon=${a.longitude}#map=18/${a.latitude}/${a.longitude}`
</script>

<template>
  <div class="dashboard-shell">
    <div class="head">
      <div>
        <h1 class="text-h6 mb-0">Candidatures points de retrait</h1>
        <p class="text-muted text-meta mb-0">Acheteurs qui demandent à gérer un point de retrait.</p>
      </div>
      <v-btn color="primary" size="small" @click="inviteOpen = true">
        <PhEnvelopeSimple :size="16" class="mr-1" /> Inviter un acheteur
      </v-btn>
    </div>

    <v-btn-toggle v-model="filter" mandatory density="comfortable" divided class="mb-4 flex-wrap">
      <v-btn v-for="f in FILTERS" :key="f.value" :value="f.value" size="small">{{ f.label }}</v-btn>
    </v-btn-toggle>

    <v-skeleton-loader v-if="pending && !applications.length" type="list-item-two-line@3" />
    <CommonEmptyState v-else-if="!applications.length" message="Aucune candidature dans cette catégorie." />

    <div class="list">
      <button v-for="a in applications" :key="a.id" type="button" class="row" @click="open(a)">
        <div class="row__main">
          <div class="row__title">
            {{ a.target_pickup_point_name ?? a.point_name ?? 'Point sans nom' }}
            <v-chip v-if="a.target_pickup_point_id" size="x-small" variant="tonal" class="ml-1">point existant</v-chip>
          </div>
          <div class="text-muted text-meta">
            {{ fullName(a) }} · {{ a.applicant_phone }}<template v-if="!a.target_pickup_point_id"> · {{ a.point_address || 'adresse non renseignée' }}</template>
          </div>
          <div class="text-muted text-fine">
            <template v-if="a.submitted_at">Soumis le {{ formatDate(a.submitted_at) }}</template>
            <template v-else>Brouillon mis à jour le {{ formatDate(a.updated_at) }}</template>
            <template v-if="a.submission_count > 1"> · {{ a.submission_count }}ᵉ envoi</template>
            <template v-if="a.origin === 'invited'"> · sur invitation</template>
          </div>
        </div>
        <v-chip size="small" variant="tonal" :color="STATUS_META[a.status].color">{{ STATUS_META[a.status].label }}</v-chip>
      </button>
    </div>

    <!-- Détail -->
    <v-dialog v-model="detailOpen" max-width="860" scrollable>
      <v-card v-if="selected" class="detail">
        <div class="detail__head">
          <div>
            <h2 class="detail__title">{{ selected.target_pickup_point_name ?? selected.point_name ?? 'Point sans nom' }}</h2>
            <div class="text-muted text-meta">{{ fullName(selected) }} · {{ selected.applicant_phone }} · {{ selected.applicant_email ?? 'sans e-mail' }}</div>
          </div>
          <v-chip variant="tonal" :color="STATUS_META[selected.status].color">{{ STATUS_META[selected.status].label }}</v-chip>
        </div>

        <div class="detail__body">
          <div v-if="selected.admin_note" class="note">
            <strong>Dernière décision :</strong> {{ selected.admin_note }}
            <div v-if="selected.admin_suggestion"><em>Suggestion : {{ selected.admin_suggestion }}</em></div>
          </div>

          <section class="block">
            <h3><PhUser :size="16" /> Identité</h3>
            <div class="identity">
              <button v-if="selected.portrait_photo_key" type="button" class="portrait" @click="zoomed = images[selected.portrait_photo_key] ?? null">
                <img v-if="images[selected.portrait_photo_key]" :src="images[selected.portrait_photo_key]" alt="Photo d'identité" />
              </button>
              <dl class="facts">
                <div><dt>Nom</dt><dd>{{ fullName(selected) }}</dd></div>
                <div><dt>Naissance</dt><dd>{{ formatDate(selected.birth_date) }}<template v-if="age(selected.birth_date) !== null"> ({{ age(selected.birth_date) }} ans)</template></dd></div>
                <div><dt>Adresse</dt><dd>{{ selected.residence_address || '—' }}</dd></div>
                <div><dt>Pièce</dt><dd>{{ selected.id_document_type === 'passeport' ? 'Passeport' : 'CNI biométrique' }} n° {{ selected.id_document_number || '—' }}</dd></div>
              </dl>
            </div>
          </section>

          <section class="block">
            <h3><PhIdentificationCard :size="16" /> Pièce d'identité</h3>
            <div class="thumbs">
              <button
                v-for="key in [selected.id_document_front_key, selected.id_document_back_key].filter(Boolean) as string[]"
                :key="key"
                type="button"
                class="thumb thumb--doc"
                @click="zoomed = images[key] ?? null"
              >
                <img v-if="images[key]" :src="images[key]" alt="Pièce d'identité" />
              </button>
            </div>
          </section>

          <section v-if="selected.target_pickup_point_id" class="block">
            <h3><PhMapPin :size="16" /> Point existant</h3>
            <p class="text-meta mb-0">
              Invitation à gérer « {{ selected.target_pickup_point_name }} » : à la validation, le compte est rattaché
              à ce point (aucun nouveau point créé).
            </p>
          </section>

          <section v-if="!selected.target_pickup_point_id" class="block">
            <h3><PhMapPin :size="16" /> Point proposé</h3>
            <dl class="facts">
              <div><dt>Adresse</dt><dd>{{ selected.point_address || '—' }}</dd></div>
              <div><dt>Repère</dt><dd>{{ selected.point_landmark || '—' }}</dd></div>
              <div><dt>Horaires</dt><dd>{{ selected.opening_hours || '—' }}</dd></div>
              <div><dt>Capacité</dt><dd>{{ selected.storage_capacity ? `${selected.storage_capacity} colis` : '—' }}</dd></div>
              <div>
                <dt>Position</dt>
                <dd>
                  <a v-if="selected.latitude != null" :href="mapUrl(selected)" target="_blank" rel="noopener">
                    {{ selected.latitude.toFixed(5) }}, {{ selected.longitude?.toFixed(5) }} — voir sur la carte
                  </a>
                  <template v-else>—</template>
                </dd>
              </div>
            </dl>
          </section>

          <section v-if="!selected.target_pickup_point_id" class="block">
            <h3><PhStorefront :size="16" /> Photos du local ({{ selected.premises_photo_keys.length }})</h3>
            <div class="thumbs">
              <button v-for="key in selected.premises_photo_keys" :key="key" type="button" class="thumb" @click="zoomed = images[key] ?? null">
                <img v-if="images[key]" :src="images[key]" alt="Photo du local" />
              </button>
            </div>
          </section>
        </div>

        <div v-if="selected.status === 'submitted'" class="detail__actions">
          <v-btn variant="text" color="error" @click="openDecision('reject')"><PhProhibit :size="16" class="mr-1" /> Refuser définitivement</v-btn>
          <v-btn variant="tonal" @click="openDecision('changes')"><PhArrowCounterClockwise :size="16" class="mr-1" /> Renvoyer pour correction</v-btn>
          <v-btn color="primary" @click="openDecision('approve')"><PhCheckCircle :size="16" class="mr-1" /> Valider</v-btn>
        </div>
        <div v-else-if="selected.status === 'draft' || selected.status === 'changes_requested'" class="detail__actions">
          <span class="text-muted text-meta mr-auto"><PhClock :size="14" /> En attente du candidat</span>
          <v-btn variant="text" color="error" @click="openDecision('reject')">Refuser définitivement</v-btn>
        </div>
      </v-card>
    </v-dialog>

    <!-- Décision -->
    <v-dialog :model-value="!!decision" max-width="460" @update:model-value="(v) => { if (!v) decision = null }">
      <v-card v-if="decision && selected" class="pa-5">
        <template v-if="decision === 'approve'">
          <h2 class="dialog-title">Valider « {{ selected.target_pickup_point_name ?? selected.point_name }} » ?</h2>
          <p class="text-meta">
            <template v-if="selected.target_pickup_point_id">Le compte de {{ fullName(selected) }} sera rattaché à ce point existant comme gestionnaire.</template>
            <template v-else>Le point de retrait sera créé et actif, et le compte de {{ fullName(selected) }} deviendra gestionnaire de ce point.</template>
            Le candidat est prévenu par notification et par e-mail.
          </p>
        </template>
        <template v-else-if="decision === 'changes'">
          <h2 class="dialog-title">Renvoyer pour correction</h2>
          <p class="text-meta mb-3">Seconde chance : le dossier est rouvert, le candidat corrige puis le renvoie.</p>
          <v-textarea v-model="reason" label="Motif (visible par le candidat)" rows="2" auto-grow variant="outlined" />
          <v-textarea v-model="suggestion" label="Suggestion pour corriger (facultatif)" rows="2" auto-grow variant="outlined" />
        </template>
        <template v-else>
          <h2 class="dialog-title">Refuser définitivement</h2>
          <p class="text-meta mb-3">Le compte ne pourra plus postuler. Vous pourrez toujours l'inviter plus tard.</p>
          <v-textarea v-model="reason" label="Motif (visible par le candidat)" rows="2" auto-grow variant="outlined" />
        </template>
        <div class="d-flex justify-end ga-2 mt-2">
          <v-btn variant="text" @click="decision = null">Annuler</v-btn>
          <v-btn
            :color="decision === 'reject' ? 'error' : 'primary'"
            :loading="busy"
            :disabled="decision !== 'approve' && reason.trim().length < 5"
            @click="decide"
          >
            Confirmer
          </v-btn>
        </div>
      </v-card>
    </v-dialog>

    <!-- Invitation -->
    <v-dialog v-model="inviteOpen" max-width="440">
      <v-card class="pa-5">
        <h2 class="dialog-title">Inviter un acheteur</h2>
        <p class="text-meta mb-3">
          La personne doit déjà avoir un compte acheteur. Elle reçoit un e-mail et une notification pour compléter son
          dossier.
        </p>
        <v-text-field v-model="inviteEmail" label="E-mail du compte" type="email" variant="outlined" />
        <v-textarea v-model="inviteMessage" label="Message (facultatif)" rows="2" auto-grow variant="outlined" />
        <div class="d-flex justify-end ga-2">
          <v-btn variant="text" @click="inviteOpen = false">Annuler</v-btn>
          <v-btn color="primary" :loading="inviting" :disabled="!inviteEmail.includes('@')" @click="invite">Envoyer</v-btn>
        </div>
      </v-card>
    </v-dialog>

    <v-dialog :model-value="!!zoomed" max-width="900" @update:model-value="(v) => { if (!v) zoomed = null }">
      <img v-if="zoomed" :src="zoomed" alt="Document agrandi" class="zoomed" @click="zoomed = null" />
    </v-dialog>
  </div>
</template>

<style scoped>
.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.list {
  display: grid;
  gap: 8px;
}

.row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 12px 14px;
  text-align: left;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-md);
  background: var(--color-neutral-900);
  cursor: pointer;
}

.row:hover {
  border-color: var(--color-primary);
}

.row__main {
  flex: 1;
  min-width: 0;
}

.row__title {
  font-weight: 800;
  color: var(--color-neutral-200);
}

.detail__head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  padding: 18px 20px 12px;
  border-bottom: 1px solid var(--color-divider);
}

.detail__title {
  margin: 0;
  font-family: var(--font-heading);
  font-size: 19px;
  font-weight: 800;
}

.detail__body {
  padding: 14px 20px;
}

.detail__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  padding: 12px 20px 16px;
  border-top: 1px solid var(--color-divider);
}

.note {
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: var(--color-neutral-800);
  font-size: 13px;
}

.block {
  margin-bottom: 16px;
}

.block h3 {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--color-neutral-400);
}

.identity {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}

.portrait {
  flex: none;
  width: 96px;
  height: 124px;
  padding: 0;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-sm);
  overflow: hidden;
  background: var(--color-neutral-800);
  cursor: zoom-in;
}

.portrait img,
.thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.facts {
  display: grid;
  gap: 4px;
  margin: 0;
  font-size: 13px;
}

.facts > div {
  display: grid;
  grid-template-columns: 90px 1fr;
  gap: 8px;
}

.facts dt {
  color: var(--color-neutral-400);
}

.facts dd {
  margin: 0;
  color: var(--color-neutral-200);
}

.facts a {
  color: var(--color-primary);
}

.thumbs {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 8px;
}

.thumb {
  aspect-ratio: 4 / 3;
  padding: 0;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-sm);
  overflow: hidden;
  background: var(--color-neutral-800);
  cursor: zoom-in;
}

.thumb--doc {
  aspect-ratio: 16 / 10;
}

.zoomed {
  display: block;
  max-width: 100%;
  max-height: 85vh;
  margin: 0 auto;
  border-radius: var(--radius-md);
  cursor: zoom-out;
}

.dialog-title {
  margin: 0 0 10px;
  font-family: var(--font-heading);
  font-size: 18px;
  font-weight: 800;
}
</style>
