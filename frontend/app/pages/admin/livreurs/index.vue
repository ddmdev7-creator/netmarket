<script setup lang="ts">
import { PhImage, PhMagnifyingGlass, PhPlus, PhScales, PhStar, PhUserCircle } from '@phosphor-icons/vue'
import type { CourierAdminCreate, CourierDetailRead, CourierStatus } from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const { apiFetch, apiFetchBlob } = useApi()
const toast = useToastStore()

const tab = ref<CourierStatus>('pending')
const tabs: { value: CourierStatus; label: string }[] = [
  { value: 'pending', label: 'En attente' },
  { value: 'approved', label: 'Approuvés' },
  { value: 'rejected', label: 'Rejetés' },
  { value: 'suspended', label: 'Suspendus' },
]

const { data: couriers, pending, refresh } = await useAsyncData(
  'admin-couriers',
  () => apiFetch<CourierDetailRead[]>('/admin/couriers', { query: { status: tab.value } }),
  { default: () => [], getCachedData: () => undefined },
)
watch(tab, () => refresh())

// Vue carte : composant autonome (components/admin/CourierDeliveriesMap.vue),
// qui charge tous les livreurs approuvés + les courses en cours quel que soit
// l'onglet de statut ci-dessus.
const view = ref<'list' | 'map'>('list')

const search = ref('')
const visibleCouriers = computed(() => {
  const query = search.value.trim().toLowerCase()
  if (!query) return couriers.value
  return couriers.value.filter((c) =>
    [c.full_name ?? '', c.phone, c.zone ?? ''].join(' ').toLowerCase().includes(query),
  )
})

const statusMeta: Record<CourierStatus, { label: string; color: string }> = {
  pending: { label: 'En attente', color: 'warning' },
  approved: { label: 'Approuvé', color: 'success' },
  rejected: { label: 'Rejeté', color: 'error' },
  suspended: { label: 'Suspendu', color: 'error' },
}

const vehicleLabels: Record<string, string> = { moto: 'Moto', taxi: 'Taxi', voiture: 'Voiture' }
const idDocumentLabels: Record<string, string> = { cni_biometrique: "Carte d'identité biométrique", passeport: 'Passeport' }

// Comme pour /admin/vendeurs : la liste courante ne montre que le statut de
// l'onglet actif, donc après une action on retire l'élément localement
// plutôt que de re-filtrer côté client.
const updatingId = ref<string | null>(null)

async function update(courier: CourierDetailRead, status: CourierStatus, adminNote?: string) {
  updatingId.value = courier.id
  try {
    await apiFetch<CourierDetailRead>(`/admin/couriers/${courier.id}`, {
      method: 'PATCH',
      body: { status, ...(adminNote ? { admin_note: adminNote } : {}) },
    })
    if (status !== tab.value) {
      couriers.value = couriers.value.filter((c) => c.id !== courier.id)
    } else {
      await refresh()
    }
    toast.success('Livreur mis à jour.')
    rejectDialogId.value = null
    rejectNote.value = ''
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de mettre à jour ce livreur.'))
  } finally {
    updatingId.value = null
  }
}

const rejectDialogId = ref<string | null>(null)
const rejectNote = ref('')

function openRejectDialog(courierId: string) {
  rejectDialogId.value = courierId
  rejectNote.value = ''
}

function confirmReject() {
  const courier = couriers.value.find((c) => c.id === rejectDialogId.value)
  if (!courier || !rejectNote.value.trim()) return
  update(courier, 'rejected', rejectNote.value.trim())
}

// Vignettes de documents — chargées à la demande (pas au chargement de la
// liste) : chaque livreur en attente peut avoir jusqu'à 6 photos, et
// GET /couriers/{id}/documents/{key} n'est pas public (voir apiFetchBlob),
// donc pas de simple <img src> possible ici.
const expandedId = ref<string | null>(null)
const documentUrls = reactive<Record<string, string>>({})
const loadingDocuments = ref<string | null>(null)

// Vignette de profil affichée directement dans la liste pour les livreurs
// approuvés (voir <img> dans le template) -- chargée à part, pas au clic
// comme le reste des documents (toggleDocuments/openCompare plus bas) : sans
// ça, l'admin ne verrait jamais un visage tant qu'il n'a pas déplié "Voir les
// documents" sur chaque ligne. Réutilise le même cache documentUrls : si
// l'admin déplie ensuite les documents de ce livreur, la photo est déjà là.
watch(
  couriers,
  async (list) => {
    for (const c of list) {
      if (c.status !== 'approved' || !c.face_photo_key || documentUrls[c.face_photo_key]) continue
      try {
        const blob = await apiFetchBlob(`/couriers/${c.id}/documents/${c.face_photo_key}`)
        documentUrls[c.face_photo_key] = URL.createObjectURL(blob)
      } catch {
        // Pas grave — la ligne retombe sur l'icône générique.
      }
    }
  },
  { immediate: true },
)

interface DocEntry {
  label: string
  key: string
}

// Regroupées comme demandé : "Identification" (pièce d'identité + photo de
// visage) d'un côté, "Engin" de l'autre — deux groupes distincts plutôt
// qu'une seule grille mélangée, pour que l'admin valide chaque aspect
// séparément.
function identificationDocsFor(courier: CourierDetailRead): DocEntry[] {
  const entries: DocEntry[] = []
  if (courier.id_document_front_key) {
    entries.push({ label: idDocumentLabels[courier.id_document_type ?? ''] ?? 'Pièce (recto)', key: courier.id_document_front_key })
  }
  if (courier.id_document_back_key) entries.push({ label: 'Pièce (verso)', key: courier.id_document_back_key })
  if (courier.face_photo_key) entries.push({ label: 'Photo de visage', key: courier.face_photo_key })
  return entries
}

function vehicleDocsFor(courier: CourierDetailRead): DocEntry[] {
  return courier.vehicle_photo_keys.map((key, i) => ({ label: `Engin — photo ${i + 1}`, key }))
}

function allDocsFor(courier: CourierDetailRead): DocEntry[] {
  return [...identificationDocsFor(courier), ...vehicleDocsFor(courier)]
}

async function toggleDocuments(courier: CourierDetailRead) {
  if (expandedId.value === courier.id) {
    expandedId.value = null
    return
  }
  expandedId.value = courier.id
  loadingDocuments.value = courier.id
  try {
    for (const { key } of allDocsFor(courier)) {
      if (documentUrls[key]) continue
      const blob = await apiFetchBlob(`/couriers/${courier.id}/documents/${key}`)
      documentUrls[key] = URL.createObjectURL(blob)
    }
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de charger les documents.'))
  } finally {
    loadingDocuments.value = null
  }
}

onBeforeUnmount(() => {
  for (const url of Object.values(documentUrls)) URL.revokeObjectURL(url)
})

// Visionneuse plein cadre — les vignettes seules ne suffisent pas pour
// vérifier correctement une pièce d'identité ou une plaque d'immatriculation.
const viewerCourierId = ref<string | null>(null)
const viewerKey = ref<string | null>(null)

function openViewer(courierId: string, key: string) {
  viewerCourierId.value = courierId
  viewerKey.value = key
}

function closeViewer() {
  viewerCourierId.value = null
  viewerKey.value = null
}

const viewerCourier = computed(() => couriers.value.find((c) => c.id === viewerCourierId.value) ?? null)
const viewerList = computed(() => (viewerCourier.value ? allDocsFor(viewerCourier.value) : []))
const viewerIndex = computed(() => viewerList.value.findIndex((d) => d.key === viewerKey.value))
const viewerDoc = computed(() => viewerList.value[viewerIndex.value] ?? null)

function viewerPrev() {
  const i = viewerIndex.value
  if (i > 0) viewerKey.value = viewerList.value[i - 1]!.key
}

function viewerNext() {
  const i = viewerIndex.value
  if (i >= 0 && i < viewerList.value.length - 1) viewerKey.value = viewerList.value[i + 1]!.key
}

// Comparaison côte à côte pièce d'identité / photo de visage — vue
// d'ensemble rapide, indépendante de "Voir les documents" (pas besoin de
// tout déplier pour ce seul rapprochement).
function canCompare(courier: CourierDetailRead): boolean {
  return !!(courier.id_document_front_key && courier.face_photo_key)
}

const compareCourierId = ref<string | null>(null)
const compareLoading = ref<string | null>(null)
const compareCourier = computed(() => couriers.value.find((c) => c.id === compareCourierId.value) ?? null)

async function openCompare(courier: CourierDetailRead) {
  if (!canCompare(courier)) return
  compareCourierId.value = courier.id
  compareLoading.value = courier.id
  try {
    for (const key of [courier.id_document_front_key, courier.face_photo_key] as string[]) {
      if (documentUrls[key]) continue
      const blob = await apiFetchBlob(`/couriers/${courier.id}/documents/${key}`)
      documentUrls[key] = URL.createObjectURL(blob)
    }
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de charger les documents.'))
    compareCourierId.value = null
  } finally {
    compareLoading.value = null
  }
}

function closeCompare() {
  compareCourierId.value = null
}

const createOpen = ref(false)
const creating = ref(false)
const form = ref({ phone: '', email: '', firstName: '', lastName: '' })

function resetForm() {
  form.value = { phone: '', email: '', firstName: '', lastName: '' }
}

async function createCourier() {
  if (!/^\+224\d{9}$/.test(form.value.phone.trim())) {
    toast.error('Numéro invalide — format attendu : +224XXXXXXXXX.')
    return
  }
  if (!form.value.email.trim()) {
    toast.error("L'adresse email est obligatoire — c'est là qu'arrive l'invitation.")
    return
  }
  creating.value = true
  try {
    const payload: CourierAdminCreate = {
      phone: form.value.phone.trim(),
      email: form.value.email.trim(),
      first_name: form.value.firstName.trim() || undefined,
      last_name: form.value.lastName.trim() || undefined,
    }
    await apiFetch('/admin/couriers', { method: 'POST', body: payload })
    toast.success('Invitation envoyée par email.')
    createOpen.value = false
    resetForm()
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'envoyer cette invitation."))
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <div class="dashboard-shell">
    <div class="d-flex justify-space-between align-center mb-4">
      <h1 class="text-h6 mb-0">Livreurs</h1>
      <div class="d-flex align-center ga-2 flex-wrap justify-end">
        <AdminViewToggle v-model="view" />
        <v-btn size="small" color="primary" variant="tonal" @click="createOpen = true">
          <PhPlus :size="16" class="mr-1" />
          Créer un compte livreur
        </v-btn>
      </div>
    </div>

    <AdminCourierDeliveriesMap v-if="view === 'map'" />

    <template v-else>
    <v-btn-toggle v-model="tab" mandatory density="comfortable" divided class="mb-4 flex-wrap">
      <v-btn v-for="t in tabs" :key="t.value" :value="t.value" size="small">{{ t.label }}</v-btn>
    </v-btn-toggle>

    <v-text-field
      v-if="couriers.length > 0"
      v-model="search"
      placeholder="Rechercher par nom, téléphone ou zone…"
      density="compact"
      variant="outlined"
      hide-details
      clearable
      class="mb-4"
    >
      <template #prepend-inner>
        <PhMagnifyingGlass :size="16" color="var(--color-neutral-500)" />
      </template>
    </v-text-field>

    <CommonEmptyState v-if="!pending && couriers.length === 0" message="Aucun livreur dans cette catégorie." />
    <CommonEmptyState v-else-if="!pending && visibleCouriers.length === 0" message="Aucun livreur ne correspond à cette recherche." />

    <div class="couriers-grid">
    <v-card v-for="courier in visibleCouriers" :key="courier.id" class="mb-3 pa-3">
      <div class="d-flex justify-space-between align-center mb-1">
        <div class="d-flex align-center ga-2" style="min-width: 0">
          <div class="courier-avatar">
            <img
              v-if="courier.face_photo_key && documentUrls[courier.face_photo_key]"
              :src="documentUrls[courier.face_photo_key]"
              alt=""
            />
            <PhUserCircle v-else :size="18" color="var(--color-neutral-500)" />
          </div>
          <span style="font-weight: 600">{{ courier.full_name ?? courier.phone }}</span>
        </div>
        <v-chip :color="statusMeta[courier.status].color" size="small" variant="tonal">
          {{ statusMeta[courier.status].label }}
        </v-chip>
      </div>
      <div class="text-muted mb-2" style="font-size: 12.5px">
        {{ courier.phone }} · {{ vehicleLabels[courier.vehicle_type] }}<span v-if="courier.zone"> · {{ courier.zone }}</span>
      </div>
      <div v-if="courier.review_count > 0" class="d-flex align-center ga-1 mb-2">
        <PhStar
          v-for="n in 5"
          :key="n"
          :size="13"
          :weight="n <= Math.round(courier.average_rating ?? 0) ? 'fill' : 'regular'"
          color="var(--color-accent)"
        />
        <span class="text-muted" style="font-size: 11px">({{ courier.review_count }})</span>
      </div>

      <div v-if="courier.id_document_type" class="text-muted mb-1" style="font-size: 12px">
        Pièce : {{ idDocumentLabels[courier.id_document_type] }}
      </div>
      <div v-if="courier.vehicle_name" class="text-muted mb-1" style="font-size: 12px">
        Engin : {{ courier.vehicle_name }} · {{ courier.vehicle_plate_number }}
      </div>
      <div v-if="courier.admin_note" class="text-muted mb-2" style="font-size: 11.5px">
        Note admin : {{ courier.admin_note }}
      </div>

      <div class="d-flex ga-3 mb-2">
        <button
          v-if="allDocsFor(courier).length"
          type="button"
          class="doc-toggle"
          @click="toggleDocuments(courier)"
        >
          <PhImage :size="14" class="mr-1" style="vertical-align: -2px" />
          {{ expandedId === courier.id ? 'Masquer les documents' : 'Voir les documents' }}
        </button>

        <button
          v-if="canCompare(courier)"
          type="button"
          class="doc-toggle"
          :disabled="compareLoading === courier.id"
          @click="openCompare(courier)"
        >
          <PhScales :size="14" class="mr-1" style="vertical-align: -2px" />
          {{ compareLoading === courier.id ? 'Chargement…' : 'Comparer' }}
        </button>
      </div>

      <div v-if="expandedId === courier.id" class="mb-3">
        <v-progress-circular v-if="loadingDocuments === courier.id" indeterminate size="20" color="primary" />
        <template v-else>
          <template v-if="identificationDocsFor(courier).length">
            <div class="doc-group-title">Identification</div>
            <div class="doc-preview-grid mb-3">
              <button
                v-for="doc in identificationDocsFor(courier)"
                :key="doc.key"
                type="button"
                class="doc-preview-grid__item"
                @click="openViewer(courier.id, doc.key)"
              >
                <img v-if="documentUrls[doc.key]" :src="documentUrls[doc.key]" :alt="doc.label" />
                <span class="doc-preview-grid__label">{{ doc.label }}</span>
              </button>
            </div>
          </template>

          <template v-if="vehicleDocsFor(courier).length">
            <div class="doc-group-title">Engin</div>
            <div class="doc-preview-grid mb-3">
              <button
                v-for="doc in vehicleDocsFor(courier)"
                :key="doc.key"
                type="button"
                class="doc-preview-grid__item"
                @click="openViewer(courier.id, doc.key)"
              >
                <img v-if="documentUrls[doc.key]" :src="documentUrls[doc.key]" :alt="doc.label" />
                <span class="doc-preview-grid__label">{{ doc.label }}</span>
              </button>
            </div>
          </template>
        </template>
      </div>

      <div class="d-flex ga-2">
        <template v-if="courier.status === 'pending'">
          <v-btn color="primary" size="small" class="flex-grow-1" :loading="updatingId === courier.id" @click="update(courier, 'approved')">
            Approuver
          </v-btn>
          <v-btn color="error" variant="outlined" size="small" class="flex-grow-1" :loading="updatingId === courier.id" @click="openRejectDialog(courier.id)">
            Rejeter
          </v-btn>
        </template>
        <v-btn v-else-if="courier.status === 'approved'" color="error" variant="outlined" size="small" class="flex-grow-1" :loading="updatingId === courier.id" @click="update(courier, 'suspended')">
          Suspendre
        </v-btn>
        <v-btn v-else color="primary" size="small" class="flex-grow-1" :loading="updatingId === courier.id" @click="update(courier, 'approved')">
          Réactiver
        </v-btn>
      </div>
    </v-card>
    </div>
    </template>

    <v-dialog :model-value="!!viewerCourierId" max-width="480" @update:model-value="(v) => !v && closeViewer()">
      <v-card class="pa-3">
        <div class="d-flex justify-space-between align-center mb-2">
          <span style="font-size: 13px; font-weight: 600">{{ viewerDoc?.label }}</span>
          <span class="text-muted" style="font-size: 11.5px">{{ viewerIndex + 1 }} / {{ viewerList.length }}</span>
        </div>
        <img v-if="viewerDoc && documentUrls[viewerDoc.key]" :src="documentUrls[viewerDoc.key]" class="viewer-image mb-3" :alt="viewerDoc.label" />
        <div class="d-flex ga-2">
          <v-btn variant="outlined" size="small" class="flex-grow-1" :disabled="viewerIndex <= 0" @click="viewerPrev">Précédent</v-btn>
          <v-btn variant="outlined" size="small" class="flex-grow-1" :disabled="viewerIndex >= viewerList.length - 1" @click="viewerNext">Suivant</v-btn>
          <v-btn variant="text" size="small" @click="closeViewer">Fermer</v-btn>
        </div>
      </v-card>
    </v-dialog>

    <v-dialog :model-value="!!compareCourierId" max-width="480" @update:model-value="(v) => !v && closeCompare()">
      <v-card class="pa-3">
        <div class="text-subtitle-2 mb-3">Pièce d'identité vs photo de visage</div>
        <div class="compare-grid mb-3">
          <div class="compare-grid__item">
            <span class="doc-preview-grid__label mb-1">{{ idDocumentLabels[compareCourier?.id_document_type ?? ''] ?? "Pièce d'identité" }}</span>
            <img v-if="compareCourier && documentUrls[compareCourier.id_document_front_key ?? '']" :src="documentUrls[compareCourier.id_document_front_key ?? '']" class="compare-grid__image" alt="Pièce d'identité" />
          </div>
          <div class="compare-grid__item">
            <span class="doc-preview-grid__label mb-1">Photo de visage</span>
            <img v-if="compareCourier && documentUrls[compareCourier.face_photo_key ?? '']" :src="documentUrls[compareCourier.face_photo_key ?? '']" class="compare-grid__image" alt="Photo de visage" />
          </div>
        </div>
        <v-btn variant="outlined" size="small" block @click="closeCompare">Fermer</v-btn>
      </v-card>
    </v-dialog>

    <v-dialog :model-value="!!rejectDialogId" max-width="360" @update:model-value="(v) => !v && (rejectDialogId = null)">
      <v-card class="pa-5">
        <div class="text-subtitle-1 mb-2">Motif du refus</div>
        <p class="text-muted mb-3" style="font-size: 12.5px">
          Le livreur reçoit ce motif par notification — sois précis (ex. « photo de visage illisible », « plaque non
          visible sur les photos de l'engin »).
        </p>
        <v-textarea v-model="rejectNote" rows="3" placeholder="Motif du refus" class="mb-3" />
        <div class="d-flex ga-2">
          <v-btn variant="outlined" class="flex-grow-1" @click="rejectDialogId = null">Annuler</v-btn>
          <v-btn color="error" class="flex-grow-1" :disabled="!rejectNote.trim()" :loading="!!updatingId" @click="confirmReject">
            Refuser
          </v-btn>
        </div>
      </v-card>
    </v-dialog>

    <v-dialog v-model="createOpen" max-width="520">
      <v-card class="pa-5">
        <h2 class="text-h6 mb-2">Inviter un livreur</h2>
        <p class="text-muted mb-4" style="font-size: 12.5px; line-height: 1.5">
          Un email d'activation sera envoyé à ce livreur pour définir son mot de passe et compléter lui-même son
          profil (pièce d'identité, informations du véhicule). Son compte apparaîtra ici, dans « En attente »,
          une fois ce profil soumis — c'est à ce moment-là que tu pourras l'approuver.
        </p>

        <v-form @submit.prevent="createCourier">
          <div class="d-flex ga-3">
            <div class="flex-grow-1">
              <label class="field-label">Téléphone</label>
              <v-text-field v-model="form.phone" placeholder="+224621234567" class="mb-3" />
            </div>
            <div class="flex-grow-1">
              <label class="field-label">Email</label>
              <v-text-field v-model="form.email" type="email" placeholder="livreur@email.com" class="mb-3" />
            </div>
          </div>

          <div class="d-flex ga-3">
            <div class="flex-grow-1">
              <label class="field-label">Prénom (optionnel)</label>
              <v-text-field v-model="form.firstName" class="mb-3" />
            </div>
            <div class="flex-grow-1">
              <label class="field-label">Nom (optionnel)</label>
              <v-text-field v-model="form.lastName" class="mb-3" />
            </div>
          </div>

          <div class="d-flex ga-2">
            <v-btn variant="outlined" class="flex-grow-1" @click="createOpen = false">Annuler</v-btn>
            <v-btn type="submit" color="primary" class="flex-grow-1" :loading="creating">Envoyer l'invitation</v-btn>
          </div>
        </v-form>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
/* Même recette que .sub-order-grid (pages/vendeur/commandes/index.vue) :
   une colonne pleine largeur reste illisible passé 960px sur .dashboard-shell
   (jusqu'à 1400px) — auto-fill plutôt qu'un nombre de colonnes fixe, pour
   s'adapter à la largeur réelle disponible. */
.couriers-grid {
  display: grid;
  grid-template-columns: 1fr;
  align-items: start;
  gap: 0;
}

@media (min-width: 960px) {
  .couriers-grid {
    grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
    gap: 0 16px;
  }
}

.courier-avatar {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--color-neutral-800);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.courier-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.doc-toggle {
  display: inline-flex;
  align-items: center;
  background: none;
  border: none;
  color: var(--color-primary-300);
  font-size: 12px;
  font-weight: 600;
  padding: 0;
  cursor: pointer;
}

.doc-group-title {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-neutral-500);
  margin-bottom: 6px;
}

.doc-preview-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.doc-preview-grid__item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
}

.doc-preview-grid__item img {
  width: 100%;
  aspect-ratio: 1 / 1;
  object-fit: cover;
  border-radius: var(--radius-sm);
  background: var(--color-neutral-800);
}

.doc-preview-grid__label {
  font-size: 10px;
  color: var(--color-neutral-500);
  text-align: center;
}

.viewer-image {
  width: 100%;
  max-height: 70vh;
  object-fit: contain;
  border-radius: var(--radius-sm);
  background: var(--color-neutral-800);
}

.compare-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.compare-grid__item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.compare-grid__image {
  width: 100%;
  aspect-ratio: 3 / 4;
  object-fit: contain;
  border-radius: var(--radius-sm);
  background: var(--color-neutral-800);
}
</style>
