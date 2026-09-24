<script setup lang="ts">
import { PhArrowLeft, PhArrowSquareOut, PhImage, PhTrash } from '@phosphor-icons/vue'
import type { CategoryRead, ProductRead, ProductVariantRead } from '~/types/api'
import type { ProductFormValues, VariantFormRow } from '~/components/vendor/ProductForm.vue'

definePageMeta({ middleware: 'vendor', layout: 'blank' })

const route = useRoute()
const router = useRouter()
const { apiFetch } = useApi()
const toast = useToastStore()
const productId = route.params.id as string

const { data: categories } = await useAsyncData('vendor-categories', () => apiFetch<CategoryRead[]>('/categories'), {
  default: () => [],
})
const { data: product, error: loadError } = await useAsyncData(`vendor-product-${productId}`, () =>
  apiFetch<ProductRead>(`/products/${productId}`),
)

function toVariantRow(v: ProductVariantRead): VariantFormRow {
  return {
    _key: v.id,
    id: v.id,
    sku: v.sku ?? '',
    skuManual: !!v.sku,
    price: v.price,
    stock: v.stock,
    images: v.images ? [...v.images] : [],
    attributes: v.attributes.map((a) => ({ name: a.name, value: a.value })),
  }
}

const form = ref<ProductFormValues>({
  category_id: null,
  name: '',
  description: '',
  price: null,
  stock: 0,
  images: [''],
  variants: [],
})
watch(
  product,
  (p) => {
    if (!p) return
    form.value = {
      category_id: p.category_id,
      name: p.name,
      description: p.description ?? '',
      price: p.price,
      stock: p.stock,
      images: p.images.length ? [...p.images] : [''],
      variants: p.variants.map(toVariantRow),
    }
  },
  { immediate: true },
)

const submitting = ref(false)

function normalizedAttributes(row: VariantFormRow) {
  return row.attributes
    .map((a) => ({ name: a.name.trim(), value: a.value.trim() }))
    .filter((a) => a.name && a.value)
}

async function saveVariants() {
  for (const row of form.value.variants) {
    try {
      if (row.id && row.deleted) {
        await apiFetch(`/products/${productId}/variants/${row.id}`, { method: 'DELETE' })
      } else if (!row.id && !row.deleted) {
        await apiFetch(`/products/${productId}/variants`, {
          method: 'POST',
          body: {
            sku: row.sku.trim() || null,
            price: row.price,
            stock: row.stock,
            images: row.images.length ? row.images : null,
            attributes: normalizedAttributes(row),
          },
        })
      } else if (row.id && !row.deleted) {
        await apiFetch(`/products/${productId}/variants/${row.id}`, {
          method: 'PATCH',
          body: {
            sku: row.sku.trim() || null,
            price: row.price,
            stock: row.stock,
            images: row.images.length ? row.images : null,
            attributes: normalizedAttributes(row),
          },
        })
      }
    } catch (e) {
      toast.error(apiErrorMessage(e, "Impossible d'enregistrer une variante."))
    }
  }
}

async function submit() {
  if (!form.value.category_id || form.value.name.trim().length < 1 || form.value.price === null || form.value.price < 0) {
    toast.error('Vérifie la catégorie, le nom et le prix.')
    return
  }
  const activeVariants = form.value.variants.filter((v) => !v.deleted)
  if (activeVariants.some((row) => normalizedAttributes(row).length === 0)) {
    toast.error('Chaque variante doit avoir au moins un attribut (ex: Couleur → Rouge).')
    return
  }

  submitting.value = true
  try {
    // Les variantes d'abord : si le produit avait déjà des variantes (ou en
    // gagne/perd dans ce même enregistrement), le PATCH du produit qui suit
    // doit voir l'état final pour décider s'il peut envoyer "stock" sans se
    // heurter au 409 de catalog/service.py::update_product (stock calculé
    // automatiquement dès qu'il existe au moins une variante).
    await saveVariants()

    const body: Record<string, unknown> = {
      category_id: form.value.category_id,
      name: form.value.name.trim(),
      description: form.value.description.trim() || null,
      price: form.value.price,
      images: form.value.images.map((url) => url.trim()).filter(Boolean),
    }
    if (activeVariants.length === 0) body.stock = form.value.stock ?? 0

    product.value = await apiFetch<ProductRead>(`/products/${productId}`, { method: 'PATCH', body })
    form.value.variants = product.value.variants.map(toVariantRow)

    toast.success('Produit mis à jour.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de sauvegarder ce produit.'))
  } finally {
    submitting.value = false
  }
}

const togglingStatus = ref(false)
async function toggleStatus(active: boolean) {
  if (!product.value) return
  togglingStatus.value = true
  try {
    product.value = await apiFetch<ProductRead>(`/products/${productId}`, {
      method: 'PATCH',
      body: { status: active ? 'active' : 'inactive' },
    })
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de changer le statut du produit.'))
  } finally {
    togglingStatus.value = false
  }
}

const apiBase = useApiBase()
const coverUrl = computed(() => {
  const image = product.value?.images[0]
  return image ? resolveImageUrl(image, apiBase) : null
})
const categoryName = computed(() => categories.value.find((c) => c.id === product.value?.category_id)?.name ?? null)

const confirmDelete = ref(false)
const deleting = ref(false)
async function deleteProduct() {
  deleting.value = true
  try {
    await apiFetch(`/products/${productId}`, { method: 'DELETE' })
    await router.replace('/vendeur/produits')
  } catch (e) {
    toast.error(
      apiErrorMessage(
        e,
        "Impossible de supprimer ce produit — il est probablement déjà référencé dans une commande. Tu peux le désactiver à la place.",
      ),
    )
    confirmDelete.value = false
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <div v-if="loadError" class="pa-6">
    <CommonEmptyState message="Produit introuvable." />
  </div>
  <div v-else class="dashboard-shell product-edit">
    <div class="d-flex align-center ga-2 mb-3">
      <v-btn icon variant="text" size="small" @click="router.back()">
        <PhArrowLeft :size="20" />
      </v-btn>
      <span class="text-muted" style="font-size: 13px">Mes produits</span>
    </div>

    <template v-if="product">
      <!-- Récapitulatif : ce qu'on modifie, son état en boutique, et les
           raccourcis (voir la fiche, activer/désactiver) au même endroit. -->
      <header class="edit-hero mb-5">
        <div class="edit-hero__thumb">
          <img v-if="coverUrl" :src="coverUrl" :alt="product.name" />
          <PhImage v-else :size="28" weight="light" />
        </div>
        <div class="edit-hero__main">
          <div class="edit-hero__eyebrow">
            <span v-if="categoryName">{{ categoryName }}</span>
            <span class="edit-hero__status" :class="{ 'edit-hero__status--off': product.status !== 'active' }">
              {{ product.status === 'active' ? 'En ligne' : 'Hors ligne' }}
            </span>
          </div>
          <h1 class="edit-hero__title">{{ product.name }}</h1>
          <div class="edit-hero__stats">
            <span><strong class="edit-hero__price">{{ formatGnf(product.price) }}</strong></span>
            <span>
              <strong>{{ product.stock }}</strong> en stock
            </span>
            <span v-if="product.variants.length">
              <strong>{{ product.variants.length }}</strong>
              variante{{ product.variants.length > 1 ? 's' : '' }}
            </span>
          </div>
        </div>
        <div class="edit-hero__actions">
          <label class="edit-hero__switch">
            <v-switch
              :model-value="product.status === 'active'"
              color="success"
              density="compact"
              hide-details
              inset
              :loading="togglingStatus"
              @update:model-value="toggleStatus(!!$event)"
            />
            <span>Visible en boutique</span>
          </label>
          <v-btn variant="outlined" size="small" :to="`/produits/${product.id}`" target="_blank">
            <PhArrowSquareOut :size="15" class="mr-1" />
            Voir la fiche
          </v-btn>
        </div>
      </header>

      <VendorProductForm v-model="form" :categories="categories" hide-context />

      <div class="danger-zone">
        <div>
          <div class="danger-zone__title">Supprimer ce produit</div>
          <div class="danger-zone__text">
            Impossible s'il figure déjà dans une commande — désactive-le plutôt.
          </div>
        </div>
        <v-btn variant="outlined" color="error" size="small" @click="confirmDelete = true">
          <PhTrash :size="15" class="mr-1" />
          Supprimer
        </v-btn>
      </div>

      <!-- Toujours à portée de pouce, quel que soit l'onglet ou la variante
           ouverte : plus besoin de redescendre en bas de page pour enregistrer. -->
      <div class="save-bar">
        <div class="save-bar__inner">
          <span class="save-bar__hint">Les modifications ne sont appliquées qu'après enregistrement.</span>
          <v-btn color="primary" size="large" min-width="220" :loading="submitting" @click="submit">
            Enregistrer
          </v-btn>
        </div>
      </div>
    </template>

    <v-dialog v-model="confirmDelete" max-width="340">
      <v-card class="pa-5">
        <div class="text-subtitle-1 mb-2">Supprimer ce produit ?</div>
        <p class="text-muted mb-4" style="font-size: 13px">Cette action est définitive.</p>
        <div class="d-flex ga-2">
          <v-btn variant="outlined" class="flex-grow-1" @click="confirmDelete = false">Annuler</v-btn>
          <v-btn color="error" class="flex-grow-1" :loading="deleting" @click="deleteProduct">Supprimer</v-btn>
        </div>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.product-edit {
  padding-bottom: 110px;
}

.edit-hero {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  padding: 16px;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-lg);
  background: var(--color-neutral-900);
  box-shadow: var(--shadow-sm);
}

.edit-hero__thumb {
  width: 84px;
  height: 84px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-divider);
  background: #fff;
  color: var(--color-neutral-500);
  overflow: hidden;
}

.edit-hero__thumb img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.edit-hero__main {
  flex: 1 1 220px;
  min-width: 0;
}

.edit-hero__eyebrow {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--color-neutral-400);
}

.edit-hero__status {
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 700;
  font-size: 11px;
  color: var(--color-success);
  background: color-mix(in srgb, var(--color-success) 14%, transparent);
}

.edit-hero__status--off {
  color: var(--color-neutral-400);
  background: var(--color-neutral-800);
}

.edit-hero__title {
  margin: 4px 0 6px;
  font-family: var(--font-heading);
  font-size: 20px;
  font-weight: 800;
  line-height: 1.25;
  color: var(--color-neutral-100);
}

.edit-hero__stats {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
  font-size: 13px;
  color: var(--color-neutral-400);
}

.edit-hero__stats strong {
  color: var(--color-neutral-100);
}

.edit-hero__stats .edit-hero__price {
  color: var(--color-accent);
}

.edit-hero__actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}

.edit-hero__switch {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

@media (max-width: 600px) {
  .edit-hero__actions {
    width: 100%;
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
  }
}

.danger-zone {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  max-width: 820px;
  margin: 40px auto 0;
  padding: 14px 16px;
  border: 1px solid color-mix(in srgb, var(--color-error) 35%, transparent);
  border-radius: var(--radius-lg);
}

.danger-zone__title {
  font-weight: 700;
  font-size: 13.5px;
}

.danger-zone__text {
  font-size: 12px;
  color: var(--color-neutral-400);
}

.save-bar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 5;
  padding: 12px 16px calc(12px + env(safe-area-inset-bottom, 0px));
  background: var(--color-neutral-900);
  border-top: 1px solid var(--color-divider);
  box-shadow: var(--shadow-dock);
}

.save-bar__inner {
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 16px;
}

.save-bar__hint {
  font-size: 12.5px;
  color: var(--color-neutral-400);
}

@media (max-width: 600px) {
  .save-bar__hint {
    display: none;
  }

  .save-bar__inner .v-btn {
    flex: 1;
  }
}
</style>
