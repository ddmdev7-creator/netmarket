<script setup lang="ts">
import { PhCrown, PhImage, PhLink, PhSparkle, PhStar, PhUploadSimple, PhX } from '@phosphor-icons/vue'

// Sélecteur de photos du formulaire produit : photos du produit (mode
// complet) et de chaque variante (compact). Avec `ai`, l'amélioration IA
// (fond blanc, recadrage, netteté — app/uploads/enhance.py, Premium) se
// branche sur le même geste d'ajout : un interrupteur partagé par tous les
// sélecteurs de la page, plus un bouton « Améliorer » sur une photo déjà là.
const images = defineModel<string[]>({ required: true })
// compact : bande de vignettes + tuile "Ajouter" (formulaire de variante),
// sans la zone de dépôt ni l'ajout par URL.
const props = withDefaults(defineProps<{ label?: string; compact?: boolean; ai?: boolean }>(), {
  label: 'Images',
  compact: false,
  ai: false,
})

const toast = useToastStore()
const { apiFetch } = useApi()
const apiBase = useApiBase()
const { isPremium } = useVendorPremium()

const MAX_SIZE = 8 * 1024 * 1024
const ACCEPTED = ['image/jpeg', 'image/png', 'image/webp']
const STORED_KEY = /^[0-9a-f-]{36}\.jpg$/

// --- Interrupteur IA : un seul état pour toute la page, mémorisé ---
const aiWanted = useState('nm-ai-enhance', () => {
  if (import.meta.server) return false
  try {
    return localStorage.getItem('nm-ai-enhance') === '1'
  } catch {
    return false
  }
})
const aiOn = computed(() => props.ai && isPremium.value && aiWanted.value)
const premiumDialog = ref(false)

function toggleAi() {
  if (!isPremium.value) {
    premiumDialog.value = true
    return
  }
  aiWanted.value = !aiWanted.value
  try {
    localStorage.setItem('nm-ai-enhance', aiWanted.value ? '1' : '0')
  } catch {
    /* stockage indisponible : l'état reste valable pour la session */
  }
}

// Photos passées par l'IA pendant cette session (badge + pas de 2e passage).
const enhanced = useState('nm-ai-enhanced-keys', () => new Set<string>())

// --- Envois en cours : une tuile par fichier, avec son aperçu local ---
interface PendingTile {
  id: string
  preview: string
  ai: boolean
}
const pending = ref<PendingTile[]>([])

function validate(files: File[]): File[] {
  return files.filter((file) => {
    if (!ACCEPTED.includes(file.type)) {
      toast.error(`« ${file.name} » : format non supporté (JPEG, PNG ou WebP).`)
      return false
    }
    if (file.size > MAX_SIZE) {
      toast.error(`« ${file.name} » dépasse 8 Mo.`)
      return false
    }
    return true
  })
}

async function uploadOne(file: File, useAi: boolean): Promise<string | null> {
  const tile: PendingTile = { id: crypto.randomUUID(), preview: URL.createObjectURL(file), ai: useAi }
  pending.value.push(tile)
  try {
    const formData = new FormData()
    formData.append('files', file)
    const { keys } = await apiFetch<{ keys: string[] }>(useAi ? '/uploads/images/enhance' : '/uploads/images', {
      method: 'POST',
      body: formData,
    })
    const key = keys[0] ?? null
    if (key && useAi) enhanced.value.add(key)
    return key
  } catch (e) {
    toast.error(apiErrorMessage(e, `Impossible d'envoyer « ${file.name} ».`))
    return null
  } finally {
    pending.value = pending.value.filter((p) => p.id !== tile.id)
    URL.revokeObjectURL(tile.preview)
  }
}

// Un fichier par requête, deux à la fois : chaque tuile se remplit dès que
// sa photo est prête au lieu d'attendre tout le lot (l'IA prend quelques
// secondes par photo). L'ordre de sélection est conservé.
async function addFiles(raw: File[]) {
  const files = validate(raw)
  if (!files.length) return
  const useAi = aiOn.value
  const results: (string | null)[] = new Array(files.length).fill(null)
  let next = 0
  async function worker() {
    while (next < files.length) {
      const index = next++
      results[index] = await uploadOne(files[index]!, useAi)
    }
  }
  await Promise.all([worker(), worker()])
  const keys = results.filter((k): k is string => !!k)
  if (!keys.length) return
  images.value.push(...keys)
  const noun = keys.length > 1 ? `${keys.length} photos ajoutées` : 'Photo ajoutée'
  toast.success(useAi ? `${noun} et améliorées par l'IA.` : `${noun}.`)
}

const fileInput = ref<HTMLInputElement | null>(null)
function pickFiles() {
  fileInput.value?.click()
}
function onFilesSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const files = input.files ? Array.from(input.files) : []
  input.value = '' // permet de re-sélectionner le même fichier plus tard
  addFiles(files)
}

// --- Glisser-déposer ---
const dragging = ref(false)
let dragDepth = 0
function onDragEnter() {
  dragDepth++
  dragging.value = true
}
function onDragLeave() {
  dragDepth = Math.max(0, dragDepth - 1)
  if (!dragDepth) dragging.value = false
}
function onDrop(event: DragEvent) {
  dragDepth = 0
  dragging.value = false
  addFiles(Array.from(event.dataTransfer?.files ?? []))
}

// --- Améliorer une photo déjà ajoutée ---
const enhancing = ref(new Set<string>())
function canEnhance(url: string): boolean {
  return props.ai && STORED_KEY.test(url) && !enhanced.value.has(url)
}

async function enhanceExisting(index: number) {
  const key = images.value[index]
  if (!key) return
  if (!isPremium.value) {
    premiumDialog.value = true
    return
  }
  enhancing.value.add(key)
  try {
    const { keys } = await apiFetch<{ keys: string[] }>(`/uploads/images/${key}/enhance`, { method: 'POST' })
    const fresh = keys[0]
    if (!fresh) return
    enhanced.value.add(fresh)
    // La liste a pu bouger pendant le traitement : on remplace par la clé.
    const at = images.value.indexOf(key)
    if (at !== -1) images.value.splice(at, 1, fresh)
    toast.success("Photo améliorée par l'IA.")
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'améliorer cette photo."))
  } finally {
    enhancing.value.delete(key)
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

// Repli manuel (image déjà hébergée ailleurs) — l'upload direct reste le chemin normal.
const manualUrl = ref('')
function addManualUrl() {
  if (!manualUrl.value.trim()) return
  images.value.push(manualUrl.value.trim())
  manualUrl.value = ''
}
</script>

<template>
  <div
    class="ip"
    :class="{ 'ip--compact': compact, 'ip--dragging': dragging }"
    @dragenter.prevent="onDragEnter"
    @dragover.prevent
    @dragleave.prevent="onDragLeave"
    @drop.prevent="onDrop"
  >
    <label v-if="label" class="field-label">{{ label }}</label>

    <!-- Interrupteur IA -->
    <button
      v-if="ai"
      type="button"
      class="ai-toggle"
      :class="{ 'ai-toggle--on': aiOn, 'ai-toggle--compact': compact }"
      :aria-pressed="aiOn"
      @click="toggleAi"
    >
      <span class="ai-toggle__icon"><PhSparkle :size="compact ? 14 : 18" weight="fill" /></span>
      <span class="ai-toggle__text">
        <span class="ai-toggle__title">
          Amélioration IA
          <span v-if="!isPremium" class="ai-toggle__premium"><PhCrown :size="10" weight="fill" /> Premium</span>
        </span>
        <span v-if="!compact" class="ai-toggle__sub">
          {{ aiOn ? 'Activée — fond blanc, recadrage et netteté sur chaque photo ajoutée' : 'Fond blanc, recadrage et netteté automatiques' }}
        </span>
      </span>
      <span class="ai-toggle__switch" aria-hidden="true"><span /></span>
    </button>

    <!-- Galerie -->
    <div
      v-if="images.length || pending.length || compact"
      class="ip-grid"
      :class="{ 'ip-grid--strip': compact }"
    >
      <div v-for="(url, i) in images" :key="url + i" class="ip-tile" :class="{ 'ip-tile--working': enhancing.has(url) }">
        <img :src="resolveImageUrl(url, apiBase, 320)" :alt="`Photo ${i + 1}`" />

        <span v-if="i === 0 && (images.length > 1 || !compact)" class="ip-tile__cover" title="Photo principale">
          <PhStar :size="9" weight="fill" />
          <span v-if="!compact">Couverture</span>
        </span>
        <button
          v-else-if="i > 0"
          type="button"
          class="ip-tile__btn ip-tile__btn--cover"
          aria-label="Définir comme photo principale"
          title="Définir comme photo principale"
          @click="setCover(i)"
        >
          <PhStar :size="11" />
        </button>

        <button type="button" class="ip-tile__btn ip-tile__btn--remove" aria-label="Retirer cette photo" @click="removeImage(i)">
          <PhX :size="11" weight="bold" />
        </button>

        <span v-if="enhanced.has(url)" class="ip-tile__ai" title="Améliorée par l'IA">
          <PhSparkle :size="9" weight="fill" /> IA
        </span>
        <button
          v-else-if="canEnhance(url) && !enhancing.has(url)"
          type="button"
          class="ip-tile__enhance"
          :title="isPremium ? 'Améliorer cette photo avec l\'IA' : 'Amélioration IA — Premium'"
          @click="enhanceExisting(i)"
        >
          <PhSparkle :size="11" weight="fill" />
          <span>Améliorer</span>
        </button>

        <div v-if="enhancing.has(url)" class="ip-tile__overlay">
          <span class="ip-spark"><PhSparkle :size="18" weight="fill" /></span>
          <span>IA…</span>
        </div>
      </div>

      <div v-for="tile in pending" :key="tile.id" class="ip-tile ip-tile--pending" :class="{ 'ip-tile--ai': tile.ai }">
        <img :src="tile.preview" alt="" />
        <div class="ip-tile__overlay">
          <span v-if="tile.ai" class="ip-spark"><PhSparkle :size="18" weight="fill" /></span>
          <span v-else class="ip-spinner" />
          <span>{{ tile.ai ? 'Amélioration…' : 'Envoi…' }}</span>
        </div>
        <span class="ip-tile__progress" />
      </div>

      <button type="button" class="ip-add" :class="{ 'ip-add--ai': aiOn, 'ip-add--wide': compact && !images.length && !pending.length }" @click="pickFiles">
        <PhSparkle v-if="aiOn" :size="20" weight="fill" />
        <PhUploadSimple v-else :size="20" />
        <span>{{ compact && !images.length && !pending.length ? (aiOn ? 'Ajouter des photos (IA)' : 'Ajouter des photos') : 'Ajouter' }}</span>
      </button>
    </div>

    <!-- Zone de dépôt (galerie vide, mode complet) -->
    <button v-else type="button" class="ip-drop" :class="{ 'ip-drop--ai': aiOn }" @click="pickFiles">
      <span class="ip-drop__icon">
        <PhSparkle v-if="aiOn" :size="26" weight="fill" />
        <PhImage v-else :size="26" weight="light" />
      </span>
      <span class="ip-drop__title">Glisse tes photos ici</span>
      <span class="ip-drop__sub">ou <u>parcours tes fichiers</u> · JPEG, PNG, WebP · 8 Mo max</span>
      <span v-if="aiOn" class="ip-drop__ai">L'IA les détoure et les met sur fond blanc</span>
    </button>

    <div v-if="dragging" class="ip-dropmask">
      <PhUploadSimple :size="22" />
      <span>{{ aiOn ? 'Déposer pour ajouter et améliorer' : 'Déposer pour ajouter' }}</span>
    </div>

    <template v-if="!compact">
      <p v-if="images.length > 1" class="text-muted mt-2 mb-0 text-fine">
        La photo « Couverture » est celle affichée dans le catalogue — touche
        <PhStar :size="10" weight="bold" style="vertical-align: -1px" /> sur une autre pour la remplacer.
      </p>

      <details class="manual-url mt-2">
        <summary class="text-muted">
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

    <v-dialog v-model="premiumDialog" max-width="420">
      <div class="premium-card">
        <span class="premium-card__icon"><PhSparkle :size="26" weight="fill" /></span>
        <h3 class="premium-card__title">Photos pro avec l'IA</h3>
        <p class="premium-card__text">
          Détourage, fond blanc, recadrage et netteté en un geste : des fiches qui inspirent confiance et se vendent
          mieux. Cette fonction est incluse dans l'abonnement Premium.
        </p>
        <div class="premium-card__actions">
          <v-btn variant="text" @click="premiumDialog = false">Plus tard</v-btn>
          <v-btn color="primary" rounded="lg" to="/vendeur/abonnement" target="_blank" @click="premiumDialog = false">
            <PhCrown :size="16" weight="fill" class="mr-2" />
            Voir Premium
          </v-btn>
        </div>
        <p class="premium-card__note">S'ouvre dans un nouvel onglet — ton produit en cours n'est pas perdu.</p>
      </div>
    </v-dialog>
  </div>
</template>

<style scoped>
.ip {
  position: relative;
  --ip-violet: #7c3aed;
  --ip-gold: #b45309;
}

:root[data-theme='dark'] .ip {
  --ip-violet: #c4b5fd;
  --ip-gold: #fbbf24;
}

/* --- Interrupteur IA --- */
.ai-toggle {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-divider);
  background: var(--color-neutral-900);
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.2s ease, background 0.2s ease, box-shadow 0.2s ease;
}

.ai-toggle:hover {
  border-color: color-mix(in srgb, #8b5cf6 45%, var(--color-divider));
}

.ai-toggle--on {
  border-color: color-mix(in srgb, #8b5cf6 60%, transparent);
  background: linear-gradient(135deg, color-mix(in srgb, #8b5cf6 10%, transparent), color-mix(in srgb, var(--color-primary) 8%, transparent));
  box-shadow: 0 0 0 3px color-mix(in srgb, #8b5cf6 12%, transparent);
}

.ai-toggle--compact {
  width: auto;
  display: inline-flex;
  padding: 6px 10px;
  gap: 8px;
  margin-bottom: 10px;
}

.ai-toggle__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  border-radius: 10px;
  color: #fff;
  background: linear-gradient(135deg, #8b5cf6, var(--color-primary));
}

.ai-toggle--compact .ai-toggle__icon {
  width: 24px;
  height: 24px;
  border-radius: 7px;
}

.ai-toggle__text {
  display: flex;
  flex-direction: column;
  gap: 1px;
  flex: 1;
  min-width: 0;
}

.ai-toggle__title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13.5px;
  font-weight: 700;
  color: var(--color-neutral-100);
}

.ai-toggle--compact .ai-toggle__title {
  font-size: 12.5px;
}

.ai-toggle__sub {
  font-size: 12px;
  color: var(--color-neutral-400);
  line-height: 1.35;
}

.ai-toggle__premium {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 7px;
  border-radius: 999px;
  background: color-mix(in srgb, #f59e0b 18%, transparent);
  color: var(--ip-gold);
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.ai-toggle__switch {
  position: relative;
  width: 36px;
  height: 20px;
  flex-shrink: 0;
  border-radius: 999px;
  background: var(--color-neutral-700);
  transition: background 0.2s ease;
}

.ai-toggle__switch span {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25);
  transition: transform 0.2s ease;
}

.ai-toggle--on .ai-toggle__switch {
  background: linear-gradient(135deg, #8b5cf6, var(--color-primary));
}

.ai-toggle--on .ai-toggle__switch span {
  transform: translateX(16px);
}

.ai-toggle--compact .ai-toggle__switch {
  width: 30px;
  height: 17px;
}

.ai-toggle--compact .ai-toggle__switch span {
  width: 13px;
  height: 13px;
}

.ai-toggle--compact.ai-toggle--on .ai-toggle__switch span {
  transform: translateX(13px);
}

/* --- Galerie --- */
.ip-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(104px, 1fr));
  gap: 10px;
}

.ip-grid--strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.ip-tile,
.ip-add {
  position: relative;
  aspect-ratio: 1;
  border-radius: var(--radius-md);
  overflow: hidden;
}

.ip-grid--strip .ip-tile,
.ip-grid--strip .ip-add {
  width: 84px;
  height: 84px;
}

.ip-tile {
  background: #fff;
  border: 1px solid var(--color-divider);
  animation: ip-in 0.25s ease;
}

.ip-tile img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

@keyframes ip-in {
  from {
    opacity: 0;
    transform: scale(0.94);
  }
}

.ip-tile__btn {
  position: absolute;
  top: 5px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}

.ip-tile__btn--remove {
  right: 5px;
}

.ip-tile__btn--remove:hover {
  background: var(--color-error);
}

.ip-tile__btn--cover {
  left: 5px;
}

.ip-tile__btn--cover:hover {
  color: var(--color-accent);
}

.ip-tile__cover {
  position: absolute;
  top: 5px;
  left: 5px;
  display: flex;
  align-items: center;
  gap: 3px;
  height: 20px;
  min-width: 20px;
  justify-content: center;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--color-primary);
  color: #fff;
  font-size: 9.5px;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.ip-grid--strip .ip-tile__cover {
  padding: 0;
}

.ip-tile__ai,
.ip-tile__enhance {
  position: absolute;
  left: 5px;
  bottom: 5px;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  height: 20px;
  padding: 0 7px;
  border-radius: 999px;
  border: none;
  color: #fff;
  font-size: 10px;
  font-weight: 800;
  background: linear-gradient(135deg, #8b5cf6, var(--color-primary));
}

.ip-tile__enhance {
  cursor: pointer;
  opacity: 0;
  transform: translateY(4px);
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.ip-tile:hover .ip-tile__enhance,
.ip-tile__enhance:focus-visible {
  opacity: 1;
  transform: none;
}

/* Écran tactile : pas de survol, le bouton reste visible. */
@media (hover: none) {
  .ip-tile__enhance {
    opacity: 1;
    transform: none;
  }
}

.ip-grid--strip .ip-tile__enhance span {
  display: none;
}

.ip-grid--strip .ip-tile__enhance {
  padding: 0 5px;
}

.ip-tile__overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  background: rgba(15, 17, 26, 0.55);
  backdrop-filter: blur(2px);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
}

.ip-tile--pending img {
  object-fit: cover;
  filter: saturate(0.6);
}

.ip-tile--ai .ip-tile__overlay {
  background: linear-gradient(135deg, rgba(91, 33, 182, 0.55), rgba(37, 99, 235, 0.45));
}

.ip-tile__progress {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 3px;
  background: linear-gradient(90deg, transparent, #fff, transparent);
  background-size: 50% 100%;
  background-repeat: no-repeat;
  animation: ip-sweep 1.1s linear infinite;
}

@keyframes ip-sweep {
  from {
    background-position: -50% 0;
  }
  to {
    background-position: 150% 0;
  }
}

.ip-spinner {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #fff;
  animation: ip-spin 0.8s linear infinite;
}

.ip-spark {
  display: flex;
  animation: ip-pulse 1.2s ease-in-out infinite;
}

@keyframes ip-spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes ip-pulse {
  50% {
    transform: scale(1.25) rotate(12deg);
    opacity: 0.75;
  }
}

.ip-add {
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
  transition: background 0.15s ease, border-color 0.15s ease;
}

.ip-add:hover {
  background: color-mix(in srgb, var(--color-primary) 12%, transparent);
}

.ip-add--ai {
  border-color: #8b5cf6;
  color: var(--ip-violet);
  background: color-mix(in srgb, #8b5cf6 8%, transparent);
}

.ip-grid--strip .ip-add--wide {
  width: 100%;
  height: 84px;
  aspect-ratio: auto;
  flex-direction: row;
  gap: 8px;
  font-size: 13px;
}

/* --- Zone de dépôt --- */
.ip-drop {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 28px 16px;
  border-radius: var(--radius-lg);
  border: 1.5px dashed var(--color-divider-strong);
  background: color-mix(in srgb, var(--color-primary) 3%, transparent);
  color: inherit;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.ip-drop:hover {
  border-color: var(--color-primary);
  background: color-mix(in srgb, var(--color-primary) 7%, transparent);
}

.ip-drop--ai {
  border-color: color-mix(in srgb, #8b5cf6 60%, transparent);
  background: color-mix(in srgb, #8b5cf6 6%, transparent);
}

.ip-drop__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  border-radius: 16px;
  margin-bottom: 4px;
  background: color-mix(in srgb, var(--color-primary) 12%, transparent);
  color: var(--color-primary);
}

.ip-drop--ai .ip-drop__icon {
  color: #fff;
  background: linear-gradient(135deg, #8b5cf6, var(--color-primary));
}

.ip-drop__title {
  font-size: 14.5px;
  font-weight: 700;
  color: var(--color-neutral-100);
}

.ip-drop__sub {
  font-size: 12px;
  color: var(--color-neutral-400);
}

.ip-drop__ai {
  margin-top: 2px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ip-violet);
}

.ip-dropmask {
  position: absolute;
  inset: -6px;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border-radius: var(--radius-lg);
  border: 2px dashed var(--color-primary);
  background: color-mix(in srgb, var(--color-primary) 14%, var(--color-neutral-900));
  color: var(--color-primary);
  font-weight: 700;
  pointer-events: none;
}

.manual-url summary {
  font-size: 11.5px;
  cursor: pointer;
  list-style: none;
}

.manual-url summary::-webkit-details-marker {
  display: none;
}

/* --- Dialogue Premium --- */
.premium-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 28px 24px 18px;
  border-radius: var(--radius-lg);
  background: var(--color-neutral-900);
}

.premium-card__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  border-radius: 18px;
  color: #fff;
  background: linear-gradient(135deg, #8b5cf6, var(--color-primary));
  margin-bottom: 14px;
}

.premium-card__title {
  font-family: var(--font-heading);
  font-size: 19px;
  font-weight: 800;
  margin: 0 0 8px;
}

.premium-card__text {
  font-size: 13.5px;
  color: var(--color-neutral-300);
  line-height: 1.5;
  margin: 0 0 18px;
}

.premium-card__actions {
  display: flex;
  gap: 8px;
}

.premium-card__note {
  margin: 12px 0 0;
  font-size: 11.5px;
  color: var(--color-neutral-500);
}

@media (prefers-reduced-motion: reduce) {
  .ip-tile,
  .ip-spark,
  .ip-spinner,
  .ip-tile__progress {
    animation: none;
  }
}
</style>
