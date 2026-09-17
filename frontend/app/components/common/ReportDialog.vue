<script setup lang="ts">
import type { ReportCreate } from '~/types/api'

// Réutilisé pour signaler un produit ou un avis — seul l'endpoint change
// (POST /products/{id}/reports ou POST /reviews/{id}/reports), la logique
// et l'UI sont identiques.
const open = defineModel<boolean>({ required: true })
const props = defineProps<{ endpoint: string }>()
const emit = defineEmits<{ reported: [] }>()

const { apiFetch } = useApi()
const toast = useToastStore()

const reason = ref('')
const submitting = ref(false)

async function submit() {
  if (reason.value.trim().length < 3) {
    toast.error('Précise le motif (3 caractères minimum).')
    return
  }
  submitting.value = true
  try {
    const payload: ReportCreate = { reason: reason.value.trim() }
    await apiFetch(props.endpoint, { method: 'POST', body: payload })
    toast.success('Signalement envoyé — merci, notre équipe va l’examiner.')
    reason.value = ''
    open.value = false
    emit('reported')
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'envoyer ce signalement."))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <v-dialog v-model="open" max-width="360">
    <v-card class="pa-4">
      <h2 class="text-h6 mb-3">Signaler</h2>
      <p class="text-muted mb-3 text-meta">
        Expliquez brièvement le problème — notre équipe va l'examiner.
      </p>
      <v-form @submit.prevent="submit">
        <v-textarea
          v-model="reason"
          rows="3"
          placeholder="Ex: photo trompeuse, contenu inapproprié…"
          class="mb-3"
        />
        <div class="d-flex flex-column ga-2">
          <v-btn type="submit" color="error" block :loading="submitting">Signaler</v-btn>
          <v-btn variant="text" block @click="open = false">Annuler</v-btn>
        </div>
      </v-form>
    </v-card>
  </v-dialog>
</template>
