<script setup lang="ts">
import { PhCheckCircle, PhMapPin, PhPencilSimple, PhPlus, PhStorefront, PhTrash, PhUser } from '@phosphor-icons/vue'
import type { PickupPointManagerAdminCreate, PickupPointManagerRead, PickupPointRead, VendorRead } from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const { apiFetch } = useApi()
const toast = useToastStore()
const { locating, locate } = useGeolocation()

const { data: points, pending, refresh } = await useAsyncData(
  'admin-pickup-points',
  () => apiFetch<PickupPointRead[]>('/admin/pickup-points'),
  { default: () => [], getCachedData: () => undefined },
)

const { data: managers, refresh: refreshManagers } = await useAsyncData(
  'admin-pickup-point-managers',
  () => apiFetch<PickupPointManagerRead[]>('/admin/pickup-point-managers'),
  { default: () => [], getCachedData: () => undefined },
)

// Pour proposer de rattacher un point à une boutique existante — un point de
// retrait n'est pas forcément une boutique (on peut aussi construire un local
// dédié uniquement à ça), donc toujours optionnel (voir vendorOptions ci-dessous).
const { data: vendors } = await useAsyncData('admin-vendors-for-pickup-points', () => apiFetch<VendorRead[]>('/admin/vendors'), {
  default: () => [],
})

const vendorOptions = computed(() => vendors.value.map((v) => ({ title: v.shop_name, value: v.id })))
function vendorById(id: string | null) {
  return id ? (vendors.value.find((v) => v.id === id) ?? null) : null
}

const managersByPoint = computed(() => {
  const grouped: Record<string, PickupPointManagerRead[]> = {}
  for (const m of managers.value) {
    ;(grouped[m.pickup_point_id] ??= []).push(m)
  }
  return grouped
})

const showForm = ref(false)
const editingId = ref<string | null>(null)
const form = ref({
  name: '',
  zone: '',
  latitude: null as number | null,
  longitude: null as number | null,
  vendorId: null as string | null,
})
const submitting = ref(false)

function startCreate() {
  editingId.value = null
  form.value = { name: '', zone: '', latitude: null, longitude: null, vendorId: null }
  showForm.value = true
}

function startEdit(point: PickupPointRead) {
  editingId.value = point.id
  form.value = {
    name: point.name,
    zone: point.zone,
    latitude: point.latitude,
    longitude: point.longitude,
    vendorId: point.vendor_id,
  }
  showForm.value = true
}

// Évite de ressaisir la zone/position déjà connue quand le point EST la
// boutique du vendeur choisi — reste une pure commodité, l'admin peut
// toujours corriger ensuite (ex. un local de retrait séparé du magasin).
function fillFromVendor() {
  const vendor = vendorById(form.value.vendorId)
  if (!vendor) return
  if (!form.value.name.trim()) form.value.name = vendor.shop_name
  if (vendor.zone) form.value.zone = vendor.zone
  if (vendor.latitude !== null) form.value.latitude = vendor.latitude
  if (vendor.longitude !== null) form.value.longitude = vendor.longitude
}

async function useCurrentPosition() {
  try {
    const { latitude, longitude } = await locate()
    form.value.latitude = latitude
    form.value.longitude = longitude
    toast.success('Position enregistrée.')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Impossible de récupérer la position.')
  }
}

async function submit() {
  if (form.value.name.trim().length < 2) {
    toast.error('Le nom du point doit contenir au moins 2 caractères.')
    return
  }
  if (form.value.zone.trim().length < 3) {
    toast.error('Précise la zone/le repère de ce point.')
    return
  }
  submitting.value = true
  try {
    const body = {
      name: form.value.name.trim(),
      zone: form.value.zone.trim(),
      latitude: form.value.latitude,
      longitude: form.value.longitude,
      vendor_id: form.value.vendorId,
    }
    if (editingId.value) {
      await apiFetch(`/admin/pickup-points/${editingId.value}`, { method: 'PATCH', body })
    } else {
      await apiFetch('/admin/pickup-points', { method: 'POST', body })
    }
    await refresh()
    showForm.value = false
    toast.success(editingId.value ? 'Point mis à jour.' : 'Point créé.')
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'enregistrer ce point."))
  } finally {
    submitting.value = false
  }
}

const togglingId = ref<string | null>(null)
async function toggleActive(point: PickupPointRead) {
  togglingId.value = point.id
  try {
    await apiFetch(`/admin/pickup-points/${point.id}`, { method: 'PATCH', body: { is_active: !point.is_active } })
    await refresh()
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de mettre à jour ce point.'))
  } finally {
    togglingId.value = null
  }
}

const confirmDeleteId = ref<string | null>(null)
const deleting = ref(false)
async function deletePoint() {
  if (!confirmDeleteId.value) return
  deleting.value = true
  try {
    await apiFetch(`/admin/pickup-points/${confirmDeleteId.value}`, { method: 'DELETE' })
    await refresh()
    toast.success('Point supprimé.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de supprimer ce point.'))
  } finally {
    deleting.value = false
    confirmDeleteId.value = null
  }
}

// Gestionnaires — un compte par personne staffant un point, créé uniquement
// par l'admin (pas d'auto-inscription, contrairement aux livreurs) : voir
// app/pickup_point_managers dans le backend.
const managerDialogPointId = ref<string | null>(null)
const creatingManager = ref(false)
const managerForm = ref({ phone: '', password: '', firstName: '', lastName: '' })

function resetManagerForm() {
  managerForm.value = { phone: '', password: '', firstName: '', lastName: '' }
}

function openManagerDialog(pointId: string) {
  resetManagerForm()
  managerDialogPointId.value = pointId
}

async function createManager() {
  if (!managerDialogPointId.value) return
  if (!/^\+224\d{9}$/.test(managerForm.value.phone.trim())) {
    toast.error('Numéro invalide — format attendu : +224XXXXXXXXX.')
    return
  }
  if (managerForm.value.password.length < 8) {
    toast.error('Le mot de passe doit contenir au moins 8 caractères.')
    return
  }
  creatingManager.value = true
  try {
    const payload: PickupPointManagerAdminCreate = {
      phone: managerForm.value.phone.trim(),
      password: managerForm.value.password,
      first_name: managerForm.value.firstName.trim() || undefined,
      last_name: managerForm.value.lastName.trim() || undefined,
      pickup_point_id: managerDialogPointId.value,
    }
    await apiFetch('/admin/pickup-point-managers', { method: 'POST', body: payload })
    toast.success('Gestionnaire créé.')
    managerDialogPointId.value = null
    await refreshManagers()
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de créer ce gestionnaire.'))
  } finally {
    creatingManager.value = false
  }
}

const removingManagerId = ref<string | null>(null)
async function removeManager(managerId: string) {
  removingManagerId.value = managerId
  try {
    await apiFetch(`/admin/pickup-point-managers/${managerId}`, { method: 'DELETE' })
    await refreshManagers()
    toast.success('Gestionnaire supprimé.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de supprimer ce gestionnaire.'))
  } finally {
    removingManagerId.value = null
  }
}
</script>

<template>
  <div class="dashboard-shell">
    <div class="d-flex justify-space-between align-center mb-4">
      <h1 class="text-h6">Points de retrait</h1>
      <v-btn color="primary" size="small" @click="startCreate">
        <PhPlus :size="16" class="mr-1" />
        Nouveau
      </v-btn>
    </div>

    <v-card v-if="showForm" class="mb-4 pa-3">
      <label class="field-label">Boutique liée (optionnel)</label>
      <p class="text-muted mb-2" style="font-size: 11.5px">
        À renseigner uniquement si ce point de retrait EST la boutique d'un vendeur — un point peut aussi être un
        local dédié, sans lien avec une boutique.
      </p>
      <v-select
        v-model="form.vendorId"
        :items="vendorOptions"
        placeholder="Aucune"
        clearable
        density="comfortable"
        class="mb-1"
      />
      <v-btn
        v-if="form.vendorId"
        variant="text"
        size="small"
        class="mb-3"
        style="padding: 0"
        @click="fillFromVendor"
      >
        <PhStorefront :size="14" class="mr-1" />
        Reprendre le nom/la zone/la position de cette boutique
      </v-btn>

      <label class="field-label">Nom du point</label>
      <v-text-field v-model="form.name" placeholder="Ex: Point Wari Madina" class="mb-2" />

      <label class="field-label">Zone / repère</label>
      <v-textarea v-model="form.zone" rows="2" placeholder="Ex: En face de la pharmacie" class="mb-1" />

      <v-btn variant="outlined" size="small" :loading="locating" class="mb-2" @click="useCurrentPosition">
        <PhMapPin :size="15" class="mr-1" />
        Utiliser la position actuelle
      </v-btn>
      <p class="text-muted mb-2" style="font-size: 11.5px">Ou touche la carte pour placer le point toi-même.</p>
      <CommonMapPicker v-model:latitude="form.latitude" v-model:longitude="form.longitude" class="mb-2" />
      <div v-if="form.latitude !== null" class="d-flex align-center ga-1 text-muted mb-3" style="font-size: 11.5px">
        <PhCheckCircle :size="14" weight="fill" color="var(--color-primary)" />
        <span>{{ form.latitude.toFixed(4) }}, {{ form.longitude!.toFixed(4) }}</span>
      </div>

      <div class="d-flex ga-2">
        <v-btn variant="outlined" class="flex-grow-1" @click="showForm = false">Annuler</v-btn>
        <v-btn color="primary" class="flex-grow-1" :loading="submitting" @click="submit">
          {{ editingId ? 'Enregistrer' : 'Créer' }}
        </v-btn>
      </div>
    </v-card>

    <CommonEmptyState v-if="!pending && points.length === 0" message="Aucun point de retrait pour l'instant." />

    <v-card v-for="p in points" :key="p.id" class="mb-3 pa-3">
      <div class="d-flex justify-space-between align-center mb-1">
        <span style="font-weight: 600">{{ p.name }}</span>
        <v-chip :color="p.is_active ? 'success' : 'default'" size="x-small" variant="tonal">
          {{ p.is_active ? 'Actif' : 'Inactif' }}
        </v-chip>
      </div>
      <div v-if="p.vendor_shop_name" class="d-flex align-center ga-1 text-muted mb-1" style="font-size: 11.5px">
        <PhStorefront :size="13" />
        <span>Boutique : {{ p.vendor_shop_name }}</span>
      </div>
      <div class="text-muted mb-3" style="font-size: 12.5px">{{ p.zone }}</div>

      <div class="d-flex ga-2 mb-3">
        <v-btn variant="outlined" size="small" class="flex-grow-1" :loading="togglingId === p.id" @click="toggleActive(p)">
          {{ p.is_active ? 'Désactiver' : 'Activer' }}
        </v-btn>
        <v-btn variant="outlined" size="small" @click="startEdit(p)">
          <PhPencilSimple :size="15" />
        </v-btn>
        <v-btn variant="outlined" color="error" size="small" @click="confirmDeleteId = p.id">
          <PhTrash :size="15" />
        </v-btn>
      </div>

      <v-divider class="mb-2" />
      <div class="d-flex justify-space-between align-center mb-1">
        <span class="field-label mb-0">Gestionnaires</span>
        <v-btn variant="text" size="x-small" @click="openManagerDialog(p.id)">
          <PhPlus :size="13" class="mr-1" />
          Ajouter
        </v-btn>
      </div>
      <p v-if="!managersByPoint[p.id]?.length" class="text-muted mb-0" style="font-size: 11.5px">
        Aucun gestionnaire pour ce point.
      </p>
      <div
        v-for="m in managersByPoint[p.id]"
        :key="m.id"
        class="d-flex align-center justify-space-between"
        style="padding: 3px 0"
      >
        <div class="d-flex align-center ga-1" style="font-size: 12.5px">
          <PhUser :size="13" color="var(--color-neutral-500)" />
          <span>{{ m.full_name ?? m.phone }}</span>
        </div>
        <v-btn
          variant="text"
          color="error"
          size="x-small"
          :loading="removingManagerId === m.id"
          @click="removeManager(m.id)"
        >
          <PhTrash :size="13" />
        </v-btn>
      </div>
    </v-card>

    <v-dialog :model-value="!!confirmDeleteId" max-width="340" @update:model-value="(v) => !v && (confirmDeleteId = null)">
      <v-card class="pa-5">
        <div class="text-subtitle-1 mb-2">Supprimer ce point ?</div>
        <p class="text-muted mb-4" style="font-size: 13px">
          Les adresses qui l'ont déjà enregistré ne sont pas affectées (le texte est figé).
        </p>
        <div class="d-flex ga-2">
          <v-btn variant="outlined" class="flex-grow-1" @click="confirmDeleteId = null">Annuler</v-btn>
          <v-btn color="error" class="flex-grow-1" :loading="deleting" @click="deletePoint">Supprimer</v-btn>
        </div>
      </v-card>
    </v-dialog>

    <v-dialog :model-value="!!managerDialogPointId" max-width="380" @update:model-value="(v) => !v && (managerDialogPointId = null)">
      <v-card class="pa-4">
        <h2 class="text-h6 mb-3">Ajouter un gestionnaire</h2>
        <p class="text-muted mb-4" style="font-size: 12.5px">
          Le compte est actif immédiatement — pas de validation à part.
        </p>

        <v-form @submit.prevent="createManager">
          <label class="field-label">Téléphone</label>
          <v-text-field v-model="managerForm.phone" placeholder="+224621234567" class="mb-2" />

          <label class="field-label">Mot de passe</label>
          <v-text-field v-model="managerForm.password" type="password" placeholder="8 caractères minimum" class="mb-2" />

          <div class="d-flex ga-2">
            <div class="flex-grow-1">
              <label class="field-label">Prénom (optionnel)</label>
              <v-text-field v-model="managerForm.firstName" class="mb-2" />
            </div>
            <div class="flex-grow-1">
              <label class="field-label">Nom (optionnel)</label>
              <v-text-field v-model="managerForm.lastName" class="mb-2" />
            </div>
          </div>

          <div class="d-flex flex-column ga-2 mt-2">
            <v-btn type="submit" color="primary" block :loading="creatingManager">Créer</v-btn>
            <v-btn variant="text" block @click="managerDialogPointId = null">Annuler</v-btn>
          </div>
        </v-form>
      </v-card>
    </v-dialog>
  </div>
</template>
