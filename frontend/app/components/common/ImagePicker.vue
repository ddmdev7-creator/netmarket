<script setup lang="ts">
import { PhImage, PhLink, PhSpinner, PhUploadSimple, PhX } from '@phosphor-icons/vue'

// Bloc upload/grille/URL manuelle factorisé depuis ProductForm.vue — utilisé
// à la fois pour les images du produit (avec le bouton "Améliorer avec l'IA"
// injecté via le slot #extra-actions, propre au produit) et pour les photos
// de chaque variante (sans ce slot).
const images = defineModel<string[]>({ required: true })
withDefaults(defineProps<{ label?: string }>(), { label: 'Images' })

const toast = useToastStore()
const { apiFetch } = useApi()
const apiBase = useApiBase()

const uploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

function pickFiles() {
  fileInput.value?.click()
}

async function onFilesSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const files = input.files ? Array.from(input.files) : []
  input.value = '' // permet de re-sélectionner le même fichier plus tard
  if (files.length === 0) return

  uploading.value = true
  try {
    const formData = new FormData()
    for (const file of files) formData.append('files', file)
    const { keys } = await apiFetch<{ keys: string[] }>('/uploads/images', { method: 'POST', body: formData })
    images.value.push(...keys)
    toast.success(keys.length > 1 ? `${keys.length} images ajoutées.` : 'Image ajoutée.')
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'envoyer ces images."))
  } finally {
    uploading.value = false
  }
}

function removeImage(index: number) {
  images.value.splice(index, 1)
}

// Repli manuel (image déjà hébergée ailleurs) — l'upload direct ci-dessus reste le chemin normal.
const manualUrl = ref('')
function addManualUrl() {
  if (!manualUrl.value.trim()) return
  images.value.push(manualUrl.value.trim())
  manualUrl.value = ''
}
</script>

<template>
  <div>
    <label v-if="label" class="field-label">{{ label }}</label>

    <div v-if="images.length" class="image-grid mb-2">
      <div v-for="(url, i) in images" :key="url + i" class="image-grid__item">
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

    <slot name="extra-actions" />

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

@media (min-width: 640px) {
  .image-grid {
    grid-template-columns: repeat(5, 1fr);
  }
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
