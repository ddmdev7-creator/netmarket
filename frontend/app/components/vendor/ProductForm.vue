<script setup lang="ts">
import { PhPlus, PhSparkle, PhSpinner, PhUploadSimple, PhX } from '@phosphor-icons/vue'
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
defineProps<{ categories: CategoryRead[] }>()

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
  model.value.variants.push({
    _key: crypto.randomUUID(),
    id: null,
    sku: '',
    price: null,
    stock: 0,
    images: [],
    attributes: [{ name: '', value: '' }],
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
    <div class="product-context">
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
        <p class="text-muted mb-4 text-body">
          Une variante = une combinaison précise (ex. Couleur : Rouge + Taille : M). Ajoute plusieurs attributs à une
          même carte pour la préciser, et une carte séparée pour chaque combinaison différente (Rouge/M et Rouge/L
          sont deux variantes distinctes). Chaque variante a son propre stock — et, si besoin, son propre prix.
        </p>

        <CommonEmptyState
          v-if="!visibleVariants.length"
          message="Aucune variante pour l'instant — ce produit se vend avec un stock et un prix uniques."
        />

        <div v-else class="variant-grid mb-4">
          <div v-for="row in visibleVariants" :key="row._key" class="panel-card">
            <div class="panel-card__header">
              <span class="panel-card__title">{{ variantTitle(row) }}</span>
              <button type="button" class="icon-btn" aria-label="Supprimer cette variante" @click="removeVariant(row)">
                <PhX :size="16" />
              </button>
            </div>

            <div class="panel-card__body">
              <div class="attr-box">
                <label class="field-label mb-2">Attributs de cette variante</label>
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
                    @click="removeAttribute(row, ai)"
                  >
                    <PhX :size="14" />
                  </button>
                </div>
                <v-btn variant="text" color="primary" size="small" @click="addAttribute(row)">
                  <PhPlus :size="14" class="mr-1" />
                  Ajouter un attribut à cette variante
                </v-btn>
              </div>

              <v-divider class="my-4" />

              <div class="form-grid">
                <div>
                  <label class="field-label">SKU (optionnel)</label>
                  <v-text-field
                    v-model="row.sku"
                    placeholder="Ex: TSH-RD-M"
                    variant="outlined"
                    density="compact"
                    hint="Référence interne pour retrouver cette variante dans tes propres outils (code-barres, fournisseur...) — l'app ne l'utilise pas."
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

              <label class="field-label">Prix (optionnel — sinon le prix de base s'applique)</label>
              <v-text-field
                v-model.number="row.price"
                type="number"
                min="0"
                variant="outlined"
                density="compact"
                class="mb-4"
              />

              <v-divider class="mb-4" />

              <CommonImagePicker v-model="row.images" label="Photos de cette variante (optionnel)" />
              <p class="text-muted mt-2 mb-0 text-fine">
                Laisse vide pour reprendre les photos du produit (onglet Photos) — n'ajoute des photos ici que si
                cette variante a une apparence différente (ex. une autre couleur).
              </p>
            </div>
          </div>
        </div>

        <v-btn variant="tonal" color="primary" @click="addVariant">
          <PhPlus :size="16" class="mr-1" />
          Ajouter une variante
        </v-btn>
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
   choix sur la largeur du VIEWPORT — faux dès que plusieurs cartes de
   variante sont posées côte à côte par .variant-grid (chaque carte peut
   alors rester étroite même sur un très grand écran), d'où les champs mal
   alignés signalés. @container réagit à la largeur réelle de
   .panel-card__body (voir container-type ci-dessous), quel que soit le
   nombre de cartes affichées à côté. Le champ lui-même reste plafonné (voir
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
   de variante peut descendre jusqu'à 420px de large (voir .variant-grid),
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


/* auto-fit + minmax(min(420px, 100%), 1fr) plutôt que des colonnes fixes
   par media query : avec une seule variante, un grid-template-columns fixe
   à "1fr 1fr" ne remplirait que la moitié du conteneur (la 2e colonne
   resterait vide mais réservée) — auto-fit fait grandir la carte pour
   occuper toute la largeur quand il n'y en a qu'une, et ne crée d'autres
   colonnes que quand une 2e/3e carte tient vraiment à côté. min(420px,100%)
   évite tout débordement sur mobile (sinon minmax(420px,...) imposerait
   420px de large même sur un écran de téléphone plus étroit). */
.variant-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(420px, 100%), 1fr));
  gap: 16px;
  align-items: start;
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

/* Détache visuellement le bloc d'attributs (le cœur de "ce qui distingue
   cette variante") du reste des champs, plutôt qu'une simple liste de
   champs qui se ressemble tous. */
.attr-box {
  background: var(--color-neutral-800);
  border-radius: var(--radius-md);
  padding: 12px;
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
