<script setup lang="ts">
import { PhImages, PhMegaphone, PhPackage, PhPencilSimple, PhPercent, PhPlus, PhSparkle } from '@phosphor-icons/vue'
import type { SubscriptionPlanRead, SubscriptionPlanWrite } from '~/types/api'

// Formules d'abonnement et leurs quotas (voir backend app/subscriptions/quotas.py).
// « Gratuit » porte les quotas de base : modifiable, mais jamais vendue.
const { apiFetch } = useApi()
const toast = useToastStore()

const { data: plans, refresh } = await useAsyncData(
  'admin-subscription-plans',
  () => apiFetch<SubscriptionPlanRead[]>('/admin/subscription-plans'),
  { default: () => [], getCachedData: hydrateThenRefetch },
)
defineExpose({ refresh })

function unlimited(value: number | null, unit: string) {
  return value === null ? 'Illimité' : `${value} ${unit}`
}

interface PlanForm {
  name: string
  price_gnf: string
  duration_days: string
  description: string
  is_active: boolean
  sort_order: string
  max_products: string
  products_unlimited: boolean
  max_images_per_product: string
  ai_enhancements_per_month: string
  ai_unlimited: boolean
  featured_per_month: string
  commission_discount: string
}

const dialog = ref(false)
const editing = ref<SubscriptionPlanRead | null>(null)
const form = ref<PlanForm>(blankForm())
const saving = ref(false)

function blankForm(): PlanForm {
  return {
    name: '',
    price_gnf: '',
    duration_days: '30',
    description: '',
    is_active: true,
    sort_order: String(plans.value?.length ?? 0),
    max_products: '50',
    products_unlimited: false,
    max_images_per_product: '8',
    ai_enhancements_per_month: '50',
    ai_unlimited: false,
    featured_per_month: '0',
    commission_discount: '0',
  }
}

function openCreate() {
  editing.value = null
  form.value = blankForm()
  dialog.value = true
}

function openEdit(plan: SubscriptionPlanRead) {
  editing.value = plan
  form.value = {
    name: plan.name,
    price_gnf: String(plan.price_gnf),
    duration_days: String(plan.duration_days),
    description: plan.description ?? '',
    is_active: plan.is_active,
    sort_order: String(plan.sort_order),
    max_products: plan.max_products === null ? '' : String(plan.max_products),
    products_unlimited: plan.max_products === null,
    max_images_per_product: String(plan.max_images_per_product),
    ai_enhancements_per_month: plan.ai_enhancements_per_month === null ? '' : String(plan.ai_enhancements_per_month),
    ai_unlimited: plan.ai_enhancements_per_month === null,
    featured_per_month: String(plan.featured_per_month),
    commission_discount: String(plan.commission_discount),
  }
  dialog.value = true
}

function int(value: string): number {
  return Math.round(Number(String(value).replace(',', '.')))
}

async function save() {
  const f = form.value
  const isFree = editing.value?.is_free ?? false
  const body: SubscriptionPlanWrite = {
    name: f.name.trim(),
    description: f.description.trim() || null,
    sort_order: int(f.sort_order) || 0,
    max_products: f.products_unlimited ? null : int(f.max_products),
    max_images_per_product: int(f.max_images_per_product),
    ai_enhancements_per_month: f.ai_unlimited ? null : int(f.ai_enhancements_per_month),
    featured_per_month: int(f.featured_per_month) || 0,
    commission_discount: Number(String(f.commission_discount).replace(',', '.')) || 0,
    ...(isFree ? {} : { price_gnf: int(f.price_gnf), duration_days: int(f.duration_days), is_active: f.is_active }),
  }
  const numbers = [body.max_images_per_product, ...(isFree ? [] : [body.price_gnf, body.duration_days])]
  if (body.name!.length < 2 || numbers.some((n) => n === undefined || !Number.isFinite(n) || n < 0)) {
    toast.error('Vérifiez le nom, le prix, la durée et les quotas.')
    return
  }
  saving.value = true
  try {
    if (editing.value?.id) {
      await apiFetch(`/admin/subscription-plans/${editing.value.id}`, { method: 'PATCH', body })
    } else {
      await apiFetch('/admin/subscription-plans', { method: 'POST', body })
    }
    dialog.value = false
    await refresh()
    toast.success('Formule enregistrée.')
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'enregistrer cette formule."))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div>
    <div class="d-flex justify-space-between align-center flex-wrap ga-2 mb-3">
      <p class="text-muted mb-0" style="font-size: 13px; max-width: 640px">
        Les quotas s'appliquent immédiatement à tous les vendeurs de la formule. « Gratuit » fixe les quotas de base
        (sans abonnement) ; une formule hors vente reste active pour ceux qui l'ont déjà.
      </p>
      <v-btn color="primary" @click="openCreate"><PhPlus :size="16" class="mr-1" /> Formule</v-btn>
    </div>

    <div class="plans-admin">
      <article v-for="p in plans" :key="p.id ?? p.name" class="pa-card" :class="{ 'pa-card--off': !p.is_active && !p.is_free }">
        <header class="pa-card__head">
          <div>
            <strong class="pa-card__name">{{ p.name }}</strong>
            <div class="pa-card__price">
              <template v-if="p.is_free">Formule de base · gratuite</template>
              <template v-else>{{ formatGnf(p.price_gnf) }} / {{ p.duration_days }} j</template>
            </div>
          </div>
          <span v-if="p.is_free" class="pf-tag pf-tag--primary">Base</span>
          <span v-else-if="p.is_active" class="pf-tag pf-tag--success">En vente</span>
          <span v-else class="pf-tag">Hors vente</span>
        </header>
        <ul class="pa-card__quotas">
          <li><PhPackage :size="15" /> {{ unlimited(p.max_products, 'produits') }}</li>
          <li><PhImages :size="15" /> {{ p.max_images_per_product }} photos / produit</li>
          <li><PhSparkle :size="15" /> {{ unlimited(p.ai_enhancements_per_month, 'IA / mois') }}</li>
          <li><PhPercent :size="15" /> {{ p.commission_discount > 0 ? `−${p.commission_discount} pts de commission` : "Commission standard" }}</li>
          <li><PhMegaphone :size="15" /> {{ p.featured_per_month }} mises en avant / mois</li>
        </ul>
        <v-btn variant="tonal" color="primary" size="small" @click="openEdit(p)">
          <PhPencilSimple :size="15" class="mr-1" /> Modifier
        </v-btn>
      </article>
    </div>

    <v-dialog v-model="dialog" max-width="520" scrollable>
      <v-card class="pa-5">
        <div class="text-h6 mb-4">{{ editing ? `Modifier « ${editing.name} »` : 'Nouvelle formule' }}</div>

        <v-text-field v-model="form.name" label="Nom" class="mb-2" hide-details="auto" />
        <v-textarea v-model="form.description" label="Accroche (affichée aux vendeurs)" rows="2" auto-grow maxlength="300" class="mb-2" hide-details="auto" />

        <div v-if="!editing?.is_free" class="pa-grid mb-2">
          <v-text-field v-model="form.price_gnf" label="Prix" suffix="GNF" inputmode="numeric" hide-details="auto" />
          <v-text-field v-model="form.duration_days" label="Durée" suffix="jours" inputmode="numeric" hide-details="auto" />
        </div>

        <div class="pa-subtitle">Quotas</div>
        <div class="pa-grid">
          <div>
            <v-text-field v-model="form.max_products" label="Produits en vente" inputmode="numeric" :disabled="form.products_unlimited" hide-details />
            <v-checkbox v-model="form.products_unlimited" label="Illimité" density="compact" hide-details />
          </div>
          <div>
            <v-text-field v-model="form.ai_enhancements_per_month" label="Améliorations IA / mois" inputmode="numeric" :disabled="form.ai_unlimited" hide-details />
            <v-checkbox v-model="form.ai_unlimited" label="Illimité" density="compact" hide-details />
          </div>
          <v-text-field v-model="form.max_images_per_product" label="Photos par produit" inputmode="numeric" hide-details="auto" />
          <v-text-field v-model="form.commission_discount" label="Réduction de commission" suffix="points" inputmode="decimal" hide-details="auto" />
          <v-text-field v-model="form.featured_per_month" label="Mises en avant / mois" hint="Bientôt disponible" persistent-hint inputmode="numeric" />
          <v-text-field v-model="form.sort_order" label="Ordre d'affichage" inputmode="numeric" hide-details="auto" />
        </div>

        <v-switch v-if="!editing?.is_free" v-model="form.is_active" label="En vente" color="primary" density="compact" hide-details class="mt-2" />

        <div class="d-flex ga-2 mt-4">
          <v-btn variant="outlined" class="flex-grow-1" @click="dialog = false">Annuler</v-btn>
          <v-btn color="primary" class="flex-grow-1" :loading="saving" @click="save">Enregistrer</v-btn>
        </div>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.plans-admin {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 14px;
}

.pa-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-divider);
  background: var(--color-neutral-900);
  box-shadow: var(--shadow-sm);
}

.pa-card--off {
  opacity: 0.75;
}

.pa-card__head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
}

.pa-card__name {
  font-family: var(--font-heading);
  font-size: 17px;
}

.pa-card__price {
  font-size: 13px;
  color: var(--color-neutral-400);
}

.pa-card__quotas {
  flex: 1;
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: 13px;
}

.pa-card__quotas li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 0;
}

.pa-card__quotas svg {
  color: var(--color-primary);
}

.pa-subtitle {
  margin: 8px 0 8px;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-neutral-500);
}

.pa-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 10px 12px;
}
</style>
