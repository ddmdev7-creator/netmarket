<script setup lang="ts">
import { PhArrowLeft, PhSpinner, PhUploadSimple, PhX } from '@phosphor-icons/vue'
import type { Ref } from 'vue'
import type { CourierDetailRead, CourierDocumentSlot, CourierRegister, IdDocumentType, VehicleType } from '~/types/api'

definePageMeta({ middleware: 'auth', layout: 'blank' })

const auth = useAuthStore()
const router = useRouter()
const { apiFetch } = useApi()
const toast = useToastStore()

if (auth.user?.role === 'courier') {
  await router.replace('/livreur')
}

const vehicleType = ref<VehicleType>('moto')
const zone = ref('')
const submitting = ref(false)

const vehicleOptions = [
  { title: 'Moto', value: 'moto' },
  { title: 'Taxi', value: 'taxi' },
  { title: 'Voiture', value: 'voiture' },
]

const idDocumentType = ref<IdDocumentType>('cni_biometrique')
const idDocumentOptions = [
  { title: "Carte d'identité biométrique", value: 'cni_biometrique' },
  { title: 'Passeport', value: 'passeport' },
]

const vehicleName = ref('')
const vehiclePlateNumber = ref('')

// Un slot = un document unique (recto/verso/visage) ; on garde le fichier
// choisi (pour l'aperçu local, pas besoin de re-télécharger ce qu'on vient
// d'envoyer) et la clé renvoyée par le serveur une fois uploadé.
interface SlotState {
  file: File | null
  previewUrl: string | null
  key: string | null
  uploading: boolean
}

function emptySlot(): SlotState {
  return { file: null, previewUrl: null, key: null, uploading: false }
}

const idFront = ref<SlotState>(emptySlot())
const idBack = ref<SlotState>(emptySlot())
const face = ref<SlotState>(emptySlot())
const vehiclePhotos = ref<SlotState[]>([])

const idFrontInput = ref<HTMLInputElement | null>(null)
const idBackInput = ref<HTMLInputElement | null>(null)
const faceInput = ref<HTMLInputElement | null>(null)
const vehicleInput = ref<HTMLInputElement | null>(null)

async function uploadToSlot(file: File, slot: CourierDocumentSlot): Promise<string> {
  const formData = new FormData()
  formData.append('slot', slot)
  formData.append('files', file)
  const { keys } = await apiFetch<{ keys: string[] }>('/couriers/me/documents', { method: 'POST', body: formData })
  return keys[0]!
}

async function handleSingleFile(file: File, slot: CourierDocumentSlot, target: Ref<SlotState>) {
  if (target.value.previewUrl) URL.revokeObjectURL(target.value.previewUrl)
  target.value = { file, previewUrl: URL.createObjectURL(file), key: null, uploading: true }
  try {
    target.value.key = await uploadToSlot(file, slot)
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'envoyer ce document."))
    target.value = emptySlot()
  } finally {
    target.value.uploading = false
  }
}

// Handlers dédiés par slot plutôt qu'un seul générique recevant le ref en
// paramètre de template : un ref de <script setup> référencé dans le
// template est auto-déballé par Vue (idFront y vaut idFront.value, pas le
// Ref lui-même) — passer directement le ref en argument depuis le template
// ne fonctionne donc pas, il faut fermer dessus ici, côté script.
function onIdFrontSelected(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  ;(event.target as HTMLInputElement).value = ''
  if (file) handleSingleFile(file, 'id_front', idFront)
}

function onIdBackSelected(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  ;(event.target as HTMLInputElement).value = ''
  if (file) handleSingleFile(file, 'id_back', idBack)
}

function onFaceSelected(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  ;(event.target as HTMLInputElement).value = ''
  if (file) handleSingleFile(file, 'face', face)
}

const MAX_VEHICLE_PHOTOS = 4

async function onVehicleFilesSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const files = input.files ? Array.from(input.files) : []
  input.value = ''
  const remaining = MAX_VEHICLE_PHOTOS - vehiclePhotos.value.length
  if (files.length > remaining) {
    toast.error(`Maximum ${MAX_VEHICLE_PHOTOS} photos de l'engin — ${remaining} de plus possible(s).`)
  }
  for (const file of files.slice(0, remaining)) {
    // Mutations ci-dessous passent par l'index dans vehiclePhotos.value (pas
    // par la référence locale `slot`) : Vue ne suit les changements que via
    // le proxy réactif du tableau, pas via l'objet brut d'origine.
    const index = vehiclePhotos.value.push({ file, previewUrl: URL.createObjectURL(file), key: null, uploading: true }) - 1
    try {
      vehiclePhotos.value[index]!.key = await uploadToSlot(file, 'vehicle')
    } catch (e) {
      toast.error(apiErrorMessage(e, "Impossible d'envoyer cette photo."))
      vehiclePhotos.value.splice(index, 1)
      continue
    } finally {
      const slot = vehiclePhotos.value[index]
      if (slot) slot.uploading = false
    }
  }
}

function removeVehiclePhoto(index: number) {
  const [removed] = vehiclePhotos.value.splice(index, 1)
  if (removed?.previewUrl) URL.revokeObjectURL(removed.previewUrl)
}

const backRequired = computed(() => idDocumentType.value === 'cni_biometrique')

const canSubmit = computed(() => {
  if (!idFront.value.key || !face.value.key) return false
  if (backRequired.value && !idBack.value.key) return false
  if (!vehicleName.value.trim() || !vehiclePlateNumber.value.trim()) return false
  if (vehiclePhotos.value.length === 0 || vehiclePhotos.value.some((p) => p.uploading)) return false
  if (idFront.value.uploading || face.value.uploading || idBack.value.uploading) return false
  return true
})

async function submit() {
  if (!canSubmit.value) return
  submitting.value = true
  try {
    const payload: CourierRegister = {
      vehicle_type: vehicleType.value,
      zone: zone.value.trim() || undefined,
      id_document_type: idDocumentType.value,
      id_document_front_key: idFront.value.key!,
      id_document_back_key: idBack.value.key ?? undefined,
      face_photo_key: face.value.key!,
      vehicle_name: vehicleName.value.trim(),
      vehicle_plate_number: vehiclePlateNumber.value.trim(),
      vehicle_photo_keys: vehiclePhotos.value.map((p) => p.key!),
    }
    await apiFetch<CourierDetailRead>('/couriers/me', { method: 'POST', body: payload })
    await auth.fetchMe()
    toast.success('Inscription envoyée — en attente de validation par un administrateur.')
    await router.push('/livreur')
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible de finaliser l'inscription."))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="app-shell pa-0">
    <div class="d-flex align-center pa-2 ga-2">
      <v-btn icon variant="text" @click="router.back()">
        <PhArrowLeft :size="20" />
      </v-btn>
      <h1 class="text-h6">Devenir livreur</h1>
      <LayoutHomeLink />
    </div>

    <div class="detail-card">
      <p class="text-muted mb-5" style="font-size: 13px">
        Inscris-toi comme livreur pour recevoir des sous-commandes à livrer. Tu manipuleras des colis payés
        cash à la livraison — pour la sécurité des vendeurs et acheteurs, ton identité et ton engin doivent
        être vérifiés par un administrateur avant que des commandes te soient assignées.
      </p>

      <v-form @submit.prevent="submit">
        <label class="field-label">Type de véhicule</label>
        <v-select v-model="vehicleType" :items="vehicleOptions" class="mb-2" />

        <label class="field-label">Zone (optionnel)</label>
        <v-text-field v-model="zone" placeholder="Ex: Kaloum" class="mb-4" />

        <v-divider class="mb-4" />
        <div class="section-title">Pièce d'identité</div>

        <label class="field-label">Type de pièce</label>
        <v-select v-model="idDocumentType" :items="idDocumentOptions" class="mb-2" />

        <label class="field-label">Recto</label>
        <div class="doc-slot mb-2">
          <img v-if="idFront.previewUrl" :src="idFront.previewUrl" class="doc-slot__preview" alt="Recto de la pièce" />
          <input ref="idFrontInput" type="file" accept="image/jpeg,image/png,image/webp" class="d-none" @change="onIdFrontSelected" />
          <v-btn variant="outlined" size="small" :loading="idFront.uploading" @click="idFrontInput?.click()">
            <PhUploadSimple :size="14" class="mr-1" />
            {{ idFront.key ? 'Remplacer' : 'Choisir une photo' }}
          </v-btn>
        </div>

        <template v-if="backRequired">
          <label class="field-label">Verso</label>
          <div class="doc-slot mb-2">
            <img v-if="idBack.previewUrl" :src="idBack.previewUrl" class="doc-slot__preview" alt="Verso de la pièce" />
            <input ref="idBackInput" type="file" accept="image/jpeg,image/png,image/webp" class="d-none" @change="onIdBackSelected" />
            <v-btn variant="outlined" size="small" :loading="idBack.uploading" @click="idBackInput?.click()">
              <PhUploadSimple :size="14" class="mr-1" />
              {{ idBack.key ? 'Remplacer' : 'Choisir une photo' }}
            </v-btn>
          </div>
        </template>

        <v-divider class="mb-4 mt-2" />
        <div class="section-title">Photo de visage</div>
        <p class="text-muted mb-2" style="font-size: 12px">
          Fond blanc, visage bien dégagé et net, bonne luminosité — comme une photo d'identité.
        </p>
        <div class="doc-slot mb-4">
          <img v-if="face.previewUrl" :src="face.previewUrl" class="doc-slot__preview" alt="Photo de visage" />
          <input ref="faceInput" type="file" accept="image/jpeg,image/png,image/webp" class="d-none" @change="onFaceSelected" />
          <v-btn variant="outlined" size="small" :loading="face.uploading" @click="faceInput?.click()">
            <PhUploadSimple :size="14" class="mr-1" />
            {{ face.key ? 'Remplacer' : 'Choisir une photo' }}
          </v-btn>
        </div>

        <v-divider class="mb-4" />
        <div class="section-title">Engin</div>

        <label class="field-label">Nom / modèle de l'engin</label>
        <v-text-field v-model="vehicleName" placeholder="Ex: Yamaha DT125" class="mb-2" />

        <label class="field-label">Numéro d'immatriculation</label>
        <v-text-field v-model="vehiclePlateNumber" placeholder="Ex: RC-1234-AB" class="mb-2" />

        <label class="field-label">Photos de l'engin — la plaque doit être visible sur au moins une photo</label>
        <div v-if="vehiclePhotos.length" class="doc-grid mb-2">
          <div v-for="(photo, i) in vehiclePhotos" :key="i" class="doc-grid__item">
            <img v-if="photo.previewUrl" :src="photo.previewUrl" alt="Photo de l'engin" />
            <PhSpinner v-if="photo.uploading" :size="16" class="doc-grid__spinner" />
            <button type="button" class="doc-grid__remove" @click="removeVehiclePhoto(i)">
              <PhX :size="12" weight="bold" />
            </button>
          </div>
        </div>
        <input ref="vehicleInput" type="file" accept="image/jpeg,image/png,image/webp" multiple class="d-none" @change="onVehicleFilesSelected" />
        <v-btn
          v-if="vehiclePhotos.length < MAX_VEHICLE_PHOTOS"
          variant="outlined"
          size="small"
          block
          class="mb-4"
          @click="vehicleInput?.click()"
        >
          <PhUploadSimple :size="14" class="mr-1" />
          Ajouter des photos ({{ vehiclePhotos.length }}/{{ MAX_VEHICLE_PHOTOS }})
        </v-btn>

        <v-btn type="submit" color="primary" block size="large" :disabled="!canSubmit" :loading="submitting">
          M'inscrire
        </v-btn>
      </v-form>
    </div>
  </div>
</template>

<style scoped>
.doc-slot {
  display: flex;
  align-items: center;
  gap: 10px;
}

.doc-slot__preview {
  width: 56px;
  height: 56px;
  object-fit: cover;
  border-radius: var(--radius-sm);
  background: var(--color-neutral-800);
  flex-shrink: 0;
}

.doc-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}

.doc-grid__item {
  position: relative;
  aspect-ratio: 1 / 1;
  border-radius: var(--radius-sm);
  overflow: hidden;
  background: var(--color-neutral-800);
}

.doc-grid__item img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.doc-grid__spinner {
  position: absolute;
  inset: 0;
  margin: auto;
  color: #fff;
}

.doc-grid__remove {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
}
</style>
