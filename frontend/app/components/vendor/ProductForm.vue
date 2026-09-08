<script setup lang="ts">
import { PhImage, PhLink, PhSparkle, PhSpinner, PhUploadSimple, PhX } from '@phosphor-icons/vue'
import type { CategoryRead, VendorSubscriptionRead } from '~/types/api'

export interface ProductFormValues {
  category_id: string | null
  name: string
  description: string
  price: number | null
  stock: number | null
  images: string[]
}

const model = defineModel<ProductFormValues>({ required: true })
defineProps<{ categories: CategoryRead[] }>()

const toast = useToastStore()
const { apiFetch } = useApi()
const apiBase = useApiBase()

// Pas d'await ici : ProductForm est un composant enfant, pas une page — on
// laisse le statut premium arriver de façon réactive plutôt que de bloquer
// le rendu du formulaire dessus.
const { data: subscription } = useAsyncData(
  'product-form-subscription',
  () => apiFetch<VendorSubscriptionRead | null>('/subscriptions/me'),
  { default: () => null },
)
const isPremium = computed(() => subscription.value?.status === 'active')

const uploading = ref(false)
const enhancing = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const enhanceFileInput = ref<HTMLInputElement | null>(null)

function pickFiles() {
  fileInput.value?.click()
}

function pickEnhanceFiles() {
  if (!isPremium.value) {
    navigateTo('/vendeur/abonnement')
    return
  }
  enhanceFileInput.value?.click()
}

async function uploadFiles(files: File[], endpoint: string, setBusy: (busy: boolean) => void) {
  setBusy(true)
  try {
    const formData = new FormData()
    for (const file of files) formData.append('files', file)
    const { keys } = await apiFetch<{ keys: string[] }>(endpoint, { method: 'POST', body: formData })
    model.value.images.push(...keys)
    toast.success(keys.length > 1 ? `${keys.length} images ajoutées.` : 'Image ajoutée.')
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'envoyer ces images."))
  } finally {
    setBusy(false)
  }
}

async function onFilesSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const files = input.files ? Array.from(input.files) : []
  input.value = '' // permet de re-sélectionner le même fichier plus tard
  if (files.length === 0) return
  await uploadFiles(files, '/uploads/images', (busy) => (uploading.value = busy))
}

async function onEnhanceFilesSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const files = input.files ? Array.from(input.files) : []
  input.value = ''
  if (files.length === 0) return
  await uploadFiles(files, '/uploads/images/enhance', (busy) => (enhancing.value = busy))
}

function removeImage(index: number) {
  model.value.images.splice(index, 1)
}

// Repli manuel (image déjà hébergée ailleurs) — l'upload direct ci-dessus
// reste le chemin normal.
const manualUrl = ref('')
function addManualUrl() {
  if (!manualUrl.value.trim()) return
  model.value.images.push(manualUrl.value.trim())
  manualUrl.value = ''
}
</script>

<template>
  <div>
    <label class="field-label">Catégorie</label>
    <v-select
      v-model="model.category_id"
      :items="categories"
      item-title="name"
      item-value="id"
      placeholder="Choisir une catégorie"
      class="mb-2"
    />

    <label class="field-label">Nom du produit</label>
    <v-text-field v-model="model.name" placeholder="Ex: Riz parfumé 25kg" class="mb-2" />

    <label class="field-label">Description (optionnel)</label>
    <v-textarea v-model="model.description" rows="3" class="mb-2" />

    <div class="d-flex ga-2">
      <div class="flex-grow-1">
        <label class="field-label">Prix (GNF)</label>
        <v-text-field v-model.number="model.price" type="number" min="0" class="mb-2" />
      </div>
      <div class="flex-grow-1">
        <label class="field-label">Stock</label>
        <v-text-field v-model.number="model.stock" type="number" min="0" class="mb-2" />
      </div>
    </div>

    <label class="field-label">Images — au moins 3 recommandées, la fiche produit affiche un carrousel</label>

    <div v-if="model.images.length" class="image-grid mb-2">
      <div v-for="(url, i) in model.images" :key="url + i" class="image-grid__item">
        <img :src="resolveImageUrl(url, apiBase)" :alt="`Image ${i + 1}`" />
        <button type="button" class="image-grid__remove" @click="removeImage(i)">
          <PhX :size="12" weight="bold" />
        </button>
      </div>
    </div>
    <div v-else class="image-empty mb-2">
      <PhImage :size="24" weight="light" color="var(--color-neutral-500)" />
      <span class="text-muted" style="font-size: 12px">Aucune image pour l'instant</span>
    </div>

    <input
      ref="fileInput"
      type="file"
      accept="image/jpeg,image/png,image/webp"
      multiple
      class="d-none"
      @change="onFilesSelected"
    />
    <v-btn variant="outlined" size="small" block class="mb-2" :loading="uploading" @click="pickFiles">
      <PhSpinner v-if="uploading" :size="14" class="mr-1" />
      <PhUploadSimple v-else :size="14" class="mr-1" />
      Choisir des images
    </v-btn>

    <input
      ref="enhanceFileInput"
      type="file"
      accept="image/jpeg,image/png,image/webp"
      multiple
      class="d-none"
      @change="onEnhanceFilesSelected"
    />
    <v-btn variant="outlined" size="small" block class="mb-2" :loading="enhancing" @click="pickEnhanceFiles">
      <PhSpinner v-if="enhancing" :size="14" class="mr-1" />
      <PhSparkle v-else :size="14" class="mr-1" />
      Améliorer avec l'IA {{ isPremium ? '' : '(Premium)' }}
    </v-btn>

    <details class="manual-url mb-2">
      <summary class="text-muted" style="font-size: 11.5px; cursor: pointer">
        <PhLink :size="11" class="mr-1" style="vertical-align: -1px" />
        Ajouter par URL (image déjà hébergée ailleurs)
      </summary>
      <div class="d-flex ga-2 mt-2">
        <v-text-field v-model="manualUrl" placeholder="https://…" hide-details density="compact" class="flex-grow-1" />
        <v-btn variant="outlined" size="small" @click="addManualUrl">Ajouter</v-btn>
      </div>
    </details>
  </div>
</template>

<style scoped>
.image-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.image-grid__item {
  position: relative;
  aspect-ratio: 1;
  border-radius: var(--radius-sm);
  overflow: hidden;
  background: var(--color-neutral-800);
  border: 1px solid var(--color-divider);
}

.image-grid__item img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.image-grid__remove {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.image-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 20px;
  border: 1px dashed var(--color-divider-strong);
  border-radius: var(--radius-md);
}

.manual-url summary::-webkit-details-marker {
  display: none;
}
</style>
