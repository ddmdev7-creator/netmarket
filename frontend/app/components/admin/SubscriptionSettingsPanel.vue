<script setup lang="ts">
import { PhGift, PhHourglassMedium } from '@phosphor-icons/vue'
import type { SubscriptionPlanRead, SubscriptionSettings } from '~/types/api'

const { apiFetch } = useApi()
const toast = useToastStore()

const [{ data: settings }, { data: plans }] = await Promise.all([
  useAsyncData('admin-subscription-settings', () => apiFetch<SubscriptionSettings>('/admin/subscriptions/settings'), {
    getCachedData: hydrateThenRefetch,
  }),
  useAsyncData('admin-subscription-plans', () => apiFetch<SubscriptionPlanRead[]>('/admin/subscription-plans'), {
    default: () => [],
    getCachedData: hydrateThenRefetch,
  }),
])
const trialPlans = computed(() => plans.value.filter((p) => !p.is_free))

const form = ref({ auto_trial_enabled: false, auto_trial_plan_id: null as string | null, auto_trial_days: '14', grace_days: '7' })
watch(
  settings,
  (s) => {
    if (s)
      form.value = {
        auto_trial_enabled: s.auto_trial_enabled,
        auto_trial_plan_id: s.auto_trial_plan_id,
        auto_trial_days: String(s.auto_trial_days),
        grace_days: String(s.grace_days),
      }
  },
  { immediate: true },
)

const saving = ref(false)
async function save() {
  if (form.value.auto_trial_enabled && !form.value.auto_trial_plan_id) {
    toast.error("Choisissez la formule offerte à l'essai.")
    return
  }
  saving.value = true
  try {
    settings.value = await apiFetch<SubscriptionSettings>('/admin/subscriptions/settings', {
      method: 'PATCH',
      body: {
        auto_trial_enabled: form.value.auto_trial_enabled,
        auto_trial_plan_id: form.value.auto_trial_plan_id,
        auto_trial_days: Math.round(Number(form.value.auto_trial_days)),
        grace_days: Math.round(Number(form.value.grace_days)),
      },
    })
    toast.success('Réglages enregistrés.')
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'enregistrer ces réglages."))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="settings-grid">
    <section class="st-card">
      <header class="st-card__head">
        <span class="st-card__icon" style="--hue: 270"><PhGift :size="20" weight="fill" /></span>
        <div>
          <strong>Essai automatique</strong>
          <p>Offert à chaque boutique au moment de son approbation, une seule fois par formule.</p>
        </div>
        <v-switch v-model="form.auto_trial_enabled" color="primary" hide-details inset density="compact" class="flex-grow-0" />
      </header>
      <div v-if="form.auto_trial_enabled" class="st-card__fields">
        <v-select
          v-model="form.auto_trial_plan_id"
          :items="trialPlans"
          item-title="name"
          item-value="id"
          label="Formule offerte"
          hide-details
        />
        <v-text-field v-model="form.auto_trial_days" label="Durée" suffix="jours" inputmode="numeric" hide-details />
      </div>
    </section>

    <section class="st-card">
      <header class="st-card__head">
        <span class="st-card__icon" style="--hue: 30"><PhHourglassMedium :size="20" weight="fill" /></span>
        <div>
          <strong>Période de grâce</strong>
          <p>
            Après la fin d'un abonnement, le vendeur a ce délai pour choisir ses produits ou se réabonner. Ensuite, les
            produits au-delà du quota Gratuit sont masqués (jamais supprimés).
          </p>
        </div>
      </header>
      <div class="st-card__fields">
        <v-text-field v-model="form.grace_days" label="Durée" suffix="jours" inputmode="numeric" hide-details style="max-width: 180px" />
      </div>
    </section>

    <div>
      <v-btn color="primary" :loading="saving" @click="save">Enregistrer</v-btn>
    </div>
  </div>
</template>

<style scoped>
.settings-grid {
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-width: 720px;
}

.st-card {
  padding: 16px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-divider);
  background: var(--color-neutral-900);
  box-shadow: var(--shadow-sm);
}

.st-card__head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.st-card__head > div {
  flex: 1;
}

.st-card__head p {
  margin: 2px 0 0;
  font-size: 12.5px;
  line-height: 1.45;
  color: var(--color-neutral-400);
}

.st-card__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  flex-shrink: 0;
  border-radius: 12px;
  background: hsl(var(--hue) 70% var(--tint-bg));
  color: hsl(var(--hue) 60% var(--tint-fg));
}

.st-card__fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
  margin-top: 14px;
}
</style>
