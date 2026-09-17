<script setup lang="ts">
import { PhPlus, PhSparkle, PhSpinner, PhX } from '@phosphor-icons/vue'
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
// desktop (.app-shell--wide, voir pages/vendeur/produits/*.vue).
const tab = ref<'info' | 'images' | 'variants'>('info')
</script>

<template>
  <div>
    <v-tabs v-model="tab" color="primary" class="mb-4">
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
        <div class="form-grid">
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
          </div>
          <div>
            <label class="field-label">Nom du produit</label>
            <v-text-field v-model="model.name" placeholder="Ex: Riz parfumé 25kg" class="mb-2" />
          </div>
        </div>

        <label class="field-label">Description (optionnel)</label>
        <v-textarea v-model="model.description" rows="3" class="mb-2" />

        <div class="form-grid">
          <div>
            <label class="field-label">Prix (GNF)</label>
            <v-text-field v-model.number="model.price" type="number" min="0" class="mb-2" />
          </div>
          <div>
            <label class="field-label">Stock</label>
            <v-text-field
              v-model.number="model.stock"
              type="number"
              min="0"
              :disabled="visibleVariants.length > 0"
              :hint="visibleVariants.length > 0 ? 'Calculé automatiquement à partir des variantes.' : undefined"
              :persistent-hint="visibleVariants.length > 0"
              class="mb-2"
            />
          </div>
        </div>
      </v-window-item>

      <v-window-item value="images">
        <label class="field-label">Images — au moins 3 recommandées, la fiche produit affiche un carrousel</label>
        <CommonImagePicker v-model="model.images">
          <template #extra-actions>
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
          </template>
        </CommonImagePicker>
      </v-window-item>

      <v-window-item value="variants">
        <p class="text-muted mb-3" style="font-size: 12px">
          Ex : couleur, taille, matière... Chaque variante a son propre stock — et, si besoin, son propre prix et ses
          propres photos.
        </p>

        <div v-if="visibleVariants.length" class="variant-grid mb-3">
          <v-card v-for="row in visibleVariants" :key="row._key" variant="outlined" class="pa-3">
            <div class="d-flex justify-space-between align-center mb-3">
              <span style="font-weight: 600; font-size: 13.5px">{{ variantTitle(row) }}</span>
              <button type="button" class="attr-remove" aria-label="Supprimer cette variante" @click="removeVariant(row)">
                <PhX :size="16" />
              </button>
            </div>

            <label class="field-label">Attributs (ex: Couleur → Rouge)</label>
            <div v-for="(attr, ai) in row.attributes" :key="ai" class="d-flex ga-2 align-center mb-2">
              <v-text-field
                v-model="attr.name"
                placeholder="Nom (ex: Couleur)"
                density="compact"
                hide-details
                class="flex-grow-1"
              />
              <v-text-field
                v-model="attr.value"
                placeholder="Valeur (ex: Rouge)"
                density="compact"
                hide-details
                class="flex-grow-1"
              />
              <button type="button" class="attr-remove" aria-label="Retirer cet attribut" @click="removeAttribute(row, ai)">
                <PhX :size="14" />
              </button>
            </div>
            <v-btn variant="text" size="small" class="mb-4" @click="addAttribute(row)">
              <PhPlus :size="14" class="mr-1" />
              Ajouter un attribut
            </v-btn>

            <div class="d-flex ga-2">
              <div class="flex-grow-1">
                <label class="field-label">SKU (optionnel)</label>
                <v-text-field v-model="row.sku" density="compact" class="mb-2" />
              </div>
              <div class="flex-grow-1">
                <label class="field-label">Stock</label>
                <v-text-field v-model.number="row.stock" type="number" min="0" density="compact" class="mb-2" />
              </div>
            </div>

            <label class="field-label">Prix (optionnel — sinon le prix de base s'applique)</label>
            <v-text-field v-model.number="row.price" type="number" min="0" density="compact" class="mb-4" />

            <CommonImagePicker v-model="row.images" label="Photos de cette variante (optionnel)" />
          </v-card>
        </div>

        <v-btn variant="outlined" size="small" block class="mb-2" @click="addVariant">
          <PhPlus :size="14" class="mr-1" />
          Ajouter une variante
        </v-btn>
      </v-window-item>
    </v-window>
  </div>
</template>

<style scoped>
.attr-remove {
  background: none;
  border: none;
  color: var(--color-neutral-500);
  padding: 10px;
  margin: -10px;
  cursor: pointer;
  flex-shrink: 0;
}

/* Catégorie/Nom puis Prix/Stock : une colonne sur mobile (comportement
   inchangé), deux dès qu'il y a la place — le formulaire est maintenant
   affiché dans un conteneur élargi sur desktop (.app-shell--wide, voir
   pages/vendeur/produits/*.vue). */
.form-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0 12px;
}

@media (min-width: 640px) {
  .form-grid {
    grid-template-columns: 1fr 1fr;
  }
}

/* Une carte de variante par ligne sur mobile, deux dès qu'il y a la place —
   chaque carte reste assez large pour son propre formulaire (attributs,
   stock, prix, photos). */
.variant-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
}

@media (min-width: 900px) {
  .variant-grid {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
