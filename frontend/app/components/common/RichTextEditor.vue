<script setup lang="ts">
import { PhListBullets, PhListNumbers, PhTextBolder, PhTextItalic } from '@phosphor-icons/vue'

/**
 * Mini éditeur riche (gras, italique, liste à puces, liste numérotée) pour
 * la description produit — v-model en HTML. Basé sur contenteditable +
 * document.execCommand plutôt qu'une lib type Tiptap : formellement
 * dépréciée mais toujours largement supportée pour ce sous-ensemble de
 * commandes basiques, et évite d'ajouter une dépendance npm dans un
 * environnement où on ne peut pas vérifier le build en local (voir
 * CLAUDE.md / historique du projet). Le HTML produit ici n'est jamais la
 * seule ligne de défense contre l'injection : le backend réassainit tout
 * (voir app/catalog/service.py::_sanitize_description) quelle que soit la
 * source de la requête.
 */
const model = defineModel<string>({ required: true })

const editorEl = ref<HTMLElement | null>(null)
const focused = ref(false)

const activeFormats = reactive({
  bold: false,
  italic: false,
  insertUnorderedList: false,
  insertOrderedList: false,
})

function updateActiveFormats() {
  if (!document.queryCommandSupported) return
  activeFormats.bold = document.queryCommandState('bold')
  activeFormats.italic = document.queryCommandState('italic')
  activeFormats.insertUnorderedList = document.queryCommandState('insertUnorderedList')
  activeFormats.insertOrderedList = document.queryCommandState('insertOrderedList')
}

function onInput() {
  model.value = editorEl.value?.innerHTML ?? ''
}

// mousedown.prevent (pas click) : sans ça, cliquer un bouton de la barre
// d'outils fait perdre le focus/la sélection dans la zone éditable avant
// que le clic ne parte, et execCommand n'a alors plus rien à mettre en
// forme.
function exec(command: string) {
  document.execCommand(command, false)
  editorEl.value?.focus()
  onInput()
  updateActiveFormats()
}

function onFocus() {
  focused.value = true
  updateActiveFormats()
}

onMounted(() => {
  if (editorEl.value) editorEl.value.innerHTML = model.value || ''
})

// Resynchronise le contenu affiché si le v-model change depuis l'extérieur
// (ex: rechargement du formulaire en mode édition une fois le produit
// chargé) — jamais pendant la frappe (onInput met déjà model à jour), sinon
// le curseur sauterait au début de la zone à chaque caractère saisi.
watch(model, (value) => {
  if (editorEl.value && value !== editorEl.value.innerHTML) {
    editorEl.value.innerHTML = value || ''
  }
})
</script>

<template>
  <div class="rte" :class="{ 'rte--focused': focused }">
    <div class="rte__toolbar">
      <button
        type="button"
        class="rte__btn"
        :class="{ 'rte__btn--active': activeFormats.bold }"
        aria-label="Gras"
        title="Gras"
        @mousedown.prevent="exec('bold')"
      >
        <PhTextBolder :size="16" weight="bold" />
      </button>
      <button
        type="button"
        class="rte__btn"
        :class="{ 'rte__btn--active': activeFormats.italic }"
        aria-label="Italique"
        title="Italique"
        @mousedown.prevent="exec('italic')"
      >
        <PhTextItalic :size="16" />
      </button>
      <span class="rte__sep" />
      <button
        type="button"
        class="rte__btn"
        :class="{ 'rte__btn--active': activeFormats.insertUnorderedList }"
        aria-label="Liste à puces"
        title="Liste à puces"
        @mousedown.prevent="exec('insertUnorderedList')"
      >
        <PhListBullets :size="16" />
      </button>
      <button
        type="button"
        class="rte__btn"
        :class="{ 'rte__btn--active': activeFormats.insertOrderedList }"
        aria-label="Liste numérotée"
        title="Liste numérotée"
        @mousedown.prevent="exec('insertOrderedList')"
      >
        <PhListNumbers :size="16" />
      </button>
    </div>
    <div
      ref="editorEl"
      class="rte__content"
      contenteditable="true"
      data-placeholder="Décris ton produit…"
      @input="onInput"
      @keyup="updateActiveFormats"
      @mouseup="updateActiveFormats"
      @focus="onFocus"
      @blur="focused = false"
    />
  </div>
</template>

<style scoped>
.rte {
  border: 1px solid var(--color-divider-strong);
  border-radius: var(--radius-sm);
  overflow: hidden;
  transition: border-color 0.15s ease;
}

.rte--focused {
  border-color: var(--color-primary);
}

.rte__toolbar {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 6px 8px;
  background: var(--color-neutral-800);
  border-bottom: 1px solid var(--color-divider);
}

.rte__sep {
  width: 1px;
  height: 18px;
  background: var(--color-divider-strong);
  margin: 0 4px;
  flex-shrink: 0;
}

.rte__btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: var(--radius-sm);
  background: none;
  color: var(--color-neutral-400);
  cursor: pointer;
  transition: color 0.15s ease, background 0.15s ease;
}

.rte__btn:hover {
  color: var(--color-neutral-200);
  background: var(--color-neutral-700);
}

.rte__btn--active {
  color: var(--color-primary);
  background: var(--color-primary-100);
}

.rte__content {
  min-height: 120px;
  padding: 10px 12px;
  font-size: 14px;
  line-height: 1.5;
  color: var(--color-neutral-200);
  outline: none;
}

.rte__content :deep(p) {
  margin: 0 0 8px;
}

.rte__content :deep(ul),
.rte__content :deep(ol) {
  margin: 0 0 8px;
  padding-left: 22px;
}

.rte__content:empty::before {
  content: attr(data-placeholder);
  color: var(--color-neutral-500);
}
</style>
