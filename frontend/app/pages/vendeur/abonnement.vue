<script setup lang="ts">
import {
  PhArrowRight,
  PhCalendarCheck,
  PhCheck,
  PhClockCounterClockwise,
  PhCrown,
  PhGift,
  PhHourglassMedium,
  PhImages,
  PhMegaphone,
  PhPackage,
  PhPercent,
  PhSparkle,
  PhWarningCircle,
} from '@phosphor-icons/vue'
import type { Component } from 'vue'
import type { SubscriptionPlanRead, VendorSubscriptionRead } from '~/types/api'

definePageMeta({ middleware: 'vendor', layout: 'vendeur' })

const { apiFetch } = useApi()
const toast = useToastStore()
const { overview, refresh } = useVendorPlan()
// Données partagées avec le formulaire produit : on les rafraîchit à l'ouverture.
onMounted(refresh)
const NuxtLinkComp = resolveComponent('NuxtLink')

const DAY = 86_400_000

function formatDate(value: string | null | undefined) {
  return value ? new Date(value).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' }) : '—'
}

const current = computed(() => overview.value?.current ?? null)
const plan = computed(() => overview.value?.plan ?? null)

// --- Période en cours : jours restants et barre de temps -----------------------
const period = computed(() => {
  const sub = current.value
  if (!sub?.started_at || !sub.expires_at) return null
  const start = new Date(sub.started_at).getTime()
  const end = new Date(sub.expires_at).getTime()
  const now = Date.now()
  const daysLeft = Math.max(0, Math.ceil((end - now) / DAY))
  const elapsed = Math.min(100, Math.max(0, ((now - start) / (end - start)) * 100))
  return { daysLeft, elapsed, totalDays: Math.round((end - start) / DAY) }
})

const state = computed<'trial' | 'active' | 'grace' | 'free'>(() => {
  if (current.value?.is_trial) return 'trial'
  if (current.value) return 'active'
  if (overview.value?.grace_until) return 'grace'
  return 'free'
})
const stateMeta = {
  trial: { label: 'Essai gratuit', hue: 270 },
  active: { label: 'Actif', hue: 150 },
  grace: { label: 'Terminé — période de grâce', hue: 30 },
  free: { label: 'Formule de base', hue: 215 },
} as const

const urgent = computed(() => period.value !== null && period.value.daysLeft <= (current.value?.is_trial ? 3 : 7))

// --- Quotas ------------------------------------------------------------------------
interface Gauge {
  key: string
  label: string
  icon: Component
  used: number
  limit: number | null
  hint?: string
  to?: string
}
const gauges = computed<Gauge[]>(() => {
  const o = overview.value
  if (!o) return []
  return [
    {
      key: 'products',
      label: 'Produits en vente',
      icon: PhPackage,
      used: o.products.used,
      limit: o.products.limit,
      to: '/vendeur/produits',
    },
    {
      key: 'ai',
      label: 'Améliorations IA ce mois-ci',
      icon: PhSparkle,
      used: o.ai_enhancements.used,
      limit: o.ai_enhancements.limit,
      hint: `Remise à zéro le ${new Date(o.ai_resets_at).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long' })}`,
    },
  ]
})

function gaugePercent(g: Gauge): number {
  if (g.limit === null) return 100
  if (g.limit === 0) return 100
  return Math.min(100, (g.used / g.limit) * 100)
}
function gaugeLevel(g: Gauge): 'ok' | 'warn' | 'full' | 'unlimited' {
  if (g.limit === null) return 'unlimited'
  if (g.used >= g.limit) return 'full'
  return g.used / g.limit >= 0.8 ? 'warn' : 'ok'
}

// --- Formules ------------------------------------------------------------------------
const plans = computed(() => overview.value?.plans ?? [])

function limitLabel(value: number | null, unit: string): string {
  return value === null ? `${unit} illimités` : `${value} ${unit}`
}
function features(p: SubscriptionPlanRead): { icon: Component; text: string; soon?: boolean }[] {
  return [
    { icon: PhPackage, text: p.max_products === null ? 'Produits en vente illimités' : `${p.max_products} produits en vente` },
    { icon: PhImages, text: `${p.max_images_per_product} photos par produit` },
    {
      icon: PhSparkle,
      text:
        p.ai_enhancements_per_month === null
          ? 'Améliorations IA illimitées'
          : p.ai_enhancements_per_month === 0
            ? "Pas d'amélioration IA"
            : `${p.ai_enhancements_per_month} améliorations IA / mois`,
    },
    {
      icon: PhPercent,
      text: p.commission_discount > 0 ? `Commission réduite de ${p.commission_discount} points` : 'Commission standard',
    },
    ...(p.featured_per_month > 0
      ? [{ icon: PhMegaphone, text: `${p.featured_per_month} mises en avant / mois`, soon: true }]
      : []),
  ]
}

function isCurrentPlan(p: SubscriptionPlanRead): boolean {
  return p.id === plan.value?.id
}

// --- Souscription / renouvellement ----------------------------------------------
const pending = computed(() => overview.value?.pending ?? null)
const confirmPlan = ref<SubscriptionPlanRead | null>(null)
// Une nouvelle période payée démarre à la fin de la dernière déjà acquise (hors essai).
const renewalStart = computed(() => {
  const o = overview.value
  if (!o) return null
  const last = o.scheduled ?? (o.current && !o.current.is_trial ? o.current : null)
  return last?.expires_at ?? null
})
const subscribing = ref(false)

async function subscribe() {
  const target = confirmPlan.value
  if (!target?.id) return
  subscribing.value = true
  try {
    await apiFetch<VendorSubscriptionRead>('/subscriptions/subscribe', { method: 'POST', body: { plan_id: target.id } })
    confirmPlan.value = null
    await refresh()
    toast.success('Demande envoyée — en attente de confirmation du paiement.')
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'envoyer cette demande d'abonnement."))
  } finally {
    subscribing.value = false
  }
}

const withdrawing = ref(false)
async function withdraw() {
  if (!pending.value) return
  withdrawing.value = true
  try {
    await apiFetch(`/subscriptions/${pending.value.id}/cancel`, { method: 'POST' })
    await refresh()
    toast.success('Demande retirée.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de retirer cette demande.'))
  } finally {
    withdrawing.value = false
  }
}

// --- Historique ----------------------------------------------------------------------
const statusLabels: Record<string, string> = {
  pending: 'En attente',
  active: 'Actif',
  expired: 'Terminé',
  cancelled: 'Annulé',
}
function historyStatus(sub: VendorSubscriptionRead): string {
  if (sub.status === 'active' && sub.started_at && new Date(sub.started_at).getTime() > Date.now()) return 'Programmé'
  return statusLabels[sub.status] ?? sub.status
}
</script>

<template>
  <div class="dashboard-shell">
    <div class="sub-page">
      <header class="sub-head">
        <h1 class="text-h6">Abonnement</h1>
        <p class="text-muted">Votre formule, vos quotas, et ce que débloquent les formules supérieures.</p>
      </header>

      <template v-if="overview && plan">
        <!-- Formule en cours -->
        <section class="hero" :style="{ '--hue': stateMeta[state].hue }">
          <div class="hero__top">
            <span class="hero__icon"><PhCrown :size="22" weight="fill" /></span>
            <div class="hero__title">
              <span class="hero__eyebrow">Votre formule</span>
              <strong>{{ plan.name }}</strong>
            </div>
            <span class="hero__badge">
              <PhGift v-if="state === 'trial'" :size="13" weight="fill" />
              {{ stateMeta[state].label }}
            </span>
          </div>

          <div v-if="period && current" class="hero__period">
            <div class="hero__days" :class="{ 'hero__days--urgent': urgent }">
              <span class="hero__days-n">{{ period.daysLeft }}</span>
              <span>jour{{ period.daysLeft > 1 ? 's' : '' }} restant{{ period.daysLeft > 1 ? 's' : '' }}</span>
            </div>
            <div class="hero__bar" role="progressbar" :aria-valuenow="Math.round(period.elapsed)" aria-valuemin="0" aria-valuemax="100">
              <span :style="{ width: `${period.elapsed}%` }" />
            </div>
            <div class="hero__dates">
              <span>{{ formatDate(current.started_at) }}</span>
              <span>{{ formatDate(current.expires_at) }}</span>
            </div>
          </div>

          <p v-if="state === 'free'" class="hero__text">
            Vous êtes sur la formule de base. Passez à une formule supérieure pour vendre plus de produits, améliorer vos
            photos avec l'IA et payer moins de commission.
          </p>
          <p v-else-if="state === 'grace'" class="hero__text hero__text--warn">
            <PhWarningCircle :size="16" />
            <span>
              Votre abonnement est terminé. Jusqu'au <strong>{{ formatDate(overview.grace_until) }}</strong>, choisissez les
              produits à garder en vente (formule {{ plan.name }} : {{ limitLabel(overview.products.limit, 'produits') }}) ou
              réabonnez-vous — ensuite les produits en trop seront masqués, jamais supprimés.
            </span>
          </p>
          <p v-else-if="state === 'trial' && period" class="hero__text">
            Profitez de toute la formule {{ plan.name }} gratuitement. Sans engagement : à la fin de l'essai, vous
            repassez à la formule de base sauf si vous vous abonnez.
          </p>

          <div v-if="overview.scheduled" class="hero__scheduled">
            <PhCalendarCheck :size="16" />
            <span>
              Renouvelé : {{ overview.scheduled.plan.name }} du {{ formatDate(overview.scheduled.started_at) }} au
              {{ formatDate(overview.scheduled.expires_at) }}.
            </span>
          </div>
        </section>

        <!-- Demande en attente -->
        <section v-if="pending" class="pending">
          <PhHourglassMedium :size="20" />
          <div class="pending__body">
            <strong>Demande {{ pending.plan.name }} en attente de paiement</strong>
            <span>
              Envoyez {{ formatGnf(pending.plan.price_gnf) }} par mobile money puis contactez le support : un administrateur
              confirmera votre abonnement.
            </span>
          </div>
          <v-btn variant="text" size="small" :loading="withdrawing" @click="withdraw">Retirer la demande</v-btn>
        </section>

        <!-- Quotas -->
        <h2 class="sub-section">Votre utilisation</h2>
        <div class="gauges">
          <component
            :is="g.to ? NuxtLinkComp : 'div'"
            v-for="g in gauges"
            :key="g.key"
            :to="g.to"
            class="gauge"
            :class="`gauge--${gaugeLevel(g)}`"
          >
            <div class="gauge__head">
              <component :is="g.icon" :size="18" />
              <span>{{ g.label }}</span>
            </div>
            <div class="gauge__value">
              <strong>{{ g.used }}</strong>
              <span v-if="g.limit !== null"> / {{ g.limit }}</span>
              <span v-else> · illimité</span>
            </div>
            <div class="gauge__bar"><span :style="{ width: `${gaugePercent(g)}%` }" /></div>
            <span v-if="gaugeLevel(g) === 'full'" class="gauge__hint gauge__hint--full">
              {{ g.limit === 0 ? 'Non inclus dans votre formule' : 'Quota atteint' }}
            </span>
            <span v-else-if="g.hint" class="gauge__hint">{{ g.hint }}</span>
          </component>

          <div class="gauge gauge--static">
            <div class="gauge__head"><PhImages :size="18" /><span>Photos par produit</span></div>
            <div class="gauge__value"><strong>{{ overview.max_images_per_product }}</strong></div>
            <span class="gauge__hint">Par produit et par variante</span>
          </div>

          <div class="gauge gauge--static">
            <div class="gauge__head"><PhPercent :size="18" /><span>Commission sur vos ventes</span></div>
            <div class="gauge__value">
              <strong>{{ overview.effective_commission_rate }} %</strong>
              <s v-if="overview.effective_commission_rate < overview.base_commission_rate" class="gauge__old">
                {{ overview.base_commission_rate }} %
              </s>
            </div>
            <span class="gauge__hint">
              {{ overview.effective_commission_rate < overview.base_commission_rate ? 'Réduction de votre formule appliquée' : 'Taux standard' }}
            </span>
          </div>
        </div>

        <!-- Formules -->
        <h2 class="sub-section">Formules</h2>
        <div class="plans">
          <article
            v-for="p in plans"
            :key="p.id ?? p.name"
            class="plan"
            :class="{ 'plan--current': isCurrentPlan(p), 'plan--highlight': p.sort_order === 1 && !p.is_free }"
          >
            <span v-if="isCurrentPlan(p)" class="plan__tag">Votre formule</span>
            <span v-else-if="p.sort_order === 1 && !p.is_free" class="plan__tag plan__tag--pop">Le plus choisi</span>
            <h3 class="plan__name">{{ p.name }}</h3>
            <div class="plan__price">
              <template v-if="p.is_free"><strong>0 GNF</strong><span>pour toujours</span></template>
              <template v-else>
                <strong>{{ formatGnf(p.price_gnf) }}</strong>
                <span>/ {{ p.duration_days }} jours</span>
              </template>
            </div>
            <p v-if="p.description" class="plan__desc">{{ p.description }}</p>
            <ul class="plan__features">
              <li v-for="f in features(p)" :key="f.text">
                <PhCheck :size="14" weight="bold" class="plan__check" />
                <span>{{ f.text }}</span>
                <span v-if="f.soon" class="plan__soon">bientôt</span>
              </li>
            </ul>
            <v-btn
              v-if="!p.is_free"
              :color="isCurrentPlan(p) ? undefined : 'primary'"
              :variant="isCurrentPlan(p) ? 'outlined' : 'flat'"
              block
              rounded="lg"
              :disabled="!!pending"
              class="plan__cta"
              @click="confirmPlan = p"
            >
              {{ isCurrentPlan(p) && !current?.is_trial ? 'Renouveler' : "S'abonner" }}
              <PhArrowRight :size="16" class="ml-1" />
            </v-btn>
          </article>
        </div>
        <p class="text-muted plans__note">
          Paiement par mobile money, confirmé par l'administration. Un abonnement payé n'est pas remboursable : il reste
          actif jusqu'à sa date de fin. Renouveler avant la fin ajoute la nouvelle période à la suite.
        </p>

        <!-- Historique -->
        <template v-if="overview.history.length">
          <h2 class="sub-section"><PhClockCounterClockwise :size="18" /> Historique</h2>
          <div class="history">
            <div v-for="h in overview.history" :key="h.id" class="history__row">
              <div>
                <strong>{{ h.plan.name }}</strong>
                <span v-if="h.is_trial" class="history__trial">Essai</span>
                <div class="text-muted history__dates">
                  <template v-if="h.started_at">{{ formatDate(h.started_at) }} → {{ formatDate(h.expires_at) }}</template>
                  <template v-else>Demandé le {{ formatDate(h.created_at) }}</template>
                  <template v-if="h.cancel_reason"> · {{ h.cancel_reason }}</template>
                </div>
              </div>
              <span class="history__status" :class="`history__status--${h.status}`">{{ historyStatus(h) }}</span>
            </div>
          </div>
        </template>
      </template>
    </div>

    <v-dialog :model-value="!!confirmPlan" max-width="440" @update:model-value="(v) => !v && (confirmPlan = null)">
      <v-card v-if="confirmPlan" class="pa-5">
        <div class="text-h6 mb-1">Formule {{ confirmPlan.name }}</div>
        <p class="text-muted mb-4" style="font-size: 13.5px">
          {{ formatGnf(confirmPlan.price_gnf) }} pour {{ confirmPlan.duration_days }} jours.
          <template v-if="renewalStart">La nouvelle période commencera le <strong>{{ formatDate(renewalStart) }}</strong>, à la suite de l'actuelle.</template>
          <template v-else-if="current?.is_trial">Elle remplacera votre essai dès la confirmation du paiement.</template>
          <template v-else>Elle démarre dès la confirmation du paiement.</template>
        </p>
        <v-alert type="info" variant="tonal" density="compact" class="mb-4" style="font-size: 13px">
          Envoyez le paiement par mobile money puis contactez le support. Un abonnement payé n'est pas remboursable.
        </v-alert>
        <div class="d-flex ga-2">
          <v-btn variant="outlined" class="flex-grow-1" @click="confirmPlan = null">Annuler</v-btn>
          <v-btn color="primary" class="flex-grow-1" :loading="subscribing" @click="subscribe">Envoyer la demande</v-btn>
        </div>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.sub-page {
  max-width: 1080px;
  margin: 0 auto;
}

.sub-head {
  margin-bottom: 16px;
}

.sub-head p {
  margin: 2px 0 0;
  font-size: 13px;
}

.sub-section {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 28px 0 12px;
  font-family: var(--font-heading);
  font-size: 16px;
  font-weight: 800;
  color: var(--color-neutral-100);
}

/* --- Formule en cours --- */
.hero {
  padding: 18px;
  border-radius: var(--radius-lg);
  border: 1px solid hsl(var(--hue) 60% 50% / 0.3);
  background:
    radial-gradient(circle at 100% 0%, hsl(var(--hue) 80% 60% / 0.16), transparent 55%),
    var(--color-neutral-900);
  box-shadow: var(--shadow-sm);
}

.hero__top {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.hero__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 14px;
  color: #fff;
  background: linear-gradient(135deg, hsl(var(--hue) 70% 55%), hsl(calc(var(--hue) + 30) 70% 45%));
}

.hero__title {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.hero__eyebrow {
  font-size: 11.5px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-neutral-500);
}

.hero__title strong {
  font-family: var(--font-heading);
  font-size: 24px;
  font-weight: 800;
  line-height: 1.1;
  color: var(--color-neutral-100);
}

.hero__badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 999px;
  background: hsl(var(--hue) 70% var(--tint-bg));
  color: hsl(var(--hue) 60% var(--tint-fg));
  font-size: 12px;
  font-weight: 700;
}

.hero__period {
  margin-top: 16px;
}

.hero__days {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 8px;
  font-size: 13.5px;
  color: var(--color-neutral-300);
}

.hero__days-n {
  font-family: var(--font-heading);
  font-size: 34px;
  font-weight: 800;
  line-height: 1;
  color: var(--color-neutral-100);
}

.hero__days--urgent .hero__days-n {
  color: var(--color-warning, #e0822e);
}

.hero__bar {
  height: 10px;
  border-radius: 999px;
  background: var(--color-neutral-800);
  overflow: hidden;
}

.hero__bar span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, hsl(var(--hue) 70% 55%), hsl(calc(var(--hue) + 30) 70% 50%));
  transition: width 0.6s ease;
}

.hero__dates {
  display: flex;
  justify-content: space-between;
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-neutral-500);
}

.hero__text {
  display: flex;
  gap: 8px;
  margin: 14px 0 0;
  font-size: 13.5px;
  line-height: 1.5;
  color: var(--color-neutral-300);
}

.hero__text--warn {
  padding: 10px 12px;
  border-radius: var(--radius-md);
  background: hsl(30 90% var(--tint-bg-soft, 17%));
  color: hsl(30 70% var(--tint-fg));
}

.hero__text--warn svg {
  flex-shrink: 0;
  margin-top: 2px;
}

.hero__scheduled {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  font-size: 13px;
  color: hsl(150 55% var(--tint-fg));
}

/* --- Demande en attente --- */
.pending {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: var(--radius-md);
  border: 1px dashed hsl(38 80% 50% / 0.6);
  background: hsl(38 90% var(--tint-bg-soft, 17%));
  color: hsl(38 70% var(--tint-fg));
}

.pending__body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1 1 260px;
  font-size: 13px;
}

/* --- Jauges --- */
.gauges {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 12px;
}

.gauge {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-divider);
  background: var(--color-neutral-900);
  color: inherit;
  text-decoration: none;
  --gauge: var(--color-primary);
}

a.gauge:hover {
  border-color: var(--color-primary-300);
}

.gauge--warn {
  --gauge: var(--color-warning, #e0822e);
}

.gauge--full {
  --gauge: var(--color-error);
}

.gauge--unlimited {
  --gauge: hsl(150 55% 45%);
}

.gauge__head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-neutral-300);
}

.gauge__head svg {
  color: var(--gauge);
}

.gauge--static .gauge__head svg {
  color: var(--color-primary);
}

.gauge__value {
  display: flex;
  align-items: baseline;
  gap: 4px;
  font-size: 13px;
  color: var(--color-neutral-400);
}

.gauge__value strong {
  font-family: var(--font-heading);
  font-size: 24px;
  font-weight: 800;
  color: var(--color-neutral-100);
}

.gauge__old {
  margin-left: 6px;
  color: var(--color-neutral-500);
}

.gauge__bar {
  height: 8px;
  border-radius: 999px;
  background: var(--color-neutral-800);
  overflow: hidden;
}

.gauge__bar span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--gauge);
  transition: width 0.6s ease;
}

.gauge--unlimited .gauge__bar span {
  opacity: 0.35;
}

.gauge__hint {
  font-size: 11.5px;
  color: var(--color-neutral-500);
}

.gauge__hint--full {
  color: var(--color-error);
  font-weight: 600;
}

/* --- Formules --- */
.plans {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 14px;
  align-items: stretch;
}

.plan {
  position: relative;
  display: flex;
  flex-direction: column;
  padding: 20px 18px 18px;
  border-radius: var(--radius-lg);
  border: 1.5px solid var(--color-divider);
  background: var(--color-neutral-900);
}

.plan--highlight {
  border-color: color-mix(in srgb, var(--color-primary) 55%, transparent);
  box-shadow: 0 8px 28px -12px color-mix(in srgb, var(--color-primary) 45%, transparent);
}

.plan--current {
  border-color: hsl(150 55% 45%);
}

.plan__tag {
  position: absolute;
  top: -11px;
  left: 16px;
  padding: 3px 10px;
  border-radius: 999px;
  background: hsl(150 55% 42%);
  color: #fff;
  font-size: 11px;
  font-weight: 800;
}

.plan__tag--pop {
  background: var(--color-primary);
}

.plan__name {
  margin: 0;
  font-family: var(--font-heading);
  font-size: 18px;
  font-weight: 800;
  color: var(--color-neutral-100);
}

.plan__price {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin: 6px 0 8px;
  font-size: 12.5px;
  color: var(--color-neutral-500);
}

.plan__price strong {
  font-family: var(--font-heading);
  font-size: 22px;
  font-weight: 800;
  color: var(--color-neutral-100);
}

.plan__desc {
  margin: 0 0 12px;
  font-size: 12.5px;
  line-height: 1.45;
  color: var(--color-neutral-400);
}

.plan__features {
  flex: 1;
  margin: 0 0 16px;
  padding: 0;
  list-style: none;
}

.plan__features li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 0;
  font-size: 13px;
  color: var(--color-neutral-200);
}

.plan__check {
  flex-shrink: 0;
  color: hsl(150 55% 45%);
}

.plan__soon {
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--color-neutral-800);
  color: var(--color-neutral-500);
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
}

.plans__note {
  margin: 12px 0 0;
  font-size: 12px;
  line-height: 1.5;
}

/* --- Historique --- */
.history {
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-divider);
  background: var(--color-neutral-900);
  overflow: hidden;
}

.history__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--color-divider);
  font-size: 13.5px;
}

.history__row:last-child {
  border-bottom: none;
}

.history__dates {
  font-size: 12px;
  margin-top: 2px;
}

.history__trial {
  margin-left: 6px;
  padding: 1px 7px;
  border-radius: 999px;
  background: hsl(270 70% var(--tint-bg));
  color: hsl(270 60% var(--tint-fg));
  font-size: 11px;
  font-weight: 700;
}

.history__status {
  flex-shrink: 0;
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--color-neutral-800);
  color: var(--color-neutral-400);
  font-size: 12px;
  font-weight: 700;
}

.history__status--active {
  background: hsl(150 70% var(--tint-bg));
  color: hsl(150 55% var(--tint-fg));
}

.history__status--pending {
  background: hsl(38 90% var(--tint-bg));
  color: hsl(38 70% var(--tint-fg));
}
</style>
