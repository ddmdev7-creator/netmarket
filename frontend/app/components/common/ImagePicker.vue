<script setup lang="ts">
import { PhImage, PhLink, PhSpinner, PhStar, PhUploadSimple, PhX } from '@phosphor-icons/vue'

// Bloc upload/grille/URL manuelle factorisé depuis ProductForm.vue — utilisé
// à la fois pour les images du produit (avec le bouton "Améliorer avec l'IA"
// injecté via le slot #extra-actions, propre au produit) et pour les photos
// de chaque variante (sans ce slot).
const images = defineModel<string[]>({ required: true })
// compact : bande de vignettes + tuile "Ajouter" (formulaire de variante),
// sans le gros bouton pleine largeur ni l'ajout par URL.
withDefaults(defineProps<{ label?: string; compact?: boolean }>(), { label: 'Images', compact: false })

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

// La 1ère image du tableau est la convention déjà utilisée partout où une
// seule photo est affichée (carte produit, miniature panier, liste vendeur
// — toutes lisent images[0]) : "définir comme couverture" ne fait que la
// faire passer en tête, aucun champ dédié côté API n'est nécessaire.
function setCover(index: number) {
  if (index <= 0 || index >= images.value.length) return
  const [cover] = images.value.splice(index, 1)
  images.value.unshift(cover!)
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

    <div v-if="compact" class="image-strip">
      <div v-for="(url, i) in images" :key="url + i" class="image-strip__item">
        <img :src="resolveImageUrl(url, apiBase)" :alt="`Image ${i + 1}`" />
        <span v-if="i === 0 && images.length > 1" class="image-strip__cover" title="Photo principale">
          <PhStar :size="9" weight="fill" />
        </span>
        <button
          v-else-if="i > 0"
          type="button"
          class="image-strip__cover image-strip__cover--btn"
          aria-label="Définir comme photo principale"
          title="Définir comme photo principale"
          @click="setCover(i)"
        >
          <PhStar :size="9" />
        </button>
        <button type="button" class="image-grid__remove" aria-label="Retirer cette image" @click="removeImage(i)">
          <PhX :size="11" weight="bold" />
        </button>
      </div>
      <button type="button" class="image-strip__add" :disabled="uploading" @click="pickFiles">
        <PhSpinner v-if="uploading" :size="20" class="image-strip__spin" />
        <PhUploadSimple v-else :size="20" />
        <span>{{ uploading ? 'Envoi…' : images.length ? 'Ajouter' : 'Ajouter des photos' }}</span>
      </button>
    </div>

    <div v-else-if="images.length" class="image-grid mb-2">
      <div v-for="(url, i) in images" :key="url + i" class="image-grid__item">
        <img :src="resolveImageUrl(url, apiBase)" :alt="`Image ${i + 1}`" />
        <span v-if="i === 0" class="image-grid__cover-badge">
          <PhStar :size="10" weight="fill" />
          Couverture
        </span>
        <button
          v-else
          type="button"
          class="image-grid__cover-btn"
          aria-label="Définir comme photo de couverture"
          title="Définir comme photo de couverture"
          @click="setCover(i)"
        >
          <PhStar :size="12" />
        </button>
        <button type="button" class="image-grid__remove" aria-label="Retirer cette image" @click="removeImage(i)">
          <PhX :size="12" weight="bold" />
        </button>
      </div>
    </div>
    <div v-else class="image-empty mb-2">
      <PhImage :size="24" weight="light" color="var(--color-neutral-500)" />
      <span class="text-muted" style="font-size: 12px">Aucune image pour l'instant</span>
    </div>
    <template v-if="!compact">
      <p v-if="images.length > 1" class="text-muted mb-2 text-fine">
        La photo "Couverture" (première de la liste) est celle affichée dans le catalogue et les cartes produit —
        cliquez sur <PhStar :size="10" weight="bold" style="vertical-align: -1px" /> sur une autre photo pour la
        remplacer.
      </p>

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
    </template>
    <input
      ref="fileInput"
      type="file"
      accept="image/jpeg,image/png,image/webp"
      multiple
      class="d-none"
      @change="onFilesSelected"
    />
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

.image-grid__cover-badge {
  position: absolute;
  top: 4px;
  left: 4px;
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 2px 6px;
  border-radius: 999px;
  background: var(--color-primary);
  color: #fff;
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.image-grid__cover-btn {
  position: absolute;
  top: 4px;
  left: 4px;
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
  opacity: 0.85;
  transition: opacity 0.15s ease, color 0.15s ease;
}

.image-grid__cover-btn:hover {
  opacity: 1;
  color: var(--color-accent);
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

.image-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.image-strip__item,
.image-strip__add {
  position: relative;
  width: 84px;
  height: 84px;
  border-radius: var(--radius-md);
  overflow: hidden;
}

.image-strip__item {
  background: #fff;
  border: 1px solid var(--color-divider);
}

.image-strip__item img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.image-strip__cover {
  position: absolute;
  top: 4px;
  left: 4px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-primary);
  color: #fff;
  border: none;
}

.image-strip__cover--btn {
  background: rgba(0, 0, 0, 0.55);
  cursor: pointer;
}

.image-strip__add {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 6px;
  border: 1.5px dashed var(--color-primary-300);
  background: color-mix(in srgb, var(--color-primary) 6%, transparent);
  color: var(--color-primary);
  font-size: 11.5px;
  font-weight: 700;
  line-height: 1.2;
  text-align: center;
  cursor: pointer;
  transition: background 0.15s ease;
}

.image-strip__add:hover {
  background: color-mix(in srgb, var(--color-primary) 12%, transparent);
}

.image-strip__add:only-child {
  width: 100%;
  height: 96px;
  flex-direction: row;
  gap: 8px;
  font-size: 13px;
}

.image-strip__spin {
  animation: image-strip-spin 0.9s linear infinite;
}

@keyframes image-strip-spin {
  to {
    transform: rotate(360deg);
  }
}

.manual-url summary::-webkit-details-marker {
  display: none;
}
</style>
