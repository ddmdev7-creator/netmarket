<script setup lang="ts">
import { PhPlus, PhTrash } from '@phosphor-icons/vue'
import type { CategoryCreate, CategoryRead } from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const { apiFetch } = useApi()
const toast = useToastStore()

const { data: categories, pending, refresh } = await useAsyncData(
  'admin-categories',
  () => apiFetch<CategoryRead[]>('/categories'),
  { default: () => [], getCachedData: () => undefined },
)

const categoryName = (id: string | null) => categories.value.find((c) => c.id === id)?.name ?? null

const parentOptions = computed(() => categories.value.map((c) => ({ title: c.name, value: c.id })))

const showForm = ref(false)
const creating = ref(false)
const form = ref<{ name: string; parent_id: string | null }>({ name: '', parent_id: null })

function startCreate() {
  form.value = { name: '', parent_id: null }
  showForm.value = true
}

async function submit() {
  if (form.value.name.trim().length < 1) {
    toast.error('Donne un nom à cette catégorie.')
    return
  }
  creating.value = true
  try {
    const payload: CategoryCreate = { name: form.value.name.trim(), parent_id: form.value.parent_id ?? undefined }
    await apiFetch('/categories', { method: 'POST', body: payload })
    await refresh()
    showForm.value = false
    toast.success('Catégorie créée.')
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible de créer cette catégorie."))
  } finally {
    creating.value = false
  }
}

const confirmDeleteId = ref<string | null>(null)
const deleting = ref(false)
async function deleteCategory() {
  if (!confirmDeleteId.value) return
  deleting.value = true
  try {
    await apiFetch(`/categories/${confirmDeleteId.value}`, { method: 'DELETE' })
    await refresh()
    toast.success('Catégorie supprimée.')
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible de supprimer cette catégorie — vérifie qu'aucun produit ne l'utilise encore."))
  } finally {
    deleting.value = false
    confirmDeleteId.value = null
  }
}
</script>

<template>
  <div class="admin-shell">
    <div class="d-flex justify-space-between align-center mb-4">
      <h1 class="text-h6">Catégories</h1>
      <v-btn color="primary" size="small" @click="startCreate">
        <PhPlus :size="16" class="mr-1" />
        Nouvelle
      </v-btn>
    </div>

    <v-card v-if="showForm" class="mb-4 pa-3">
      <label class="field-label">Nom de la catégorie</label>
      <v-text-field v-model="form.name" placeholder="Ex: Électronique" class="mb-2" />

      <label class="field-label">Catégorie parente (optionnel)</label>
      <v-select
        v-model="form.parent_id"
        :items="parentOptions"
        clearable
        placeholder="Aucune — catégorie principale"
        class="mb-1"
      />

      <div class="d-flex ga-2">
        <v-btn variant="outlined" class="flex-grow-1" @click="showForm = false">Annuler</v-btn>
        <v-btn color="primary" class="flex-grow-1" :loading="creating" @click="submit">Créer</v-btn>
      </div>
    </v-card>

    <CommonEmptyState v-if="!pending && categories.length === 0" message="Aucune catégorie pour l'instant." />

    <v-card v-for="c in categories" :key="c.id" class="mb-2 pa-3">
      <div class="d-flex justify-space-between align-center">
        <div>
          <div style="font-weight: 600; font-size: 13.5px">{{ c.name }}</div>
          <div v-if="c.parent_id" class="text-muted" style="font-size: 11.5px">
            Sous-catégorie de {{ categoryName(c.parent_id) ?? '…' }}
          </div>
        </div>
        <v-btn variant="outlined" color="error" size="small" @click="confirmDeleteId = c.id">
          <PhTrash :size="15" />
        </v-btn>
      </div>
    </v-card>

    <v-dialog :model-value="!!confirmDeleteId" max-width="340" @update:model-value="(v) => !v && (confirmDeleteId = null)">
      <v-card class="pa-5">
        <div class="text-subtitle-1 mb-2">Supprimer cette catégorie ?</div>
        <p class="text-muted mb-4" style="font-size: 13px">
          Impossible si des produits ou sous-catégories l'utilisent encore.
        </p>
        <div class="d-flex ga-2">
          <v-btn variant="outlined" class="flex-grow-1" @click="confirmDeleteId = null">Annuler</v-btn>
          <v-btn color="error" class="flex-grow-1" :loading="deleting" @click="deleteCategory">Supprimer</v-btn>
        </div>
      </v-card>
    </v-dialog>
  </div>
</template>
