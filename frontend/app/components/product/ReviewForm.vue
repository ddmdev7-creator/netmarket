<script setup lang="ts">
/**
 * Laisser ou modifier son avis sur un produit reçu. Ouvert depuis la fiche
 * produit, le détail d'une commande ou « Produits à noter » (Mes commandes) —
 * `existing` bascule en modification (PUT /products/{id}/reviews/mine),
 * `initialRating` pré-sélectionne la note quand l'acheteur a déjà cliqué une
 * étoile avant d'ouvrir le formulaire.
 */
import { PhImage, PhStar } from '@phosphor-icons/vue'
import type { ReviewCreate, ReviewRead } from '~/types/api'

const open = defineModel<boolean>({ required: true })
const props = withDefaults(
  defineProps<{
    productId: string
    productName?: string | null
    productImage?: string | null
    existing?: ReviewRead | null
    initialRating?: number
  }>(),
  { productName: null, productImage: null, existing: null, initialRating: 0 },
)
const emit = defineEmits<{ submitted: [review: ReviewRead] }>()

const { apiFetch } = useApi()
const apiBase = useApiBase()
const toast = useToastStore()

const MAX_COMMENT = 2000
const LABELS = ['', 'Très décevant', 'Décevant', 'Correct', 'Bien', 'Excellent']

const rating = ref(0)
const hovered = ref(0)
const comment = ref('')
const submitting = ref(false)

const isEdit = computed(() => props.existing !== null)
const shownRating = computed(() => hovered.value || rating.value)

watch(open, (isOpen) => {
  if (!isOpen) return
  rating.value = props.existing?.rating ?? props.initialRating
  comment.value = props.existing?.comment ?? ''
  hovered.value = 0
})

async function submit() {
  if (rating.value < 1) {
    toast.error('Choisissez une note de 1 à 5 étoiles.')
    return
  }
  submitting.value = true
  try {
    const payload: ReviewCreate = { rating: rating.value, comment: comment.value.trim() || null }
    const review = await apiFetch<ReviewRead>(
      isEdit.value ? `/products/${props.productId}/reviews/mine` : `/products/${props.productId}/reviews`,
      { method: isEdit.value ? 'PUT' : 'POST', body: payload },
    )
    toast.success(isEdit.value ? 'Avis mis à jour.' : 'Avis publié — merci !')
    open.value = false
    emit('submitted', review)
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
  <v-dialog v-model="open" max-width="440">
    <v-card class="review-form">
      <h2 class="review-form__title">{{ isEdit ? 'Modifier mon avis' : 'Noter ce produit' }}</h2>

      <div v-if="productName" class="review-form__product">
        <div class="review-form__thumb">
          <img v-if="productImage" :src="resolveImageUrl(productImage, apiBase)" :alt="productName" />
          <PhImage v-else :size="20" weight="light" color="var(--color-neutral-500)" />
        </div>
        <span class="review-form__name">{{ productName }}</span>
      </div>

      <div class="stars" role="radiogroup" aria-label="Note" @mouseleave="hovered = 0">
        <button
          v-for="n in 5"
          :key="n"
          type="button"
          role="radio"
          class="star"
          :class="{ 'star--on': n <= shownRating }"
          :aria-checked="rating === n"
          :aria-label="`${n} étoile${n > 1 ? 's' : ''} — ${LABELS[n]}`"
          @mouseenter="hovered = n"
          @click="rating = n"
        >
          <PhStar :size="34" :weight="n <= shownRating ? 'fill' : 'regular'" />
        </button>
      </div>
      <p class="stars__label">{{ shownRating ? LABELS[shownRating] : 'Touchez une étoile pour noter' }}</p>

      <v-textarea
        v-model="comment"
        rows="4"
        auto-grow
        variant="outlined"
        :counter="MAX_COMMENT"
        :maxlength="MAX_COMMENT"
        placeholder="Qualité, conformité à la description, emballage… (optionnel)"
        label="Votre avis"
      />

      <div class="d-flex flex-column ga-2 mt-2">
        <v-btn color="primary" block size="large" :loading="submitting" :disabled="rating < 1" @click="submit">
          {{ isEdit ? 'Enregistrer' : 'Publier mon avis' }}
        </v-btn>
        <v-btn variant="text" block @click="open = false">Annuler</v-btn>
      </div>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.review-form {
  padding: 20px;
}

.review-form__title {
  margin: 0 0 14px;
  font-family: var(--font-heading);
  font-size: 18px;
  font-weight: 800;
  color: var(--color-neutral-200);
}

.review-form__product {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px;
  margin-bottom: 16px;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-md);
}

.review-form__thumb {
  width: 48px;
  height: 48px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border-radius: var(--radius-sm);
  background: #fff;
}

.review-form__thumb img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.review-form__name {
  font-weight: 700;
  font-size: 14px;
  color: var(--color-neutral-200);
}

.stars {
  display: flex;
  justify-content: center;
  gap: 4px;
}

.star {
  display: flex;
  padding: 4px;
  border: none;
  background: none;
  color: var(--color-neutral-500);
  cursor: pointer;
  transition: transform 0.12s ease, color 0.12s ease;
}

.star:hover {
  transform: scale(1.12);
}

.star--on {
  color: var(--color-accent);
}

.stars__label {
  margin: 6px 0 16px;
  text-align: center;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--color-neutral-300);
  min-height: 20px;
}
</style>
