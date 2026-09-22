<script setup lang="ts">
import { PhArrowLeft } from '@phosphor-icons/vue'
import type { UserRead } from '~/types/api'

definePageMeta({ middleware: 'auth', layout: 'blank' })

const auth = useAuthStore()
const router = useRouter()
const { apiFetch } = useApi()
const toast = useToastStore()

const firstName = ref('')
const lastName = ref('')
const email = ref('')
watch(
  () => auth.user,
  (u) => {
    if (!u) return
    firstName.value = u.first_name ?? ''
    lastName.value = u.last_name ?? ''
    email.value = u.email ?? ''
  },
  { immediate: true },
)

const submitting = ref(false)

async function submit() {
  submitting.value = true
  try {
    const updated = await apiFetch<UserRead>('/users/me', {
      method: 'PATCH',
      body: {
        first_name: firstName.value.trim() || null,
        last_name: lastName.value.trim() || null,
        email: email.value.trim() || null,
      },
    })
    auth.user = updated
    toast.success('Profil mis à jour.')
    await router.push('/profil')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de sauvegarder ces informations.'))
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
      <h1 class="text-h6">Modifier mon profil</h1>
      <LayoutHomeLink />
    </div>

    <div class="detail-card">
      <label class="field-label">Prénom</label>
      <v-text-field v-model="firstName" placeholder="Ex: Mamadou" class="mb-2" />

      <label class="field-label">Nom</label>
      <v-text-field v-model="lastName" placeholder="Ex: Diallo" class="mb-2" />

      <label class="field-label">Email</label>
      <v-text-field v-model="email" type="email" placeholder="ex: vous@exemple.com" class="mb-2" />

      <label class="field-label">Téléphone</label>
      <v-text-field :model-value="auth.user?.phone" disabled hint="Le téléphone ne peut pas être modifié." persistent-hint class="mb-4" />

      <v-btn color="primary" block size="large" :loading="submitting" @click="submit">Enregistrer</v-btn>
    </div>
  </div>
</template>
