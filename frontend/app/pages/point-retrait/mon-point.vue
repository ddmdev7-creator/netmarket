<script setup lang="ts">
/**
 * « Mon point » : ce que voient les clients (nom, adresse, horaires, note)
 * et les horaires, modifiables par le gestionnaire.
 */
import { PhClock, PhMapPin, PhStar, PhStorefront } from '@phosphor-icons/vue'
import type { PickupPointRead } from '~/types/api'

definePageMeta({ middleware: 'pickup-manager', layout: 'point-retrait' })

const { apiFetch } = useApi()
const toast = useToastStore()

const { data: point, refresh } = await useAsyncData(
  'pickup-manager-point',
  () => apiFetch<PickupPointRead>('/pickup-point-managers/me/point'),
  { getCachedData: hydrateThenRefetch },
)

const hours = ref('')
watch(point, (p) => (hours.value = p?.opening_hours ?? ''), { immediate: true })
const saving = ref(false)

async function saveHours() {
  saving.value = true
  try {
    await apiFetch('/pickup-point-managers/me/point', { method: 'PATCH', body: { opening_hours: hours.value.trim() } })
    await refresh()
    toast.success('Horaires mis à jour : ils sont affichés aux clients.')
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'enregistrer les horaires."))
  } finally {
    saving.value = false
  }
}

const mapUrl = computed(() =>
  point.value?.latitude != null
    ? `https://www.openstreetmap.org/?mlat=${point.value.latitude}&mlon=${point.value.longitude}#map=18/${point.value.latitude}/${point.value.longitude}`
    : null,
)
</script>

<template>
  <div class="px-4 pb-4 mp">
    <h1 class="mp__title">Mon point de retrait</h1>

    <section v-if="point" class="mp-card">
      <div class="mp-line"><PhStorefront :size="18" /><div><div class="mp-line__label">Nom</div><div class="mp-line__value">{{ point.name }}</div></div></div>
      <div class="mp-line">
        <PhMapPin :size="18" />
        <div>
          <div class="mp-line__label">Adresse</div>
          <div class="mp-line__value">{{ point.zone }}</div>
          <a v-if="mapUrl" :href="mapUrl" target="_blank" rel="noopener" class="mp-link">Voir sur la carte</a>
        </div>
      </div>
      <div class="mp-line">
        <PhStar :size="18" />
        <div>
          <div class="mp-line__label">Avis des clients</div>
          <div class="mp-line__value">
            <template v-if="point.review_count">{{ point.average_rating?.toFixed(1) }} / 5 · {{ point.review_count }} avis</template>
            <template v-else>Pas encore d'avis</template>
          </div>
        </div>
      </div>
      <v-chip v-if="!point.is_active" color="error" variant="tonal" size="small" class="mt-2">
        Point désactivé par l'équipe Ndjouri
      </v-chip>
    </section>

    <section v-if="point" class="mp-card">
      <h2 class="mp-card__title"><PhClock :size="18" /> Horaires d'ouverture</h2>
      <p class="text-muted text-meta">Affichés aux clients qui choisissent votre point. Exemple : « Lun–Sam 8h–20h, Dim 10h–14h ».</p>
      <v-text-field v-model="hours" label="Horaires" variant="outlined" hide-details class="mb-3" />
      <v-btn color="primary" :loading="saving" :disabled="hours.trim().length < 3" @click="saveHours">Enregistrer</v-btn>
    </section>

    <p class="text-muted text-fine">
      Pour changer le nom, l'adresse ou la position du point, contactez l'équipe Ndjouri.
    </p>
  </div>
</template>

<style scoped>
.mp {
  max-width: 640px;
  margin: 0 auto;
}

.mp__title {
  margin: 14px 0;
  font-family: var(--font-heading);
  font-size: 22px;
  font-weight: 800;
}

.mp-card {
  margin-bottom: 12px;
  padding: 16px;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-md);
  background: var(--color-neutral-900);
}

.mp-card__title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 6px;
  font-family: var(--font-heading);
  font-size: 16px;
  font-weight: 800;
}

.mp-line {
  display: flex;
  gap: 12px;
  padding: 8px 0;
  color: var(--color-neutral-400);
}

.mp-line + .mp-line {
  border-top: 1px solid var(--color-divider);
}

.mp-line__label {
  font-size: 12px;
}

.mp-line__value {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-neutral-200);
}

.mp-link {
  font-size: 12.5px;
  color: var(--color-primary);
}
</style>
