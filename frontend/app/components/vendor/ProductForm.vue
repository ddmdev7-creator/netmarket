<script setup lang="ts">
import {
  PhArrowsClockwise,
  PhCaretDown,
  PhImage,
  PhPlus,
  PhSparkle,
  PhSpinner,
  PhTrash,
  PhUploadSimple,
  PhX,
} from '@phosphor-icons/vue'
import type { CategoryRead, VendorSubscriptionRead } from '~/types/api'

export interface VariantAttributeRow {
  name: string
  value: string
}

export interface VariantFormRow {
  // Clé stable purement locale (jamais envoyée à l'API) pour le :key du
  // v-for ci-dessous — nécessaire tant que id est encore null (variante pas
  // encore créée côté serveur).
  _key: string
  // null tant que la variante n'existe pas encore côté serveur (voir la
  // logique de diff create/update/delete dans nouveau.vue et [id].vue).
  id: string | null
  sku: string
  // false tant que le vendeur n'a pas saisi son propre SKU : il est alors
  // (re)généré automatiquement à partir du nom du produit et des valeurs
  // d'attribut (voir generateSku).
  skuManual?: boolean
  price: number | null
  stock: number
  images: string[]
  attributes: VariantAttributeRow[]
  // Marqueur de suppression en mode édition (le temps de differ au save) —
  // une ligne jamais créée côté serveur (id === null) est retirée du
  // tableau directement à la place.
  deleted?: boolean
}

export interface ProductFormValues {
  category_id: string | null
  name: string
  description: string
  price: number | null
  stock: number | null
  images: string[]
  variants: VariantFormRow[]
}

const model = defineModel<ProductFormValues>({ required: true })
// hideContext : la page d'édition a déjà son propre en-tête récapitulatif.
defineProps<{ categories: CategoryRead[]; hideContext?: boolean }>()

const { apiFetch } = useApi()

// Pas d'await ici : ProductForm est un composant enfant, pas une page — on
// laisse le statut premium arriver de façon réactive plutôt que de bloquer
// le rendu du formulaire dessus.
const { data: subscription } = useAsyncData(
  'product-form-subscription',
  () => apiFetch<VendorSubscriptionRead | null>('/subscriptions/me'),
  { default: () => null },
)
const isPremium = computed(() => subscription.value?.status === 'active')

const enhancing = ref(false)
const enhanceFileInput = ref<HTMLInputElement | null>(null)
const toast = useToastStore()

function pickEnhanceFiles() {
  if (!isPremium.value) {
    navigateTo('/vendeur/abonnement')
    return
  }
  enhanceFileInput.value?.click()
}

async function onEnhanceFilesSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const files = input.files ? Array.from(input.files) : []
  input.value = ''
  if (files.length === 0) return

  enhancing.value = true
  try {
    const formData = new FormData()
    for (const file of files) formData.append('files', file)
    const { keys } = await apiFetch<{ keys: string[] }>('/uploads/images/enhance', { method: 'POST', body: formData })
    model.value.images.push(...keys)
    toast.success(keys.length > 1 ? `${keys.length} images ajoutées.` : 'Image ajoutée.')
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'envoyer ces images."))
  } finally {
    enhancing.value = false
  }
}

// --- Variantes ---

const visibleVariants = computed(() => model.value.variants.filter((v) => !v.deleted))

function variantTitle(row: VariantFormRow): string {
  const values = row.attributes.map((a) => a.value.trim()).filter(Boolean)
  return values.length ? values.join(' / ') : 'Nouvelle variante'
}

function addVariant() {
  const key = crypto.randomUUID()
  // Reprend les noms d'attribut de la variante précédente (ex. Couleur +
  // Taille) : il ne reste plus qu'à taper les valeurs.
  const previous = visibleVariants.value[visibleVariants.value.length - 1]
  const names = previous?.attributes.map((a) => a.name).filter((n) => n.trim()) ?? []
  model.value.variants.push({
    _key: key,
    id: null,
    sku: '',
    skuManual: false,
    price: null,
    stock: 0,
    images: [],
    attributes: names.length ? names.map((name) => ({ name, value: '' })) : [{ name: '', value: '' }],
  })
  expanded.value.add(key)
  nextTick(() => {
    document.getElementById(`variant-${key}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

function removeVariant(row: VariantFormRow) {
  if (row.id) {
    row.deleted = true
    return
  }
  const index = model.value.variants.indexOf(row)
  if (index !== -1) model.value.variants.splice(index, 1)
}

// Cartes repliables : une variante déjà enregistrée s'affiche en une ligne
// résumé (photo, valeurs, prix, stock) — la page reste lisible même avec 10
// variantes ; une nouvelle variante s'ouvre directement.
const expanded = ref(new Set<string>())
function toggleVariant(row: VariantFormRow) {
  if (expanded.value.has(row._key)) expanded.value.delete(row._key)
  else expanded.value.add(row._key)
}

const apiBase = useApiBase()
function variantThumb(row: VariantFormRow): string | null {
  const image = row.images[0] || model.value.images.find((url) => url.trim())
  return image ? resolveImageUrl(image, apiBase) : null
}

// --- SKU automatique ---
// Ex. "T-shirt coton" + Rouge / M → "TSHI-COTO-ROUG-M". Toujours modifiable ;
// dès que le vendeur tape le sien, on n'y touche plus (skuManual).
function skuChunk(text: string, max: number): string[] {
  return text
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toUpperCase()
    .split(/[^A-Z0-9]+/)
    .filter(Boolean)
    .map((word) => word.slice(0, max))
}

function generateSku(row: VariantFormRow, taken: Set<string>): string {
  const base = skuChunk(model.value.name, 4).slice(0, 2)
  const values = row.attributes.flatMap((a) => skuChunk(a.value, 4).slice(0, 2).join('') || [])
  const parts = [...(base.length ? base : ['PRD']), ...values]
  const root = parts.join('-').slice(0, 58)
  let sku = root
  for (let n = 2; taken.has(sku); n++) sku = `${root}-${n}`
  return sku
}

function refreshAutoSkus() {
  const rows = visibleVariants.value
  const taken = new Set(rows.filter((r) => r.skuManual).map((r) => r.sku.trim()))
  for (const row of rows) {
    if (row.skuManual) continue
    row.sku = generateSku(row, taken)
    taken.add(row.sku)
  }
}

watch(
  () => [model.value.name, visibleVariants.value.map((r) => `${r._key}:${r.skuManual}:${r.attributes.map((a) => a.value).join('|')}`)],
  refreshAutoSkus,
  { immediate: true, deep: true },
)

function onSkuInput(row: VariantFormRow, value: string) {
  row.sku = value
  row.skuManual = value.trim().length > 0
}

function resetSku(row: VariantFormRow) {
  row.skuManual = false
  refreshAutoSkus()
}

function addAttribute(row: VariantFormRow) {
  row.attributes.push({ name: '', value: '' })
}

function removeAttribute(row: VariantFormRow, index: number) {
  row.attributes.splice(index, 1)
}

// Formulaire volumineux (infos + photos + variantes) : des onglets plutôt
// qu'une longue page qui scrolle, surtout utile sur le conteneur élargi en
// desktop (.dashboard-shell, voir pages/vendeur/produits/*.vue).
const tab = ref<'info' | 'images' | 'variants'>('info')

// Suggestions pour aller plus vite — le nom d'attribut reste du texte libre
// (v-combobox accepte aussi bien une saisie hors liste), voir la conception
// des variantes : pas de taxonomie imposée entre vendeurs.
const commonAttributeNames = ['Couleur', 'Taille', 'Pointure', 'Matière', 'Capacité', 'Poids']
</script>

<template>
  <div>
    <!-- Hors du v-window : reste visible quel que soit l'onglet actif, pour
         ne jamais perdre de vue quel produit on est en train de modifier. -->
    <div v-if="!hideContext" class="product-context">
      <span class="product-context__label">Produit</span>
      <span class="product-context__name">{{ model.name.trim() || 'Nouveau produit (sans nom)' }}</span>
    </div>

    <v-tabs v-model="tab" color="primary" class="mb-5">
      <v-tab value="info">Informations</v-tab>
      <v-tab value="images">Photos</v-tab>
      <v-tab value="variants">
        Variantes
        <v-chip v-if="visibleVariants.length" size="x-small" color="primary" class="ml-2">{{
          visibleVariants.length
        }}</v-chip>
      </v-tab>
    </v-tabs>

    <v-window v-model="tab">
      <v-window-item value="info">
        <div class="panel-card">
          <div class="panel-card__header">
            <span class="panel-card__title">Informations générales</span>
          </div>
          <div class="panel-card__body">
            <div class="form-grid">
              <div>
                <label class="field-label">Catégorie</label>
                <v-select
                  v-model="model.category_id"
                  :items="categories"
                  item-title="name"
                  item-value="id"
                  placeholder="Choisir une catégorie"
                  variant="outlined"
                  density="comfortable"
                  class="mb-3"
                />
              </div>
              <div>
                <label class="field-label">Nom du produit</label>
                <v-text-field
                  v-model="model.name"
                  placeholder="Ex: Riz parfumé 25kg"
                  variant="outlined"
                  density="comfortable"
                  class="mb-3"
                />
              </div>
            </div>

            <label class="field-label">Description (optionnel)</label>
            <CommonRichTextEditor v-model="model.description" class="mb-3" />

            <div class="form-grid">
              <div>
                <label class="field-label">Prix (GNF)</label>
                <v-text-field
                  v-model.number="model.price"
                  type="number"
                  min="0"
                  variant="outlined"
                  density="comfortable"
                  class="mb-3"
                />
              </div>
              <div>
                <label class="field-label">Stock</label>
                <v-text-field
                  v-model.number="model.stock"
                  type="number"
                  min="0"
                  variant="outlined"
                  density="comfortable"
                  :disabled="visibleVariants.length > 0"
                  :hint="visibleVariants.length > 0 ? 'Calculé automatiquement à partir des variantes.' : undefined"
                  :persistent-hint="visibleVariants.length > 0"
                  class="mb-3"
                />
              </div>
            </div>
          </div>
        </div>
      </v-window-item>

      <v-window-item value="images">
        <div class="panel-card">
          <div class="panel-card__header">
            <span class="panel-card__title">Photos du produit</span>
          </div>
          <div class="panel-card__body">
            <label class="field-label">Au moins 3 recommandées — la fiche produit affiche un carrousel</label>
            <CommonImagePicker v-model="model.images">
              <template #extra-actions>
                <div class="ai-hint">
                  <PhSparkle :size="13" />
                  <span>Ou uploade de nouvelles photos et laisse l'IA les améliorer automatiquement (fond, netteté) :</span>
                </div>
                <input
                  ref="enhanceFileInput"
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  multiple
                  class="d-none"
                  @change="onEnhanceFilesSelected"
                />
                <v-btn
                  variant="tonal"
                  color="primary"
                  size="small"
                  class="mb-2"
                  :loading="enhancing"
                  @click="pickEnhanceFiles"
                >
                  <PhSpinner v-if="enhancing" :size="14" class="mr-1" />
                  <PhUploadSimple v-else :size="14" class="mr-1" />
                  Uploader avec amélioration IA {{ isPremium ? '' : '(Premium)' }}
                </v-btn>
              </template>
            </CommonImagePicker>
          </div>
        </div>
      </v-window-item>

      <v-window-item value="variants">
        <div class="variants-wrap">
          <div class="variants-intro">
            <strong>Une variante = une combinaison précise</strong> (ex. Rouge + M). Rouge/M et Rouge/L sont deux
            variantes distinctes, chacune avec son stock et, si besoin, son prix.
          </div>

          <CommonEmptyState
            v-if="!visibleVariants.length"
            message="Aucune variante pour l'instant — ce produit se vend avec un stock et un prix uniques."
          />

          <div v-else class="variant-list">
            <div
              v-for="row in visibleVariants"
              :id="`variant-${row._key}`"
              :key="row._key"
              class="variant-card"
              :class="{ 'variant-card--open': expanded.has(row._key) }"
            >
              <div class="variant-card__head" role="button" tabindex="0" @click="toggleVariant(row)" @keydown.enter="toggleVariant(row)">
                <div class="variant-card__thumb">
                  <img v-if="variantThumb(row)" :src="variantThumb(row)!" alt="" />
                  <PhImage v-else :size="20" weight="light" />
                </div>
                <div class="variant-card__summary">
                  <div class="variant-card__title">{{ variantTitle(row) }}</div>
                  <div class="variant-card__meta">
                    <span>{{ formatGnf(row.price ?? model.price ?? 0) }}</span>
                    <span class="variant-card__dot">·</span>
                    <span :class="{ 'variant-card__stock--out': !row.stock }">
                      {{ row.stock ? `${row.stock} en stock` : 'Rupture' }}
                    </span>
                  </div>
                </div>
                <button
                  type="button"
                  class="icon-btn"
                  aria-label="Supprimer cette variante"
                  @click.stop="removeVariant(row)"
                >
                  <PhTrash :size="16" />
                </button>
                <PhCaretDown :size="16" class="variant-card__caret" />
              </div>

              <div v-if="expanded.has(row._key)" class="variant-card__body">
                <section class="variant-section">
                  <div class="variant-section__title">
                    <span class="variant-section__step">1</span>
                    Photos
                    <span class="variant-section__opt">facultatif</span>
                  </div>
                  <CommonImagePicker v-model="row.images" :label="''" compact />
                  <p class="variant-section__help">
                    Sans photo, la variante reprend celles du produit. Ajoutes-en si elle a un aspect différent (autre
                    couleur, motif…).
                  </p>
                </section>

                <section class="variant-section">
                  <div class="variant-section__title">
                    <span class="variant-section__step">2</span>
                    Caractéristiques
                  </div>
                  <div v-for="(attr, ai) in row.attributes" :key="ai" class="attr-row mb-2">
                    <v-combobox
                      v-model="attr.name"
                      :items="commonAttributeNames"
                      placeholder="Nom (ex: Couleur)"
                      variant="outlined"
                      density="compact"
                      hide-details
                      class="attr-row__field"
                    />
                    <v-text-field
                      v-model="attr.value"
                      placeholder="Valeur (ex: Rouge)"
                      variant="outlined"
                      density="compact"
                      hide-details
                      class="attr-row__field"
                    />
                    <button
                      type="button"
                      class="icon-btn"
                      aria-label="Retirer cet attribut"
                      :disabled="row.attributes.length === 1"
                      @click="removeAttribute(row, ai)"
                    >
                      <PhX :size="14" />
                    </button>
                  </div>
                  <v-btn variant="text" color="primary" size="small" class="px-1" @click="addAttribute(row)">
                    <PhPlus :size="14" class="mr-1" />
                    Ajouter une caractéristique
                  </v-btn>
                </section>

                <section class="variant-section">
                  <div class="variant-section__title">
                    <span class="variant-section__step">3</span>
                    Prix et stock
                  </div>
                  <div class="form-grid">
                    <div>
                      <label class="field-label">Prix (GNF)</label>
                      <v-text-field
                        v-model.number="row.price"
                        type="number"
                        min="0"
                        variant="outlined"
                        density="compact"
                        :placeholder="model.price !== null ? String(model.price) : ''"
                        hint="Vide = prix du produit"
                        persistent-hint
                        class="mb-3"
                      />
                    </div>
                    <div>
                      <label class="field-label">Stock</label>
                      <v-text-field
                        v-model.number="row.stock"
                        type="number"
                        min="0"
                        variant="outlined"
                        density="compact"
                        class="mb-3"
                      />
                    </div>
                  </div>

                  <label class="field-label">Référence (SKU)</label>
                  <v-text-field
                    :model-value="row.sku"
                    variant="outlined"
                    density="compact"
                    :hint="row.skuManual ? 'Référence personnalisée' : 'Générée automatiquement — modifiable'"
                    persistent-hint
                    class="sku-field"
                    @update:model-value="onSkuInput(row, $event)"
                  >
                    <template v-if="row.skuManual" #append-inner>
                      <button
                        type="button"
                        class="icon-btn icon-btn--plain"
                        title="Revenir au SKU automatique"
                        aria-label="Revenir au SKU automatique"
                        @click="resetSku(row)"
                      >
                        <PhArrowsClockwise :size="15" />
                      </button>
                    </template>
                  </v-text-field>
                </section>
              </div>
            </div>
          </div>

          <div class="variants-add">
            <v-btn color="primary" size="large" rounded="lg" @click="addVariant">
              <PhPlus :size="18" class="mr-2" />
              Ajouter une variante
            </v-btn>
          </div>
        </div>
      </v-window-item>
    </v-window>
  </div>
</template>

<style scoped>
.icon-btn {
  background: none;
  border: none;
  color: var(--color-neutral-500);
  padding: 10px;
  margin: -10px;
  cursor: pointer;
  flex-shrink: 0;
  border-radius: var(--radius-sm);
  transition: color 0.15s ease, background 0.15s ease;
}

.icon-btn:hover {
  color: var(--color-error);
  background: var(--color-neutral-800);
}

/* Le bouton de suppression dans .panel-card__header est sur fond bleu
   foncé (--color-primary-800) en permanence, dans les deux thèmes — un
   survol clair plutôt que --color-neutral-800 (qui se fondrait dans ce
   fond sombre au lieu de s'en détacher). */
.panel-card__header .icon-btn {
  color: var(--color-primary-100);
  opacity: 0.75;
}

.panel-card__header .icon-btn:hover {
  color: #fff;
  opacity: 1;
  background: rgba(255, 255, 255, 0.14);
}

/* Catégorie/Nom puis Prix/Stock : une colonne quand la CARTE qui contient
   ce grid est étroite, deux dès qu'elle a la place. Une @media ferait ce
   choix sur la largeur du VIEWPORT — faux pour une carte de variante,
   plus étroite que la page. @container réagit à la largeur réelle de la
   carte (voir container-type sur .panel-card__body / .variant-card__body). Le champ lui-même reste plafonné (voir
   .form-grid > div) même dans une carte pleine largeur (Informations
   générales) — sinon un champ "Prix" étiré sur 600px serait aussi absurde
   que le bug qu'on corrige ici. */
.form-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0 14px;
}

@container (min-width: 480px) {
  .form-grid {
    grid-template-columns: 1fr 1fr;
  }

  .form-grid > div {
    max-width: 420px;
  }
}

/* Nom/Valeur d'un attribut : côte à côte quand il y a la place, sinon
   chacun repasse sur sa propre ligne plutôt que d'être écrasé — une carte
   de variante peut être étroite sur téléphone,
   pas assez pour deux champs + le bouton de suppression sans wrap. */
.attr-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.attr-row__field {
  flex: 1 1 140px;
  min-width: 140px;
}


/* Variantes : une colonne centrée de cartes repliables, bouton d'ajout
   centré dessous. */
.variants-wrap {
  max-width: 820px;
  margin: 0 auto;
}

.variants-intro {
  margin-bottom: 16px;
  padding: 12px 14px;
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--color-primary) 7%, transparent);
  color: var(--color-neutral-300);
  font-size: 13px;
  line-height: 1.5;
}

.variants-intro strong {
  color: var(--color-neutral-100);
}

.variant-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.variant-card {
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
  scroll-margin-top: 16px;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.variant-card--open {
  border-color: var(--color-primary-300);
  box-shadow: var(--shadow-md);
}

.variant-card__head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px 10px 10px;
  cursor: pointer;
  user-select: none;
}

.variant-card__head:hover {
  background: var(--color-neutral-800);
}

.variant-card__thumb {
  width: 52px;
  height: 52px;
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

.variant-card__thumb img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.variant-card__summary {
  flex: 1;
  min-width: 0;
}

.variant-card__title {
  font-weight: 700;
  font-size: 14.5px;
  color: var(--color-neutral-100);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.variant-card__meta {
  display: flex;
  gap: 6px;
  margin-top: 2px;
  font-size: 12.5px;
  color: var(--color-neutral-400);
}

.variant-card__meta > span:first-child {
  color: var(--color-accent);
  font-weight: 700;
}

.variant-card__stock--out {
  color: var(--color-error);
  font-weight: 600;
}

.variant-card__caret {
  flex: none;
  color: var(--color-neutral-500);
  transition: transform 0.2s ease;
}

.variant-card--open .variant-card__caret {
  transform: rotate(180deg);
}

.variant-card__body {
  padding: 4px 20px 20px;
  border-top: 1px solid var(--color-divider);
  container-type: inline-size;
}

.variant-section {
  padding-top: 18px;
}

.variant-section + .variant-section {
  margin-top: 18px;
  border-top: 1px dashed var(--color-divider);
}

.variant-section__title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-weight: 700;
  font-size: 14px;
  color: var(--color-neutral-100);
}

.variant-section__step {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--color-primary);
  color: #fff;
  font-size: 12px;
}

.variant-section__opt {
  font-weight: 500;
  font-size: 11.5px;
  color: var(--color-neutral-500);
}

.variant-section__help {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--color-neutral-500);
}

.sku-field :deep(input) {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  letter-spacing: 0.02em;
}

.icon-btn--plain:hover {
  color: var(--color-primary);
}

.icon-btn:disabled {
  opacity: 0.3;
  pointer-events: none;
}

.variants-add {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}

/* Carte blanche (fond de surface explicite plutôt que de compter sur le
   variant Vuetify du dessous) avec un bandeau de titre coloré — même look
   pour la fiche "Informations", "Photos" et chaque variante, plutôt que des
   champs posés à nu sur le fond gris de la page. */
.panel-card {
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}

.panel-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--color-primary-800);
}

.panel-card__title {
  font-weight: 700;
  font-size: 13.5px;
  color: var(--color-primary-100);
}

.panel-card__body {
  padding: 20px;
  /* Sert de référence pour les @container ci-dessus (.form-grid) — la
     largeur qui compte est celle de CETTE carte, pas celle du viewport. */
  container-type: inline-size;
}

.product-context {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
}

.product-context__label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-neutral-500);
}

.product-context__name {
  font-size: 15px;
  font-weight: 700;
  font-family: var(--font-heading);
  color: var(--color-neutral-200);
}

.ai-hint {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  color: var(--color-primary-300);
  font-size: 11.5px;
  margin-bottom: 8px;
}

.ai-hint svg {
  flex-shrink: 0;
  margin-top: 1px;
}
</style>
