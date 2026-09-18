<script setup lang="ts">
import { PhArrowLeft } from '@phosphor-icons/vue'

definePageMeta({ layout: 'blank' })

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const toast = useToastStore()

const phone = ref((route.query.phone as string) || '+224')
const code = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const loading = ref(false)

async function submit() {
  if (!/^\d{4,5}$/.test(code.value.trim())) {
    toast.error('Le code contient 4 ou 5 chiffres.')
    return
  }
  if (newPassword.value.length < 8) {
    toast.error('Le mot de passe doit contenir au moins 8 caractères.')
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    toast.error('Les deux mots de passe ne correspondent pas.')
    return
  }

  loading.value = true
  try {
    await auth.acceptCourierInvitation(phone.value, code.value.trim(), newPassword.value)
    toast.success('Compte activé — plus qu\'à compléter ton profil livreur.')
    await router.push({ path: '/connexion', query: { redirect: '/livreur/inscription' } })
  } catch (error) {
    toast.error(apiErrorMessage(error, "Impossible d'activer ce compte."))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="app-shell auth-shell d-flex flex-column justify-center pa-6" style="min-height: 100dvh">
    <div class="auth-card">
      <NuxtLink to="/connexion" class="d-flex align-center ga-1 text-muted mb-4 text-meta" style="text-decoration: none">
        <PhArrowLeft :size="14" />
        Retour
      </NuxtLink>

      <div class="text-center mb-8">
        <h1 class="text-h5 mb-1">Ton compte livreur</h1>
        <p class="text-muted">
          Un administrateur t'a créé un compte. Utilise le code reçu par email pour définir ton mot de passe, puis
          complète ton profil (pièce d'identité, véhicule).
        </p>
      </div>

      <v-form @submit.prevent="submit">
        <v-text-field v-model="phone" label="Téléphone" placeholder="+224621234567" class="mb-2" />
        <v-text-field
          v-model="code"
          label="Code reçu par email"
          placeholder="00000"
          maxlength="5"
          inputmode="numeric"
          class="mb-2"
        />
        <v-text-field v-model="newPassword" label="Nouveau mot de passe" type="password" class="mb-2" />
        <v-text-field v-model="confirmPassword" label="Confirmer le mot de passe" type="password" class="mb-2" />

        <v-btn type="submit" color="primary" block size="large" :loading="loading">Activer mon compte</v-btn>
      </v-form>
    </div>
  </div>
</template>
