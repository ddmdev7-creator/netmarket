<script setup lang="ts">
import { PhArrowLeft } from '@phosphor-icons/vue'

definePageMeta({ layout: 'blank' })
useHead({ title: 'NdjouriMarket' })

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const toast = useToastStore()

const phone = ref('+224')
const password = ref('')
const loading = ref(false)

async function submit() {
  loading.value = true
  try {
    await auth.login(phone.value, password.value)
    const fallback = auth.user?.role === 'admin' ? '/admin' : '/'
    const redirect = (route.query.redirect as string) || fallback
    await router.push(redirect)
  } catch (error) {
    toast.error(apiErrorMessage(error, 'Numéro de téléphone ou mot de passe incorrect.'))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="app-shell auth-shell d-flex flex-column justify-center pa-4" style="min-height: 100dvh">
    <div class="auth-card">
      <NuxtLink to="/" class="d-flex align-center ga-1 text-muted mb-4 text-meta" style="text-decoration: none">
        <PhArrowLeft :size="14" />
        Retour à l'accueil
      </NuxtLink>

      <div class="text-center mb-8">
        <div class="auth-brand mb-3">NdjouriMarket</div>
        <h1 class="text-h5 mb-1">Bon retour</h1>
        <p class="text-muted">Connectez-vous pour continuer vos achats</p>
      </div>

      <v-form @submit.prevent="submit">
        <v-text-field v-model="phone" label="Téléphone" placeholder="+224621234567" class="mb-2" />
        <v-text-field v-model="password" label="Mot de passe" type="password" class="mb-2" />

        <div class="text-center mb-4">
          <NuxtLink to="/mot-de-passe-oublie" class="text-primary text-meta">Mot de passe oublié ?</NuxtLink>
        </div>

        <v-btn type="submit" color="primary" block size="large" :loading="loading">Se connecter</v-btn>
      </v-form>

      <div class="text-center mt-6 text-muted">
        Pas encore de compte ?
        <NuxtLink to="/inscription" class="text-primary">Créer un compte</NuxtLink>
      </div>
    </div>
  </div>
</template>
