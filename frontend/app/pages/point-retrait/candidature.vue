<script setup lang="ts">
/**
 * Candidature d'un acheteur pour devenir gestionnaire de point de retrait
 * (spontanée, ou suite à une invitation de l'admin). Dossier en 4 étapes,
 * enregistré en brouillon à tout moment, puis soumis à l'admin qui valide,
 * renvoie pour correction (motif + suggestion) ou refuse définitivement.
 * Backend : app/pickup_point_applications.
 */
import {
  PhArrowLeft,
  PhCheckCircle,
  PhClock,
  PhIdentificationCard,
  PhImage,
  PhInfo,
  PhMapPin,
  PhProhibit,
  PhStorefront,
  PhTrash,
  PhUser,
  PhWarningCircle,
} from '@phosphor-icons/vue'
import type {
  MyPickupApplicationState,
  PickupApplicationDraft,
  PickupApplicationRead,
  PickupApplicationSlot,
} from '~/types/api'

definePageMeta({ middleware: 'auth', layout: 'blank' })

const router = useRouter()
const auth = useAuthStore()
const { apiFetch, apiFetchBlob } = useApi()
const toast = useToastStore()

const { data: state, refresh } = await useAsyncData(
  'my-pickup-application',
  () => apiFetch<MyPickupApplicationState>('/pickup-point-applications/me'),
  { getCachedData: hydrateThenRefetch },
)

const application = computed<PickupApplicationRead | null>(() => state.value?.application ?? null)
const editable = computed(
  () => !!state.value?.can_apply && (!application.value || ['draft', 'changes_requested'].includes(application.value.status)),
)

function emptyDraft(): PickupApplicationDraft {
  return {
    first_name: auth.user?.first_name ?? null,
    last_name: auth.user?.last_name ?? null,
    birth_date: null,
    residence_address: null,
    id_document_type: 'cni_biometrique',
    id_document_number: null,
    id_document_front_key: null,
    id_document_back_key: null,
    portrait_photo_key: null,
    point_name: null,
    point_address: null,
    point_landmark: null,
    latitude: null,
    longitude: null,
    opening_hours: null,
    storage_capacity: null,
    premises_photo_keys: [],
  }
}

const form = reactive<PickupApplicationDraft>(emptyDraft())
function fillForm(source: PickupApplicationRead | null) {
  const base = emptyDraft()
  for (const key of Object.keys(base) as (keyof PickupApplicationDraft)[]) {
    // @ts-expect-error — affectation champ à champ entre deux formes compatibles
    form[key] = source ? (source[key] ?? base[key]) : base[key]
  }
  form.premises_photo_keys = [...(source?.premises_photo_keys ?? [])]
}
watch(application, (value) => fillForm(value), { immediate: true })

// --- Aperçus des documents -------------------------------------------------------
// Un document déjà enregistré n'est jamais public : on le relit en blob.

const previews = reactive<Record<string, string>>({})
async function ensurePreview(key: string | null) {
  if (!key || previews[key] || !application.value) return
  try {
    const blob = await apiFetchBlob(`/pickup-point-applications/${application.value.id}/documents/${key}`)
    previews[key] = URL.createObjectURL(blob)
  } catch {
    // Pas bloquant : la vignette reste vide.
  }
}
watch(
  () => [form.id_document_front_key, form.id_document_back_key, form.portrait_photo_key, ...form.premises_photo_keys],
  (keys) => keys.forEach((k) => ensurePreview(k as string | null)),
  { immediate: true },
)
onBeforeUnmount(() => Object.values(previews).forEach((url) => URL.revokeObjectURL(url)))

// --- Envoi des fichiers -----------------------------------------------------------

const uploading = ref<PickupApplicationSlot | null>(null)
async function upload(slot: PickupApplicationSlot, files: FileList | null) {
  if (!files?.length) return
  const selected = Array.from(files)
  if (slot === 'premises') {
    const room = (state.value?.max_premises_photos ?? 8) - form.premises_photo_keys.length
    if (selected.length > room) {
      toast.error(`Tu peux encore ajouter ${room} photo(s) du local.`)
      return
    }
  }
  const body = new FormData()
  body.append('slot', slot)
  selected.forEach((file) => body.append('files', file))
  uploading.value = slot
  try {
    const { keys } = await apiFetch<{ keys: string[] }>('/pickup-point-applications/me/documents', { method: 'POST', body })
    keys.forEach((key, i) => {
      const file = selected[i]
      if (file) previews[key] = URL.createObjectURL(file)
    })
    if (slot === 'premises') form.premises_photo_keys = [...form.premises_photo_keys, ...keys]
    else if (slot === 'id_front') form.id_document_front_key = keys[0] ?? null
    else if (slot === 'id_back') form.id_document_back_key = keys[0] ?? null
    else form.portrait_photo_key = keys[0] ?? null
    await save(false)
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'envoyer ce fichier."))
  } finally {
    uploading.value = null
  }
}

function removePremises(key: string) {
  form.premises_photo_keys = form.premises_photo_keys.filter((k) => k !== key)
}

// --- Enregistrement / soumission ------------------------------------------------------

const saving = ref(false)
const submitting = ref(false)

async function save(announce = true) {
  saving.value = true
  try {
    const body = { ...form, storage_capacity: form.storage_capacity ? Number(form.storage_capacity) : null }
    const saved = await apiFetch<PickupApplicationRead>('/pickup-point-applications/me', { method: 'PUT', body })
    if (state.value) state.value = { ...state.value, application: saved }
    if (announce) toast.success('Brouillon enregistré.')
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'enregistrer le dossier."))
    throw e
  } finally {
    saving.value = false
  }
}

const missing = computed(() => {
  const list: string[] = []
  if (!form.first_name || !form.last_name) list.push('Nom et prénom')
  if (!form.birth_date) list.push('Date de naissance')
  if (!form.residence_address) list.push('Adresse personnelle')
  if (!form.id_document_number) list.push('Numéro de pièce')
  if (!form.id_document_front_key) list.push("Pièce d'identité (recto)")
  if (form.id_document_type === 'cni_biometrique' && !form.id_document_back_key) list.push("Pièce d'identité (verso)")
  if (!form.portrait_photo_key) list.push("Photo d'identité")
  if (!form.point_name || !form.point_address) list.push('Nom et adresse du point')
  if (form.latitude == null || form.longitude == null) list.push('Position sur la carte')
  if (!form.opening_hours) list.push("Horaires d'ouverture")
  const min = state.value?.min_premises_photos ?? 4
  if (form.premises_photo_keys.length < min) list.push(`${min} photos du local (${form.premises_photo_keys.length}/${min})`)
  return list
})

const confirmOpen = ref(false)
async function submit() {
  submitting.value = true
  try {
    await save(false)
    await apiFetch('/pickup-point-applications/me/submit', { method: 'POST' })
    confirmOpen.value = false
    toast.success("Dossier envoyé ! L'équipe Ndjouri va l'examiner.")
    await refresh()
    window.scrollTo({ top: 0, behavior: 'smooth' })
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'envoyer le dossier."))
  } finally {
    submitting.value = false
  }
}

const STEPS = [
  { key: 'identity', label: 'Identité', icon: PhUser },
  { key: 'documents', label: 'Pièces', icon: PhIdentificationCard },
  { key: 'point', label: 'Point', icon: PhMapPin },
  { key: 'premises', label: 'Local', icon: PhStorefront },
]

function formatDate(iso: string | null) {
  return iso ? new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' }) : ''
}
</script>

<template>
  <div class="app-shell" style="padding-bottom: 96px">
    <div class="d-flex align-center pa-2 ga-2">
      <v-btn icon variant="text" @click="router.back()"><PhArrowLeft :size="20" /></v-btn>
      <h1 class="text-h6">Devenir point de retrait</h1>
      <LayoutHomeLink />
    </div>

    <div class="px-4 cand">
      <template v-if="state">
        <!-- États qui ne laissent pas modifier le dossier -->
        <section v-if="application?.status === 'approved'" class="banner banner--ok">
          <PhCheckCircle :size="22" weight="fill" />
          <div>
            <strong>Votre point de retrait est validé.</strong>
            <p>Reconnectez-vous si besoin puis ouvrez votre espace gestionnaire.</p>
            <v-btn color="primary" size="small" to="/point-retrait" class="mt-2">Ouvrir mon espace</v-btn>
          </div>
        </section>

        <section v-else-if="application?.status === 'rejected'" class="banner banner--ko">
          <PhProhibit :size="22" weight="fill" />
          <div>
            <strong>Votre candidature a été refusée.</strong>
            <p v-if="application.admin_note">Motif : {{ application.admin_note }}</p>
            <p>Ce refus est définitif pour ce compte.</p>
          </div>
        </section>

        <section v-else-if="!state.can_apply" class="banner banner--ko">
          <PhWarningCircle :size="22" weight="fill" />
          <div><strong>{{ state.blocked_reason }}</strong></div>
        </section>

        <section v-else-if="application?.status === 'submitted'" class="banner banner--wait">
          <PhClock :size="22" weight="fill" />
          <div>
            <strong>Dossier en cours d'examen</strong>
            <p>Envoyé le {{ formatDate(application.submitted_at) }}. Vous serez prévenu par notification et par e-mail.</p>
          </div>
        </section>

        <template v-else>
          <section v-if="application?.status === 'changes_requested'" class="banner banner--warn">
            <PhWarningCircle :size="22" weight="fill" />
            <div>
              <strong>Votre dossier est à corriger</strong>
              <p>Motif : {{ application.admin_note }}</p>
              <p v-if="application.admin_suggestion"><em>Suggestion : {{ application.admin_suggestion }}</em></p>
            </div>
          </section>
          <section v-else-if="application?.origin === 'invited'" class="banner banner--info">
            <PhInfo :size="22" weight="fill" />
            <div><strong>L'équipe Ndjouri vous a invité à devenir point de retrait.</strong></div>
          </section>
          <section v-else class="intro">
            <p>
              Recevez les colis des clients de votre quartier dans votre local et soyez rémunéré pour chaque colis
              remis. Complétez votre dossier : il sera vérifié par l'équipe Ndjouri.
            </p>
          </section>

          <ol class="steps" aria-label="Étapes du dossier">
            <li v-for="(step, i) in STEPS" :key="step.key">
              <a :href="`#${step.key}`"><component :is="step.icon" :size="16" /> {{ i + 1 }}. {{ step.label }}</a>
            </li>
          </ol>
        </template>

        <!-- Le formulaire (lecture seule si non modifiable) -->
        <fieldset v-if="application || editable" class="cand__form" :disabled="!editable">
          <section id="identity" class="card">
            <h2 class="card__title"><PhUser :size="18" /> 1. Identité</h2>
            <div class="grid-2">
              <v-text-field v-model="form.first_name" label="Prénom" variant="outlined" />
              <v-text-field v-model="form.last_name" label="Nom" variant="outlined" />
              <v-text-field v-model="form.birth_date" label="Date de naissance" type="date" variant="outlined" />
              <v-text-field v-model="form.residence_address" label="Adresse personnelle" variant="outlined" />
            </div>
          </section>

          <section id="documents" class="card">
            <h2 class="card__title"><PhIdentificationCard :size="18" /> 2. Pièce d'identité et photo</h2>
            <div class="grid-2">
              <v-select
                v-model="form.id_document_type"
                :items="[{ value: 'cni_biometrique', title: 'Carte d’identité biométrique' }, { value: 'passeport', title: 'Passeport' }]"
                label="Type de pièce"
                variant="outlined"
              />
              <v-text-field v-model="form.id_document_number" label="Numéro de la pièce" variant="outlined" />
            </div>
            <div class="docs">
              <label class="doc" :class="{ 'doc--filled': form.id_document_front_key }">
                <img v-if="form.id_document_front_key && previews[form.id_document_front_key]" :src="previews[form.id_document_front_key]" alt="Recto" />
                <span v-else class="doc__empty"><PhImage :size="22" />Recto</span>
                <span class="doc__label">{{ uploading === 'id_front' ? 'Envoi…' : form.id_document_type === 'passeport' ? 'Page photo' : 'Recto' }}</span>
                <input type="file" accept="image/*" hidden @change="upload('id_front', ($event.target as HTMLInputElement).files)" />
              </label>
              <label v-if="form.id_document_type === 'cni_biometrique'" class="doc" :class="{ 'doc--filled': form.id_document_back_key }">
                <img v-if="form.id_document_back_key && previews[form.id_document_back_key]" :src="previews[form.id_document_back_key]" alt="Verso" />
                <span v-else class="doc__empty"><PhImage :size="22" />Verso</span>
                <span class="doc__label">{{ uploading === 'id_back' ? 'Envoi…' : 'Verso' }}</span>
                <input type="file" accept="image/*" hidden @change="upload('id_back', ($event.target as HTMLInputElement).files)" />
              </label>
              <label class="doc doc--portrait" :class="{ 'doc--filled': form.portrait_photo_key }">
                <img v-if="form.portrait_photo_key && previews[form.portrait_photo_key]" :src="previews[form.portrait_photo_key]" alt="Photo d'identité" />
                <span v-else class="doc__empty"><PhUser :size="22" />Photo</span>
                <span class="doc__label">{{ uploading === 'portrait' ? 'Envoi…' : "Photo d'identité" }}</span>
                <input type="file" accept="image/*" hidden @change="upload('portrait', ($event.target as HTMLInputElement).files)" />
              </label>
            </div>
            <p class="hint">
              Photo d'identité : de face, <strong>fond blanc uni</strong>, format portrait type carte d'identité, en haute
              définition (au moins {{ state.portrait_min_width }} × {{ state.portrait_min_height }} px). Elle est vérifiée
              à l'envoi.
            </p>
          </section>

          <section id="point" class="card">
            <h2 class="card__title"><PhMapPin :size="18" /> 3. Le point de retrait</h2>
            <div class="grid-2">
              <v-text-field v-model="form.point_name" label="Nom du point (ex. Boutique Kipé Relais)" variant="outlined" />
              <v-text-field v-model="form.opening_hours" label="Horaires (ex. Lun–Sam 8h–20h)" variant="outlined" />
              <v-text-field v-model="form.point_address" label="Adresse (commune, quartier, rue)" variant="outlined" />
              <v-text-field v-model="form.point_landmark" label="Repère (ex. face à la pharmacie)" variant="outlined" />
              <v-text-field v-model="form.storage_capacity" label="Colis stockables en même temps" type="number" variant="outlined" />
            </div>
            <p class="hint mb-2">Placez le point exactement sur la carte : c'est là que les livreurs viendront déposer les colis.</p>
            <CommonMapPicker v-model:latitude="form.latitude" v-model:longitude="form.longitude" />
          </section>

          <section id="premises" class="card">
            <h2 class="card__title"><PhStorefront :size="18" /> 4. Photos du local</h2>
            <p class="hint">
              Au moins {{ state.min_premises_photos }} photos différentes (jusqu'à {{ state.max_premises_photos }}) :
              façade, entrée, espace de stockage, comptoir…
            </p>
            <div class="premises">
              <div v-for="key in form.premises_photo_keys" :key="key" class="premises__item">
                <img v-if="previews[key]" :src="previews[key]" alt="Photo du local" />
                <button v-if="editable" type="button" class="premises__remove" aria-label="Retirer la photo" @click="removePremises(key)">
                  <PhTrash :size="14" />
                </button>
              </div>
              <label v-if="editable && form.premises_photo_keys.length < state.max_premises_photos" class="premises__add">
                <PhImage :size="22" />
                <span>{{ uploading === 'premises' ? 'Envoi…' : 'Ajouter' }}</span>
                <input type="file" accept="image/*" multiple hidden @change="upload('premises', ($event.target as HTMLInputElement).files)" />
              </label>
            </div>
            <p class="counter">{{ form.premises_photo_keys.length }} / {{ state.min_premises_photos }} minimum</p>
          </section>
        </fieldset>
      </template>
    </div>

    <div v-if="state && editable" class="cand-bar">
      <v-btn variant="outlined" :loading="saving" @click="save()">Enregistrer</v-btn>
      <v-btn color="primary" class="flex-grow-1" @click="confirmOpen = true">Envoyer mon dossier</v-btn>
    </div>

    <v-dialog v-model="confirmOpen" max-width="440">
      <v-card class="pa-5">
        <h2 class="dialog-title">Envoyer le dossier ?</h2>
        <template v-if="missing.length">
          <p class="text-meta mb-2">Il manque encore :</p>
          <ul class="missing">
            <li v-for="m in missing" :key="m"><PhWarningCircle :size="14" /> {{ m }}</li>
          </ul>
        </template>
        <p v-else class="text-meta">
          Votre dossier est complet. Une fois envoyé, il ne sera plus modifiable pendant son examen.
        </p>
        <div class="d-flex justify-end ga-2 mt-4">
          <v-btn variant="text" @click="confirmOpen = false">Continuer</v-btn>
          <v-btn color="primary" :disabled="missing.length > 0" :loading="submitting" @click="submit">Envoyer</v-btn>
        </div>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.cand {
  max-width: 760px;
  margin: 0 auto;
}

.cand__form {
  border: none;
  margin: 0;
  padding: 0;
  min-width: 0;
}

.intro p {
  margin: 0 0 12px;
  font-size: 14px;
  color: var(--color-neutral-300);
}

.banner {
  display: flex;
  gap: 12px;
  padding: 14px 16px;
  margin-bottom: 14px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-divider);
  background: var(--color-neutral-900);
  font-size: 13.5px;
}

.banner svg {
  flex: none;
  margin-top: 1px;
}

.banner p {
  margin: 4px 0 0;
  color: var(--color-neutral-300);
}

.banner--ok svg {
  color: var(--color-success);
}

.banner--ko svg {
  color: var(--color-error);
}

.banner--warn svg,
.banner--wait svg {
  color: var(--color-accent);
}

.banner--info svg {
  color: var(--color-primary);
}

.steps {
  display: flex;
  gap: 6px;
  margin: 0 0 14px;
  padding: 0;
  list-style: none;
  overflow-x: auto;
}

.steps a {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid var(--color-divider);
  font-size: 12.5px;
  font-weight: 600;
  white-space: nowrap;
  color: var(--color-neutral-300);
  text-decoration: none;
}

.card {
  margin-bottom: 14px;
  padding: 16px;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-md);
  background: var(--color-neutral-900);
  scroll-margin-top: 12px;
}

.card__title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 14px;
  font-family: var(--font-heading);
  font-size: 16px;
  font-weight: 800;
}

.grid-2 {
  display: grid;
  grid-template-columns: 1fr;
  column-gap: 12px;
}

@media (min-width: 600px) {
  .grid-2 {
    grid-template-columns: 1fr 1fr;
  }
}

.docs {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.doc {
  position: relative;
  width: 150px;
  height: 100px;
  border: 1.5px dashed var(--color-divider-strong, var(--color-divider));
  border-radius: var(--radius-sm);
  overflow: hidden;
  cursor: pointer;
  background: var(--color-neutral-800);
}

.doc--portrait {
  width: 90px;
  height: 116px;
}

.doc--filled {
  border-style: solid;
  border-color: var(--color-primary);
}

.doc img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.doc__empty {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  font-size: 12px;
  color: var(--color-neutral-400);
}

.doc__label {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 3px 6px;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  background: rgba(0, 0, 0, 0.55);
}

.hint {
  margin: 10px 0 0;
  font-size: 12.5px;
  color: var(--color-neutral-400);
}

.premises {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
  gap: 8px;
  margin-top: 10px;
}

.premises__item,
.premises__add {
  position: relative;
  aspect-ratio: 1;
  border-radius: var(--radius-sm);
  overflow: hidden;
  background: var(--color-neutral-800);
}

.premises__item img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.premises__remove {
  position: absolute;
  top: 4px;
  right: 4px;
  display: flex;
  padding: 5px;
  border: none;
  border-radius: 50%;
  color: #fff;
  background: rgba(0, 0, 0, 0.6);
  cursor: pointer;
}

.premises__add {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  border: 1.5px dashed var(--color-divider);
  font-size: 12px;
  color: var(--color-neutral-400);
  cursor: pointer;
}

.counter {
  margin: 8px 0 0;
  font-size: 12px;
  font-weight: 700;
  color: var(--color-neutral-400);
}

.cand-bar {
  position: fixed;
  left: 50%;
  bottom: 0;
  transform: translateX(-50%);
  width: 100%;
  max-width: 760px;
  display: flex;
  gap: 8px;
  padding: 10px 16px calc(12px + env(safe-area-inset-bottom, 0px));
  background: var(--color-neutral-900);
  border-top: 1px solid var(--color-divider);
  z-index: 5;
}

.dialog-title {
  margin: 0 0 12px;
  font-family: var(--font-heading);
  font-size: 18px;
  font-weight: 800;
}

.missing {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 4px;
  font-size: 13px;
}

.missing li {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--color-accent);
}
</style>
