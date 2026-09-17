<script setup lang="ts">
import type { ReviewCreate } from '~/types/api'

const open = defineModel<boolean>({ required: true })
const props = defineProps<{ productId: string }>()
const emit = defineEmits<{ submitted: [] }>()

const { apiFetch } = useApi()
const toast = useToastStore()

const rating = ref(0)
const comment = ref('')
const submitting = ref(false)

async function submit() {
  if (rating.value < 1) {
    toast.error('Choisissez une note.')
    return
  }
  submitting.value = true
  try {
    const payload: ReviewCreate = { rating: rating.value, comment: comment.value.trim() || undefined }
    await apiFetch(`/products/${props.productId}/reviews`, { method: 'POST', body: payload })
    toast.success('Avis publié — merci !')
    rating.value = 0
    comment.value = ''
    open.value = false
    emit('submitted')
  } catch (e) {
    // Le backend renvoie déjà des messages français précis (éligibilité,
    // doublon) — on les relaie tels quels plutôt que de les redupliquer ici.
    toast.error(apiErrorMessage(e, "Impossible d'enregistrer cet avis."))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <v-dialog v-model="open" max-width="360">
    <v-card class="pa-4">
      <h2 class="text-h6 mb-3">Laisser un avis</h2>
      <div class="d-flex justify-center mb-3">
        <v-rating v-model="rating" color="var(--color-accent)" hover />
      </div>
      <v-textarea v-model="comment" rows="3" placeholder="Votre avis (optionnel)" class="mb-3" />
      <div class="d-flex flex-column ga-2">
        <v-btn color="primary" block :loading="submitting" @click="submit">Publier</v-btn>
        <v-btn variant="text" block @click="open = false">Annuler</v-btn>
      </div>
    </v-card>
  </v-dialog>
</template>
