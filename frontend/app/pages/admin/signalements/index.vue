<script setup lang="ts">
import { PhStar } from '@phosphor-icons/vue'
import type { ReportRead, ReportStatus } from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const { apiFetch } = useApi()
const toast = useToastStore()

const tab = ref<ReportStatus>('pending')
const tabs: { value: ReportStatus; label: string }[] = [
  { value: 'pending', label: 'En attente' },
  { value: 'dismissed', label: 'Rejetés' },
  { value: 'actioned', label: 'Traités' },
]

const { data: reports, pending, refresh } = await useAsyncData(
  'admin-reports',
  () => apiFetch<ReportRead[]>('/admin/reports', { query: { status: tab.value } }),
  { default: () => [], getCachedData: hydrateThenRefetch },
)
watch(tab, () => refresh())

const resolvingId = ref<string | null>(null)
const confirmActionId = ref<string | null>(null)

// Comme /admin/livreurs : la liste courante ne montre que le statut de
// l'onglet actif, donc après résolution on retire l'élément localement
// plutôt que de re-filtrer côté client.
async function resolve(report: ReportRead, status: ReportStatus) {
  resolvingId.value = report.id
  try {
    await apiFetch(`/admin/reports/${report.id}`, { method: 'PATCH', body: { status } })
    reports.value = reports.value.filter((r) => r.id !== report.id)
    toast.success(status === 'dismissed' ? 'Signalement rejeté.' : 'Signalement traité.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de mettre à jour ce signalement.'))
  } finally {
    resolvingId.value = null
    confirmActionId.value = null
  }
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <div class="dashboard-shell">
    <h1 class="text-h6 mb-4">Signalements</h1>

    <v-btn-toggle v-model="tab" mandatory density="comfortable" divided class="mb-4 flex-wrap">
      <v-btn v-for="t in tabs" :key="t.value" :value="t.value" size="small">{{ t.label }}</v-btn>
    </v-btn-toggle>

    <CommonEmptyState v-if="!pending && reports.length === 0" message="Aucun signalement dans cette catégorie." />

    <v-card v-for="r in reports" :key="r.id" class="mb-3 pa-3">
      <div class="d-flex justify-space-between align-center mb-2">
        <v-chip size="x-small" variant="tonal" :color="r.report_type === 'product' ? 'primary' : 'secondary'">
          {{ r.report_type === 'product' ? 'Produit' : 'Avis' }}
        </v-chip>
        <span class="text-muted" style="font-size: 11.5px">{{ formatDate(r.created_at) }}</span>
      </div>

      <div class="mb-2" style="font-size: 13px">
        <template v-if="r.report_type === 'product'">
          <strong>{{ r.product_name ?? 'Produit supprimé' }}</strong>
        </template>
        <template v-else>
          <div class="d-flex align-center ga-1 mb-1">
            <PhStar
              v-for="n in 5"
              :key="n"
              :size="12"
              :weight="r.review_rating && n <= r.review_rating ? 'fill' : 'regular'"
              color="var(--color-primary)"
            />
          </div>
          <span class="text-muted">{{ r.review_comment ?? 'Avis supprimé' }}</span>
        </template>
      </div>

      <div class="text-muted mb-3" style="font-size: 12px">Motif : {{ r.reason }}</div>
      <div v-if="r.admin_note" class="text-muted mb-3" style="font-size: 11.5px">Note admin : {{ r.admin_note }}</div>

      <div v-if="r.status === 'pending'" class="d-flex ga-2">
        <v-btn
          variant="outlined"
          size="small"
          class="flex-grow-1"
          :loading="resolvingId === r.id"
          @click="resolve(r, 'dismissed')"
        >
          Rejeter
        </v-btn>
        <v-btn color="error" size="small" class="flex-grow-1" :loading="resolvingId === r.id" @click="confirmActionId = r.id">
          Agir
        </v-btn>
      </div>
    </v-card>

    <v-dialog :model-value="!!confirmActionId" max-width="360" @update:model-value="(v) => !v && (confirmActionId = null)">
      <v-card class="pa-5">
        <div class="text-subtitle-1 mb-2">Confirmer l'action ?</div>
        <p class="text-muted mb-4" style="font-size: 13px">
          Le produit signalé sera désactivé, ou l'avis signalé sera supprimé — action irréversible.
        </p>
        <div class="d-flex ga-2">
          <v-btn variant="outlined" class="flex-grow-1" @click="confirmActionId = null">Annuler</v-btn>
          <v-btn
            color="error"
            class="flex-grow-1"
            :loading="!!resolvingId"
            @click="resolve(reports.find((r) => r.id === confirmActionId)!, 'actioned')"
          >
            Confirmer
          </v-btn>
        </div>
      </v-card>
    </v-dialog>
  </div>
</template>
