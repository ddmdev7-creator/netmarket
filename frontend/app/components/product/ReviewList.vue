<script setup lang="ts">
import { PhFlag, PhSealCheck, PhStar } from '@phosphor-icons/vue'
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

// Résumé en tête de liste : moyenne + répartition par nombre d'étoiles.
const summary = computed(() => {
  const count = reviews.value.length
  const byStars = [5, 4, 3, 2, 1].map((stars) => {
    const n = reviews.value.filter((r) => r.rating === stars).length
    return { stars, n, pct: count ? Math.round((n / count) * 100) : 0 }
  })
  const average = count ? reviews.value.reduce((sum, r) => sum + r.rating, 0) / count : 0
  return { count, average, byStars }
})

// Modifié = changé plus d'une minute après publication (created_at et
// updated_at diffèrent de quelques ms à la création).
const wasEdited = (r: ReviewRead) => new Date(r.updated_at).getTime() - new Date(r.created_at).getTime() > 60_000

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' })
}
</script>

<template>
  <div>
    <div v-if="summary.count" class="summary mb-4">
      <div class="summary__score">
        <div class="summary__avg">{{ summary.average.toFixed(1).replace('.', ',') }}</div>
        <div class="d-flex ga-1">
          <PhStar
            v-for="n in 5"
            :key="n"
            :size="15"
            :weight="n <= Math.round(summary.average) ? 'fill' : 'regular'"
            color="var(--color-accent)"
          />
        </div>
        <div class="text-muted text-fine mt-1">{{ summary.count }} avis</div>
      </div>
      <div class="summary__bars">
        <div v-for="row in summary.byStars" :key="row.stars" class="bar-row">
          <span class="bar-row__label">{{ row.stars }}</span>
          <PhStar :size="11" weight="fill" color="var(--color-accent)" />
          <div class="bar"><div class="bar__fill" :style="{ width: `${row.pct}%` }" /></div>
          <span class="bar-row__n">{{ row.n }}</span>
        </div>
      </div>
    </div>

    <CommonEmptyState v-if="!pending && reviews.length === 0" message="Aucun avis pour l'instant." />

    <div v-for="r in reviews" :key="r.id" class="review-card">
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
        <button
          v-if="auth.isAuthenticated"
          type="button"
          class="report-btn"
          aria-label="Signaler cet avis"
          @click="reportTargetId = r.id"
        >
          <PhFlag :size="14" />
        </button>
      </div>
      <div class="review-card__author">
        <span>{{ r.author_name ?? 'Acheteur' }}</span>
        <span class="verified"><PhSealCheck :size="13" weight="fill" /> Achat vérifié</span>
      </div>
      <p v-if="r.comment" class="review-card__comment">{{ r.comment }}</p>
      <div class="text-muted text-fine">
        {{ formatDate(r.created_at) }}<span v-if="wasEdited(r)"> · modifié</span>
      </div>
    </div>

    <CommonReportDialog v-model="reportDialogOpen" :endpoint="reportEndpoint" @reported="refresh" />
  </div>
</template>

<style scoped>
.summary {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 14px;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-md);
}

.summary__score {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: none;
}

.summary__avg {
  font-family: var(--font-heading);
  font-size: 32px;
  font-weight: 800;
  line-height: 1.1;
  color: var(--color-neutral-200);
}

.summary__bars {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.bar-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-neutral-400);
}

.bar-row__label {
  width: 8px;
  text-align: right;
}

.bar-row__n {
  width: 22px;
  text-align: right;
}

.bar {
  flex: 1;
  height: 7px;
  border-radius: 999px;
  background: var(--color-neutral-800);
  overflow: hidden;
}

.bar__fill {
  height: 100%;
  border-radius: 999px;
  background: var(--color-accent);
}

.review-card {
  padding: 12px 0;
  border-bottom: 1px solid var(--color-divider);
}

.review-card__author {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 10px;
  margin-bottom: 4px;
  font-size: 13px;
  font-weight: 700;
  color: var(--color-neutral-200);
}

.verified {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--color-success);
}

.review-card__comment {
  margin: 0 0 4px;
  font-size: 13.5px;
  line-height: 1.5;
  color: var(--color-neutral-300);
  white-space: pre-line;
  overflow-wrap: anywhere;
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
