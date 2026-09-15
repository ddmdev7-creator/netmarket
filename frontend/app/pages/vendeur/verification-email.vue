<script setup lang="ts">
import { PhArrowLeft, PhEnvelopeSimple } from '@phosphor-icons/vue'
import type { UserRead } from '~/types/api'

definePageMeta({ middleware: 'auth', layout: 'blank' })

const auth = useAuthStore()
const router = useRouter()
const { apiFetch } = useApi()
const toast = useToastStore()

if (auth.user?.role !== 'vendor') {
  await router.replace('/vendeur/inscription')
} else if (auth.user.email_verified) {
  await router.replace('/vendeur')
}

const code = ref('')
const submitting = ref(false)
const resending = ref(false)

async function submit() {
  if (!/^\d{4,5}$/.test(code.value.trim())) {
    toast.error('Le code contient 4 ou 5 chiffres.')
    return
  }
  submitting.value = true
  try {
    await apiFetch<UserRead>('/users/me/verify-email', { method: 'POST', body: { code: code.value.trim() } })
    await auth.fetchMe()
    await router.push('/vendeur')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de vérifier ce code.'))
  } finally {
    submitting.value = false
  }
}

async function resend() {
  resending.value = true
  try {
    await apiFetch('/users/me/resend-verification-email', { method: 'POST' })
    toast.success('Un nouveau code a été envoyé.')
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'envoyer un nouveau code."))
  } finally {
    resending.value = false
  }
}
</script>

<template>
  <div class="app-shell pa-0">
    <div class="d-flex align-center pa-2 ga-2">
      <v-btn icon variant="text" @click="router.back()">
        <PhArrowLeft :size="20" />
      </v-btn>
      <h1 class="text-h6">Vérifie ton email</h1>
      <LayoutHomeLink />
    </div>

    <div class="px-4 pt-4 d-flex flex-column align-center text-center">
      <PhEnvelopeSimple :size="40" weight="light" color="var(--color-primary)" class="mb-3" />
      <p class="text-muted mb-6" style="font-size: 13px; max-width: 300px">
        Un code à 5 chiffres a été envoyé à <strong>{{ auth.user?.email }}</strong
        >. Saisis-le ci-dessous pour accéder à ton espace vendeur.
      </p>

      <v-form class="w-100" style="max-width: 260px" @submit.prevent="submit">
        <v-text-field
          v-model="code"
          placeholder="00000"
          maxlength="5"
          inputmode="numeric"
          class="mb-2"
          style="font-size: 22px; letter-spacing: 6px; text-align: center"
          center-affix
        />

        <v-btn type="submit" color="primary" block size="large" class="mb-3" :loading="submitting">Vérifier</v-btn>
        <v-btn variant="text" block :loading="resending" @click="resend">Renvoyer le code</v-btn>
      </v-form>
    </div>
  </div>
</template>
