<script setup lang="ts">
import { PhArrowLeft } from '@phosphor-icons/vue'
import type { CategoryRead, ProductRead } from '~/types/api'
import type { ProductFormValues, VariantFormRow } from '~/components/vendor/ProductForm.vue'

definePageMeta({ middleware: 'vendor', layout: 'blank' })

const router = useRouter()
const { apiFetch } = useApi()
const toast = useToastStore()

const { data: categories } = await useAsyncData('vendor-categories', () => apiFetch<CategoryRead[]>('/categories'), {
  default: () => [],
})

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
  <div class="dashboard-shell">
    <div class="d-flex align-center ga-2 mb-4">
      <v-btn icon variant="text" @click="router.back()">
        <PhArrowLeft :size="20" />
      </v-btn>
      <h1 class="text-h6 mb-0">Nouveau produit</h1>
    </div>

    <VendorProductForm v-model="form" :categories="categories" />

    <v-btn color="primary" size="large" class="mt-4 submit-btn" :loading="submitting" @click="submit">
      Publier le produit
    </v-btn>
  </div>
</template>

<style scoped>
.submit-btn {
  width: 100%;
  max-width: 320px;
}
</style>
