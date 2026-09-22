<script setup lang="ts">
import { PhArrowLeft, PhTrash } from '@phosphor-icons/vue'
import type { AddressRead } from '~/types/api'
import type { AddressFormValues } from '~/components/address/AddressForm.vue'

definePageMeta({ middleware: 'auth', layout: 'blank' })

const route = useRoute()
const router = useRouter()
const { apiFetch } = useApi()
const toast = useToastStore()
// Réactif plutôt qu'un `const` figé : sur une route dynamique (/adresses/[id]),
// Vue Router réutilise l'instance de page en passant d'une adresse à l'autre
// (pas de remount) — un id capturé une fois pour toutes resterait bloqué sur
// la première adresse ouverte, et "Enregistrer" écrirait alors sur la
// mauvaise adresse.
const addressId = computed(() => route.params.id as string)

const { data: addresses, error: loadError } = await useAsyncData('my-addresses-edit', () =>
  apiFetch<AddressRead[]>('/addresses'),
)
const address = computed(() => addresses.value?.find((a) => a.id === addressId.value) ?? null)

const form = ref<AddressFormValues>({
  label: '',
  delivery_type: 'home_delivery',
  zone: '',
  pickup_point_id: null,
  recipient_name: '',
  recipient_phone: '',
  instructions: '',
  latitude: null,
  longitude: null,
  is_default: false,
})
watch(
  address,
  (a) => {
    if (!a) return
    form.value = {
      label: a.label,
      delivery_type: a.delivery_type,
      zone: a.zone,
      pickup_point_id: a.pickup_point_id,
      recipient_name: a.recipient_name ?? '',
      recipient_phone: a.recipient_phone ?? '',
      instructions: a.instructions ?? '',
      latitude: a.latitude,
      longitude: a.longitude,
      is_default: a.is_default,
    }
  },
  { immediate: true },
)

const submitting = ref(false)

async function submit() {
  if (form.value.label.trim().length < 1) {
    toast.error('Donne un nom à cette adresse.')
    return
  }
  const error = validateAddressForm(form.value)
  if (error) {
    toast.error(error)
    return
  }
  submitting.value = true
  try {
    await apiFetch<AddressRead>(`/addresses/${addressId.value}`, {
      method: 'PATCH',
      body: {
        label: form.value.label.trim(),
        delivery_type: form.value.delivery_type,
        zone: form.value.zone.trim(),
        pickup_point_id: form.value.pickup_point_id,
        recipient_name: form.value.recipient_name.trim() || null,
        recipient_phone: form.value.recipient_phone.trim() || null,
        instructions: form.value.instructions.trim() || null,
        latitude: form.value.latitude,
        longitude: form.value.longitude,
        is_default: form.value.is_default,
      },
    })
    toast.success('Adresse mise à jour.')
    await router.replace('/profil/adresses')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de sauvegarder cette adresse.'))
  } finally {
    submitting.value = false
  }
}

const confirmDelete = ref(false)
const deleting = ref(false)
async function deleteAddress() {
  deleting.value = true
  try {
    await apiFetch(`/addresses/${addressId.value}`, { method: 'DELETE' })
    toast.success('Adresse supprimée.')
    await router.replace('/profil/adresses')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de supprimer cette adresse.'))
    confirmDelete.value = false
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <div v-if="loadError || (addresses && !address)" class="pa-6">
    <CommonEmptyState message="Adresse introuvable." />
  </div>
  <div v-else class="app-shell pa-0" style="padding-bottom: 32px">
    <div class="d-flex align-center pa-2 ga-2">
      <v-btn icon variant="text" @click="router.back()">
        <PhArrowLeft :size="20" />
      </v-btn>
      <h1 class="text-h6">Modifier l'adresse</h1>
      <LayoutHomeLink />
    </div>

    <div v-if="address" class="px-4 detail-card">
      <AddressForm v-model="form" />

      <v-btn color="primary" block size="large" class="mb-3" :loading="submitting" @click="submit">
        Enregistrer les modifications
      </v-btn>
      <v-btn variant="outlined" color="error" block @click="confirmDelete = true">
        <PhTrash :size="16" class="mr-1" />
        Supprimer l'adresse
      </v-btn>
    </div>

    <v-dialog v-model="confirmDelete" max-width="340">
      <v-card class="pa-5">
        <div class="text-subtitle-1 mb-2">Supprimer cette adresse ?</div>
        <p class="text-muted mb-4 text-meta">Cette action est définitive.</p>
        <div class="d-flex ga-2">
          <v-btn variant="outlined" class="flex-grow-1" @click="confirmDelete = false">Annuler</v-btn>
          <v-btn color="error" class="flex-grow-1" :loading="deleting" @click="deleteAddress">Supprimer</v-btn>
        </div>
      </v-card>
    </v-dialog>
  </div>
</template>
