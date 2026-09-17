<script setup lang="ts">
import { PhArrowLeft } from '@phosphor-icons/vue'

definePageMeta({ layout: 'blank' })
useHead({ title: 'NdjouriMarket' })

const auth = useAuthStore()
const router = useRouter()
const toast = useToastStore()

const phone = ref('+224')
const email = ref('')
const password = ref('')
const loading = ref(false)

async function submit() {
  if (!email.value.trim()) {
    toast.error("L'adresse email est obligatoire.")
    return
  }
  if (password.value.length < 8) {
    toast.error('Le mot de passe doit contenir au moins 8 caractères.')
    return
  }
  loading.value = true
  try {
    await auth.register(phone.value, password.value, email.value.trim())
    await router.push('/verifier-email')
  } catch (error) {
    toast.error(apiErrorMessage(error, 'Impossible de créer le compte.'))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="app-shell auth-shell d-flex flex-column justify-center pa-6" style="min-height: 100dvh">
    <div class="auth-card">
      <NuxtLink to="/" class="d-flex align-center ga-1 text-muted mb-4 text-meta" style="text-decoration: none">
        <PhArrowLeft :size="14" />
        Retour à l'accueil
      </NuxtLink>

      <div class="text-center mb-8">
        <h1 class="text-h5 mb-1">Créer un compte</h1>
        <p class="text-muted">Rejoignez la marketplace en quelques secondes</p>
      </div>

      <v-form @submit.prevent="submit">
        <v-text-field v-model="phone" label="Téléphone" placeholder="+224621234567" class="mb-2" />
        <v-text-field v-model="email" label="Email" type="email" required class="mb-2" />
        <v-text-field v-model="password" label="Mot de passe" type="password" hint="8 caractères minimum" class="mb-2" />

        <v-btn type="submit" color="primary" block size="large" :loading="loading">Créer mon compte</v-btn>
      </v-form>

      <div class="text-center mt-6 text-muted">
        Déjà un compte ?
        <NuxtLink to="/connexion" class="text-primary">Se connecter</NuxtLink>
      </div>
    </div>
  </div>
</template>
