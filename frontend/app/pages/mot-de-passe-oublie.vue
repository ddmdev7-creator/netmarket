<script setup lang="ts">
import { PhArrowLeft } from '@phosphor-icons/vue'

definePageMeta({ layout: 'blank' })

const router = useRouter()
const auth = useAuthStore()
const toast = useToastStore()

const phone = ref('+224')
const loading = ref(false)

async function submit() {
  loading.value = true
  try {
    await auth.forgotPassword(phone.value)
    toast.success('Si un compte existe avec ce numéro, un code a été envoyé par email.')
    await router.push({ path: '/reinitialiser-mot-de-passe', query: { phone: phone.value } })
  } catch (error) {
    toast.error(apiErrorMessage(error, "Impossible d'envoyer le code. Réessaie plus tard."))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="app-shell auth-shell d-flex flex-column justify-center pa-4" style="min-height: 100dvh">
    <div class="auth-card">
      <NuxtLink to="/connexion" class="d-flex align-center ga-1 text-muted mb-4 text-meta" style="text-decoration: none">
        <PhArrowLeft :size="14" />
        Retour à la connexion
      </NuxtLink>

      <div class="text-center mb-8">
        <h1 class="text-h5 mb-1">Mot de passe oublié</h1>
        <p class="text-muted">Indiquez votre numéro pour recevoir un code par email</p>
      </div>

      <v-form @submit.prevent="submit">
        <v-text-field v-model="phone" label="Téléphone" placeholder="+224621234567" class="mb-2" />

        <v-btn type="submit" color="primary" block size="large" :loading="loading">Envoyer le code</v-btn>
      </v-form>
    </div>
  </div>
</template>
