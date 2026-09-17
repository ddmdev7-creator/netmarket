<script setup lang="ts">
import { PhFlag, PhStar } from '@phosphor-icons/vue'
import type { ReviewRead } from '~/types/api'

const props = defineProps<{ productId: string }>()

const { apiFetch } = useApi()
const auth = useAuthStore()

const { data: reviews, pending, refresh } = await useAsyncData(
  `product-reviews-${props.productId}`,
  () => apiFetch<ReviewRead[]>(`/products/${props.productId}/reviews`),
  { default: () => [] },
)

defineExpose({ refresh })

// Un seul dialogue de signalement partagé plutôt qu'une instance par avis —
// même pattern que le scanner QR partagé sur les tableaux de bord livreur/
// gestionnaire de point.
const reportTargetId = ref<string | null>(null)
const reportDialogOpen = computed({
  get: () => reportTargetId.value !== null,
  set: (v: boolean) => {
    if (!v) reportTargetId.value = null
  },
})
const reportEndpoint = computed(() => (reportTargetId.value ? `/reviews/${reportTargetId.value}/reports` : ''))

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' })
}
</script>

<template>
  <div>
    <CommonEmptyState v-if="!pending && reviews.length === 0" message="Aucun avis pour l'instant." />

    <div v-for="r in reviews" :key="r.id" class="review-card mb-3">
      <div class="d-flex justify-space-between align-center mb-1">
        <div class="d-flex align-center ga-1">
          <PhStar
            v-for="n in 5"
            :key="n"
            :size="14"
            :weight="n <= r.rating ? 'fill' : 'regular'"
            color="var(--color-accent)"
          />
        </div>
        <button v-if="auth.isAuthenticated" type="button" class="report-btn" @click="reportTargetId = r.id">
          <PhFlag :size="14" />
        </button>
      </div>
      <p v-if="r.comment" class="mb-1 text-meta">{{ r.comment }}</p>
      <div class="text-muted text-fine">{{ formatDate(r.created_at) }}</div>
    </div>

    <CommonReportDialog v-model="reportDialogOpen" :endpoint="reportEndpoint" @reported="refresh" />
  </div>
</template>

<style scoped>
.review-card {
  padding: 10px 0;
  border-bottom: 1px solid var(--color-divider);
}

.report-btn {
  background: none;
  border: none;
  color: var(--color-neutral-500);
  padding: 10px;
  margin: -10px;
  cursor: pointer;
}
</style>
