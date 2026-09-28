<script setup lang="ts">
import { PhArrowLeft, PhCheck, PhCheckCircle, PhEye, PhWarningCircle } from '@phosphor-icons/vue'
import type { CategoryRead, ProductRead, VendorRead } from '~/types/api'
import type { ProductFormValues, VariantFormRow } from '~/components/vendor/ProductForm.vue'

definePageMeta({ middleware: 'vendor', layout: 'blank' })

const router = useRouter()
const { apiFetch } = useApi()
const toast = useToastStore()

const { data: categories } = await useAsyncData('vendor-categories', () => apiFetch<CategoryRead[]>('/categories'), {
  default: () => [],
})
const { data: vendor } = await useAsyncData('vendor-me-new-product', () => apiFetch<VendorRead>('/vendors/me'))

const form = ref<ProductFormValues>({
  category_id: null,
  name: '',
  description: '',
  price: null,
  stock: 0,
  images: [''],
  variants: [],
})
const submitting = ref(false)

function normalizedAttributes(row: VariantFormRow) {
  return row.attributes
    .map((a) => ({ name: a.name.trim(), value: a.value.trim() }))
    .filter((a) => a.name && a.value)
}

// --- Assistant pas à pas ------------------------------------------------------

type Step = 1 | 2 | 3 | 4
const STEPS: { n: Step; label: string }[] = [
  { n: 1, label: 'Infos' },
  { n: 2, label: 'Photos' },
  { n: 3, label: 'Options' },
  { n: 4, label: 'Aperçu' },
]
const step = ref<Step>(1)
const TAB_BY_STEP = { 1: 'info', 2: 'images', 3: 'variants' } as const
const formTab = computed({
  get: () => TAB_BY_STEP[step.value as 1 | 2 | 3] ?? 'info',
  set: () => {},
})

const photos = computed(() => form.value.images.map((u) => u.trim()).filter(Boolean))
const activeVariants = computed(() => form.value.variants.filter((v) => !v.deleted))

function infoError(): string | null {
  if (!form.value.category_id) return 'Choisis une catégorie.'
  if (!form.value.name.trim()) return 'Le nom du produit est requis.'
  if (form.value.price === null || form.value.price < 0) return 'Indique un prix valide.'
  return null
}

function variantsError(): string | null {
  return activeVariants.value.some((row) => normalizedAttributes(row).length === 0)
    ? 'Chaque variante doit avoir au moins un attribut (ex: Couleur → Rouge).'
    : null
}

function goTo(target: Step) {
  if (target > step.value) {
    const checks: Record<number, () => string | null> = { 1: infoError, 3: variantsError }
    for (let s = step.value; s < target; s++) {
      const error = checks[s]?.()
      if (error) {
        toast.error(error)
        step.value = s as Step
        return
      }
    }
  }
  step.value = target
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

// --- Aperçu : la carte telle que l'acheteur la verra --------------------------

const previewProduct = computed<ProductRead>(() => ({
  id: 'apercu',
  vendor_id: vendor.value?.id ?? '',
  vendor_shop_name: vendor.value?.shop_name ?? 'Ma boutique',
  category_id: form.value.category_id ?? '',
  name: form.value.name.trim() || 'Nom du produit',
  description: form.value.description,
  price: form.value.price ?? 0,
  stock: activeVariants.value.length
    ? activeVariants.value.reduce((n, v) => n + (v.stock ?? 0), 0)
    : (form.value.stock ?? 0),
  images: photos.value,
  status: 'active',
  average_rating: null,
  review_count: 0,
  estimated_delivery_min: null,
  estimated_delivery_max: null,
  variants: activeVariants.value.map((v) => ({
    id: v._key,
    product_id: 'apercu',
    sku: v.sku || null,
    price: v.price,
    stock: v.stock,
    images: v.images.length ? v.images : null,
    attributes: normalizedAttributes(v),
  })),
}))

// Qualité de la fiche : ce qui fait vendre, vérifié avant publication.
const checklist = computed(() => {
  const descriptionText = form.value.description.replace(/<[^>]+>/g, '').trim()
  return [
    { ok: !!form.value.category_id && !!form.value.name.trim() && form.value.price !== null, label: 'Nom, catégorie et prix renseignés' },
    { ok: photos.value.length >= 1, label: 'Au moins une photo', hint: 'Sans photo, un produit se vend très mal.' },
    { ok: photos.value.length >= 3, label: '3 photos ou plus', hint: 'Montrez le produit sous plusieurs angles.' },
    { ok: descriptionText.length >= 80, label: 'Description détaillée (80 caractères ou plus)', hint: 'Matière, dimensions, état, contenu du colis…' },
    { ok: previewProduct.value.stock > 0, label: 'Du stock disponible', hint: 'Un produit à 0 en stock ne peut pas être acheté.' },
  ]
})
const quality = computed(() => Math.round((checklist.value.filter((c) => c.ok).length / checklist.value.length) * 100))

async function submit() {
  if (!form.value.category_id) {
    toast.error('Choisis une catégorie.')
    return
  }
  if (form.value.name.trim().length < 1) {
    toast.error('Le nom du produit est requis.')
    return
  }
  if (form.value.price === null || form.value.price < 0) {
    toast.error('Indique un prix valide.')
    return
  }
  const variants = form.value.variants.filter((v) => !v.deleted)
  if (variants.some((row) => normalizedAttributes(row).length === 0)) {
    toast.error('Chaque variante doit avoir au moins un attribut (ex: Couleur → Rouge).')
    return
  }

  submitting.value = true
  try {
    const product = await apiFetch<ProductRead>('/products', {
      method: 'POST',
      body: {
        category_id: form.value.category_id,
        name: form.value.name.trim(),
        description: form.value.description.trim() || undefined,
        price: form.value.price,
        stock: form.value.stock ?? 0,
        images: form.value.images.map((url) => url.trim()).filter(Boolean),
      },
    })

    for (const row of variants) {
      try {
        await apiFetch(`/products/${product.id}/variants`, {
          method: 'POST',
          body: {
            sku: row.sku.trim() || null,
            price: row.price,
            stock: row.stock,
            images: row.images.length ? row.images : null,
            attributes: normalizedAttributes(row),
          },
        })
      } catch (e) {
        toast.error(apiErrorMessage(e, "Produit créé, mais une variante n'a pas pu être enregistrée."))
      }
    }

    toast.success('Produit publié.')
    await router.replace(`/vendeur/produits/${product.id}`)
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de créer ce produit.'))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="dashboard-shell wizard">
    <div class="d-flex align-center ga-2 mb-3">
      <v-btn icon variant="text" aria-label="Retour" @click="step > 1 ? goTo((step - 1) as Step) : router.back()">
        <PhArrowLeft :size="20" />
      </v-btn>
      <h1 class="text-h6 mb-0">Nouveau produit</h1>
    </div>

    <nav class="wsteps" aria-label="Étapes">
      <template v-for="(s, i) in STEPS" :key="s.n">
        <button
          type="button"
          class="wsteps__step"
          :class="{ 'is-done': step > s.n, 'is-current': step === s.n }"
          :aria-current="step === s.n ? 'step' : undefined"
          @click="goTo(s.n)"
        >
          <span class="wsteps__dot">
            <PhCheck v-if="step > s.n" :size="13" weight="bold" />
            <template v-else>{{ s.n }}</template>
          </span>
          <span class="wsteps__label">{{ s.label }}</span>
        </button>
        <span v-if="i < STEPS.length - 1" class="wsteps__bar" :class="{ 'is-done': step > s.n }" />
      </template>
    </nav>

    <div class="wizard__layout">
      <div class="wizard__main">
        <p v-if="step === 1" class="wizard__intro">Commencez par l'essentiel : ce que vous vendez et à quel prix.</p>
        <p v-else-if="step === 2" class="wizard__intro">
          De bonnes photos font vendre : fond clair, produit entier, plusieurs angles.
        </p>
        <p v-else-if="step === 3" class="wizard__intro">
          Facultatif : couleurs, tailles, capacités… chacune avec son stock et, si besoin, son prix et ses photos.
        </p>

        <VendorProductForm v-show="step < 4" v-model="form" v-model:tab="formTab" :categories="categories" wizard />

        <section v-if="step === 4" class="review">
          <div class="review__quality">
            <div class="review__quality-head">
              <span>Qualité de la fiche</span>
              <strong :class="{ 'is-good': quality >= 80 }">{{ quality }} %</strong>
            </div>
            <div class="review__meter"><span :style="{ width: `${quality}%` }" :class="{ 'is-good': quality >= 80 }" /></div>
          </div>
          <ul class="review__list">
            <li v-for="item in checklist" :key="item.label" :class="{ 'is-ok': item.ok }">
              <component :is="item.ok ? PhCheckCircle : PhWarningCircle" :size="18" weight="fill" />
              <span>
                {{ item.label }}
                <small v-if="!item.ok && item.hint">{{ item.hint }}</small>
              </span>
            </li>
          </ul>
          <div class="review__preview-mobile">
            <div class="preview__label"><PhEye :size="14" /> Aperçu pour l'acheteur</div>
            <div class="preview__card"><ProductCard :product="previewProduct" /></div>
          </div>
        </section>

        <div class="wizard__actions">
          <v-btn v-if="step > 1" variant="outlined" @click="goTo((step - 1) as Step)">Retour</v-btn>
          <v-spacer />
          <v-btn v-if="step < 4" color="primary" size="large" @click="goTo((step + 1) as Step)">
            {{ step === 3 ? 'Voir l’aperçu' : 'Continuer' }}
          </v-btn>
          <v-btn v-else color="primary" size="large" min-width="200" :loading="submitting" @click="submit">
            Publier le produit
          </v-btn>
        </div>
      </div>

      <aside class="wizard__aside">
        <div class="preview__label"><PhEye :size="14" /> Aperçu en direct</div>
        <div class="preview__card"><ProductCard :product="previewProduct" /></div>
        <p class="preview__hint">La carte se met à jour pendant que vous remplissez la fiche.</p>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.wsteps {
  display: flex;
  align-items: center;
  gap: 6px;
  max-width: 560px;
  margin-bottom: 18px;
}

.wsteps__step {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0;
  border: 0;
  background: none;
  color: var(--color-neutral-500);
  cursor: pointer;
  flex-shrink: 0;
}

.wsteps__dot {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: 2px solid var(--color-divider-strong);
  background: var(--color-neutral-900);
  font-size: 12.5px;
  font-weight: 800;
}

.wsteps__label {
  font-size: 12.5px;
  font-weight: 700;
}

.wsteps__step.is-current {
  color: var(--color-primary-300);
}

.wsteps__step.is-current .wsteps__dot {
  border-color: var(--color-primary);
  background: var(--color-primary);
  color: #fff;
  box-shadow: 0 0 0 4px var(--color-primary-100);
}

.wsteps__step.is-done {
  color: var(--color-neutral-300);
}

.wsteps__step.is-done .wsteps__dot {
  border-color: var(--color-success);
  background: var(--color-success);
  color: #fff;
}

.wsteps__bar {
  flex: 1;
  height: 2px;
  min-width: 10px;
  background: var(--color-divider-strong);
}

.wsteps__bar.is-done {
  background: var(--color-success);
}

@media (max-width: 420px) {
  .wsteps__step:not(.is-current) .wsteps__label {
    display: none;
  }
}

.wizard__intro {
  margin: 0 0 14px;
  font-size: 13.5px;
  color: var(--color-neutral-400);
}

.wizard__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--color-divider);
}

.wizard__aside {
  display: none;
}

.preview__label {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  font-size: 11.5px;
  font-weight: 800;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: var(--color-neutral-500);
}

/* L'aperçu n'est pas cliquable : c'est une image de la future carte. */
.preview__card {
  width: 220px;
  pointer-events: none;
}

.preview__hint {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--color-neutral-500);
}

.review__quality {
  padding: 14px;
  border-radius: var(--radius-md);
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider);
}

.review__quality-head {
  display: flex;
  justify-content: space-between;
  font-size: 13.5px;
  font-weight: 700;
  margin-bottom: 8px;
}

.review__quality-head strong {
  color: var(--color-accent);
}

.review__quality-head strong.is-good {
  color: var(--color-success);
}

.review__meter {
  height: 8px;
  border-radius: 8px;
  background: var(--color-neutral-700);
  overflow: hidden;
}

.review__meter span {
  display: block;
  height: 100%;
  border-radius: 8px;
  background: var(--color-accent);
  transition: width 0.4s ease;
}

.review__meter span.is-good {
  background: var(--color-success);
}

.review__list {
  list-style: none;
  margin: 14px 0 18px;
  padding: 0;
}

.review__list li {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 0;
  font-size: 13.5px;
  color: var(--color-neutral-300);
}

.review__list li > svg {
  flex-shrink: 0;
  margin-top: 1px;
  color: var(--color-accent);
}

.review__list li.is-ok > svg {
  color: var(--color-success);
}

.review__list small {
  display: block;
  font-size: 12px;
  color: var(--color-neutral-400);
}

@media (min-width: 960px) {
  .wizard__layout {
    display: grid;
    grid-template-columns: 1fr 240px;
    gap: 32px;
    align-items: start;
  }

  .wizard__aside {
    display: block;
    position: sticky;
    top: 16px;
  }

  .review__preview-mobile {
    display: none;
  }
}
</style>
