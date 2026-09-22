<script setup lang="ts">
import { PhArrowLeft } from '@phosphor-icons/vue'
import type { AddressRead } from '~/types/api'
import type { AddressFormValues } from '~/components/address/AddressForm.vue'

definePageMeta({ middleware: 'auth', layout: 'blank' })

const router = useRouter()
const { apiFetch } = useApi()
const toast = useToastStore()

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
    await apiFetch<AddressRead>('/addresses', {
      method: 'POST',
      body: {
        label: form.value.label.trim(),
        delivery_type: form.value.delivery_type,
        zone: form.value.zone.trim(),
        pickup_point_id: form.value.pickup_point_id ?? undefined,
        recipient_name: form.value.recipient_name.trim() || undefined,
        recipient_phone: form.value.recipient_phone.trim() || undefined,
        instructions: form.value.instructions.trim() || undefined,
        latitude: form.value.latitude,
        longitude: form.value.longitude,
        is_default: form.value.is_default,
      },
    })
    toast.success('Adresse enregistrée.')
    await router.replace('/profil/adresses')
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'enregistrer cette adresse."))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="app-shell pa-0" style="padding-bottom: 32px">
    <div class="d-flex align-center pa-2 ga-2">
      <v-btn icon variant="text" @click="router.back()">
        <PhArrowLeft :size="20" />
      </v-btn>
      <h1 class="text-h6">Nouvelle adresse</h1>
      <LayoutHomeLink />
    </div>

    <div class="detail-card">
      <AddressForm v-model="form" />
      <v-btn color="primary" block size="large" :loading="submitting" @click="submit">Enregistrer</v-btn>
    </div>
  </div>
</template>
