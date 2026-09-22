<script setup lang="ts">
import {
  PhFolderSimple,
  PhFolderSimpleDashed,
  PhMagnifyingGlass,
  PhPencilSimple,
  PhPlus,
  PhStack,
  PhTrash,
  PhWarningCircle,
} from '@phosphor-icons/vue'
import type { CategoryCreate, CategoryRead, CategoryUpdate } from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const { apiFetch } = useApi()
const toast = useToastStore()

const { data: categories, pending, refresh } = await useAsyncData(
  'admin-categories',
  () => apiFetch<CategoryRead[]>('/categories'),
  { default: () => [], getCachedData: () => undefined },
)

// --- Arborescence -----------------------------------------------------------

interface CategoryRow {
  category: CategoryRead
  depth: number
  childCount: number
  path: string
}

const byId = computed(() => new Map(categories.value.map((c) => [c.id, c])))

const childrenOf = computed(() => {
  const map = new Map<string | null, CategoryRead[]>()
  for (const c of categories.value) {
    // Un parent introuvable (ne devrait pas arriver, FK) retombe à la racine
    // plutôt que de faire disparaître la catégorie de la liste.
    const key = c.parent_id && byId.value.has(c.parent_id) ? c.parent_id : null
    map.set(key, [...(map.get(key) ?? []), c])
  }
  for (const list of map.values()) list.sort((a, b) => a.name.localeCompare(b.name, 'fr'))
  return map
})

/** Liste à plat parcourue en profondeur (parent avant ses enfants), avec la profondeur pour l'indentation. */
const allRows = computed<CategoryRow[]>(() => {
  const rows: CategoryRow[] = []
  const visit = (parentId: string | null, depth: number, pathPrefix: string) => {
    for (const category of childrenOf.value.get(parentId) ?? []) {
      const path = pathPrefix ? `${pathPrefix} › ${category.name}` : category.name
      rows.push({ category, depth, childCount: childrenOf.value.get(category.id)?.length ?? 0, path })
      visit(category.id, depth + 1, path)
    }
  }
  visit(null, 0, '')
  return rows
})

const rootCount = computed(() => childrenOf.value.get(null)?.length ?? 0)

// --- Recherche --------------------------------------------------------------

// Insensible à la casse et aux accents ("electronique" trouve "Électronique").
function normalize(text: string): string {
  return text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().trim()
}

const search = ref('')

/**
 * Garde les catégories qui correspondent, leurs ancêtres (pour garder le
 * contexte de l'arborescence) et leurs descendants (une recherche sur
 * « Mode » doit montrer ce qu'il y a dedans).
 */
const visibleRows = computed<CategoryRow[]>(() => {
  const term = normalize(search.value)
  if (!term) return allRows.value
  const keep = new Set<string>()
  for (const row of allRows.value) {
    if (!normalize(row.category.name).includes(term)) continue
    keep.add(row.category.id)
    let parentId = row.category.parent_id
    while (parentId) {
      keep.add(parentId)
      parentId = byId.value.get(parentId)?.parent_id ?? null
    }
    const addDescendants = (id: string) => {
      for (const child of childrenOf.value.get(id) ?? []) {
        keep.add(child.id)
        addDescendants(child.id)
      }
    }
    addDescendants(row.category.id)
  }
  return allRows.value.filter((row) => keep.has(row.category.id))
})

const isMatch = (row: CategoryRow) => {
  const term = normalize(search.value)
  return term !== '' && normalize(row.category.name).includes(term)
}

// --- Création / modification -------------------------------------------------

const dialogOpen = ref(false)
const editingId = ref<string | null>(null)
const saving = ref(false)
const form = ref<{ name: string; parent_id: string | null }>({ name: '', parent_id: null })

function descendantIds(id: string): Set<string> {
  const result = new Set<string>()
  const walk = (parentId: string) => {
    for (const child of childrenOf.value.get(parentId) ?? []) {
      result.add(child.id)
      walk(child.id)
    }
  }
  walk(id)
  return result
}

/** Parents possibles : toutes les catégories sauf elle-même et ses descendantes (sinon boucle). */
const parentOptions = computed(() => {
  const excluded = editingId.value ? descendantIds(editingId.value) : new Set<string>()
  if (editingId.value) excluded.add(editingId.value)
  return allRows.value
    .filter((row) => !excluded.has(row.category.id))
    .map((row) => ({ title: row.path, value: row.category.id }))
})

function openCreate(parentId: string | null = null) {
  editingId.value = null
  form.value = { name: '', parent_id: parentId }
  dialogOpen.value = true
}

function openEdit(category: CategoryRead) {
  editingId.value = category.id
  form.value = { name: category.name, parent_id: category.parent_id }
  dialogOpen.value = true
}

async function save() {
  const name = form.value.name.trim()
  if (!name) {
    toast.error('Donne un nom à cette catégorie.')
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      const payload: CategoryUpdate = { name, parent_id: form.value.parent_id }
      await apiFetch(`/categories/${editingId.value}`, { method: 'PATCH', body: payload })
    } else {
      const payload: CategoryCreate = { name, parent_id: form.value.parent_id ?? undefined }
      await apiFetch('/categories', { method: 'POST', body: payload })
    }
    await refresh()
    dialogOpen.value = false
    toast.success(editingId.value ? 'Catégorie mise à jour.' : 'Catégorie créée.')
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'enregistrer cette catégorie."))
  } finally {
    saving.value = false
  }
}

// --- Suppression ------------------------------------------------------------

const toDelete = ref<CategoryRow | null>(null)
const deleting = ref(false)

async function deleteCategory() {
  if (!toDelete.value) return
  deleting.value = true
  try {
    await apiFetch(`/categories/${toDelete.value.category.id}`, { method: 'DELETE' })
    await refresh()
    toDelete.value = null
    toast.success('Catégorie supprimée.')
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible de supprimer cette catégorie — vérifie qu'aucun produit ne l'utilise encore."))
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <div class="dashboard-shell">
    <div class="cat-header">
      <div>
        <h1 class="text-h6">Catégories</h1>
        <p class="text-muted cat-header__sub">
          {{ categories.length }} catégorie{{ categories.length > 1 ? 's' : '' }} dont {{ rootCount }}
          principale{{ rootCount > 1 ? 's' : '' }}
        </p>
      </div>
      <v-btn color="primary" @click="openCreate()">
        <PhPlus :size="16" class="mr-1" />
        Nouvelle catégorie
      </v-btn>
    </div>

    <div class="cat-search">
      <PhMagnifyingGlass :size="17" class="cat-search__icon" />
      <input
        v-model="search"
        type="search"
        class="cat-search__input"
        placeholder="Rechercher une catégorie…"
        aria-label="Rechercher une catégorie"
      />
      <span v-if="search" class="cat-search__count">
        {{ visibleRows.filter(isMatch).length }} résultat{{ visibleRows.filter(isMatch).length > 1 ? 's' : '' }}
      </span>
    </div>

    <CommonEmptyState
      v-if="!pending && categories.length === 0"
      message="Aucune catégorie pour l'instant."
      :icon="PhStack"
    />
    <CommonEmptyState
      v-else-if="!pending && visibleRows.length === 0"
      :message="`Aucune catégorie ne correspond à « ${search} ».`"
      :icon="PhMagnifyingGlass"
    />

    <div v-if="visibleRows.length" class="cat-list">
      <div
        v-for="row in visibleRows"
        :key="row.category.id"
        class="cat-row"
        :class="{ 'cat-row--match': isMatch(row), 'cat-row--root': row.depth === 0 }"
        :style="{ paddingLeft: `${14 + row.depth * 26}px` }"
      >
        <span v-if="row.depth > 0" class="cat-row__branch" :style="{ left: `${14 + (row.depth - 1) * 26 + 8}px` }" />
        <component
          :is="row.childCount > 0 || row.depth === 0 ? PhFolderSimple : PhFolderSimpleDashed"
          :size="20"
          :weight="row.depth === 0 ? 'fill' : 'regular'"
          class="cat-row__icon"
        />
        <div class="cat-row__main">
          <span class="cat-row__name">{{ row.category.name }}</span>
          <span v-if="row.childCount > 0" class="cat-row__badge">
            {{ row.childCount }} sous-catégorie{{ row.childCount > 1 ? 's' : '' }}
          </span>
        </div>
        <div class="cat-row__actions">
          <v-btn
            icon
            variant="text"
            size="small"
            :aria-label="`Ajouter une sous-catégorie à ${row.category.name}`"
            title="Ajouter une sous-catégorie"
            @click="openCreate(row.category.id)"
          >
            <PhPlus :size="17" />
          </v-btn>
          <v-btn
            icon
            variant="text"
            size="small"
            :aria-label="`Modifier ${row.category.name}`"
            title="Modifier"
            @click="openEdit(row.category)"
          >
            <PhPencilSimple :size="17" />
          </v-btn>
          <v-btn
            icon
            variant="text"
            size="small"
            color="error"
            :aria-label="`Supprimer ${row.category.name}`"
            title="Supprimer"
            @click="toDelete = row"
          >
            <PhTrash :size="17" />
          </v-btn>
        </div>
      </div>
    </div>

    <v-dialog v-model="dialogOpen" max-width="420">
      <v-card class="pa-5">
        <div class="text-h6 mb-4">{{ editingId ? 'Modifier la catégorie' : 'Nouvelle catégorie' }}</div>

        <label class="field-label">Nom de la catégorie</label>
        <v-text-field
          v-model="form.name"
          placeholder="Ex: Électronique"
          maxlength="100"
          autofocus
          class="mb-2"
          @keydown.enter="save"
        />

        <label class="field-label">Catégorie parente (optionnel)</label>
        <v-select
          v-model="form.parent_id"
          :items="parentOptions"
          clearable
          placeholder="Aucune — catégorie principale"
          class="mb-1"
        />
        <p class="text-muted mb-4" style="font-size: 11.5px">
          Choisir un parent range cette catégorie dans une autre ; vide, c'est une catégorie principale.
        </p>

        <div class="d-flex ga-2">
          <v-btn variant="outlined" class="flex-grow-1" @click="dialogOpen = false">Annuler</v-btn>
          <v-btn color="primary" class="flex-grow-1" :loading="saving" @click="save">
            {{ editingId ? 'Enregistrer' : 'Créer' }}
          </v-btn>
        </div>
      </v-card>
    </v-dialog>

    <v-dialog :model-value="!!toDelete" max-width="380" @update:model-value="(v) => !v && (toDelete = null)">
      <v-card v-if="toDelete" class="pa-5">
        <div class="text-h6 mb-2">Supprimer « {{ toDelete.category.name }} » ?</div>
        <div v-if="toDelete.childCount > 0" class="cat-warning mb-4">
          <PhWarningCircle :size="18" weight="fill" />
          <span>
            Cette catégorie contient {{ toDelete.childCount }} sous-catégorie{{ toDelete.childCount > 1 ? 's' : '' }} :
            déplace-les ou supprime-les d'abord.
          </span>
        </div>
        <p v-else class="text-muted mb-4" style="font-size: 13px">
          Impossible si des produits l'utilisent encore.
        </p>
        <div class="d-flex ga-2">
          <v-btn variant="outlined" class="flex-grow-1" @click="toDelete = null">Annuler</v-btn>
          <v-btn
            color="error"
            class="flex-grow-1"
            :loading="deleting"
            :disabled="toDelete.childCount > 0"
            @click="deleteCategory"
          >
            Supprimer
          </v-btn>
        </div>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.cat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.cat-header__sub {
  margin: 2px 0 0;
  font-size: 12.5px;
}

.cat-search {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider-strong);
  border-radius: var(--radius-md);
  padding: 0 14px;
  height: 44px;
  margin-bottom: 14px;
  max-width: 520px;
}

.cat-search:focus-within {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(10, 102, 245, 0.14);
}

.cat-search__icon {
  color: var(--color-neutral-400);
  flex-shrink: 0;
}

.cat-search__input {
  flex: 1;
  min-width: 0;
  background: transparent;
  border: none;
  outline: none;
  font-size: 14px;
  color: var(--color-neutral-200);
}

.cat-search__input::placeholder {
  color: var(--color-neutral-500);
}

.cat-search__count {
  font-size: 12px;
  color: var(--color-neutral-400);
  white-space: nowrap;
}

.cat-list {
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

.cat-row {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 52px;
  padding: 6px 10px 6px 14px;
  border-bottom: 1px solid var(--color-divider);
  transition: background 0.12s ease;
}

.cat-row:last-child {
  border-bottom: none;
}

.cat-row:hover {
  background: var(--color-neutral-800);
}

.cat-row--root {
  background: color-mix(in srgb, var(--color-primary) 4%, var(--color-neutral-900));
}

.cat-row--match {
  background: color-mix(in srgb, var(--color-primary) 10%, var(--color-neutral-900));
}

/* Petit trait vertical qui relie une sous-catégorie à son niveau parent. */
.cat-row__branch {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 1px;
  background: var(--color-divider-strong);
}

.cat-row__icon {
  flex-shrink: 0;
  color: var(--color-primary);
}

.cat-row__main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.cat-row__name {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-neutral-200);
  overflow-wrap: anywhere;
}

.cat-row:not(.cat-row--root) .cat-row__name {
  font-weight: 500;
}

.cat-row__badge {
  font-size: 11px;
  color: var(--color-neutral-400);
  background: var(--color-neutral-700);
  border-radius: 999px;
  padding: 2px 8px;
  white-space: nowrap;
}

.cat-row__actions {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
}

.cat-warning {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  font-size: 13px;
  color: var(--color-error);
  background: color-mix(in srgb, var(--color-error) 9%, transparent);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
}
</style>
