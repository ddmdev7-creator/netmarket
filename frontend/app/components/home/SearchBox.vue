<script setup lang="ts">
import {
  PhArrowUpLeft,
  PhClockCounterClockwise,
  PhImage,
  PhMagnifyingGlass,
  PhStorefront,
  PhX,
} from '@phosphor-icons/vue'
import type { CategoryRead, SearchSuggestions } from '~/types/api'

/**
 * Barre de recherche de l'accueil avec panneau de suggestions : recherches
 * récentes et catégories à vide, puis catégories / boutiques / produits qui
 * correspondent pendant la frappe (GET /products/suggest). La liste de la
 * page n'est relancée qu'à la validation (Entrée ou choix d'une suggestion).
 */
const props = defineProps<{ categories: CategoryRead[] }>()
const model = defineModel<string>({ required: true })
const emit = defineEmits<{
  submit: [q: string]
  category: [id: string]
  shop: [shop: { id: string; name: string }]
}>()

const { apiFetch } = useApi()
const apiBase = useApiBase()

const RECENT_KEY = 'nm-recent-searches'
const RECENT_MAX = 8

const open = ref(false)
const suggestions = ref<SearchSuggestions | null>(null)
const loading = ref(false)
const activeIndex = ref(-1)
const recent = ref<string[]>([])
const rootRef = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLInputElement | null>(null)

const term = computed(() => model.value.trim())
const rootCategories = computed(() => props.categories.filter((c) => c.parent_id === null).slice(0, 8))

function readRecent() {
  try {
    const parsed = JSON.parse(localStorage.getItem(RECENT_KEY) ?? '[]')
    recent.value = Array.isArray(parsed) ? parsed.filter((v) => typeof v === 'string').slice(0, RECENT_MAX) : []
  } catch {
    recent.value = []
  }
}

function writeRecent() {
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(recent.value))
  } catch {
    // Stockage indisponible : l'historique reste en mémoire pour la session.
  }
}

function remember(q: string) {
  const value = q.trim()
  if (value.length < 2) return
  recent.value = [value, ...recent.value.filter((r) => r.toLowerCase() !== value.toLowerCase())].slice(0, RECENT_MAX)
  writeRecent()
}

function forget(q: string) {
  recent.value = recent.value.filter((r) => r !== q)
  writeRecent()
}

function clearRecent() {
  recent.value = []
  writeRecent()
}

// --- Suggestions pendant la frappe ------------------------------------------

let timer: ReturnType<typeof setTimeout> | undefined
let requestId = 0

watch(term, (value) => {
  activeIndex.value = -1
  clearTimeout(timer)
  if (value.length < 2) {
    suggestions.value = null
    loading.value = false
    return
  }
  loading.value = true
  timer = setTimeout(async () => {
    const id = ++requestId
    try {
      const result = await apiFetch<SearchSuggestions>('/products/suggest', { query: { q: value } })
      if (id === requestId) suggestions.value = result
    } catch {
      if (id === requestId) suggestions.value = null
    } finally {
      if (id === requestId) loading.value = false
    }
  }, 200)
})

// Liste à plat des lignes sélectionnables au clavier, dans l'ordre d'affichage.
type Row =
  | { kind: 'search'; q: string }
  | { kind: 'recent'; q: string }
  | { kind: 'category'; category: CategoryRead }
  | { kind: 'shop'; id: string; name: string; count: number }
  | { kind: 'product'; id: string; name: string; price: number; image: string | null }

const rows = computed<Row[]>(() => {
  if (term.value.length < 2) return recent.value.map((q) => ({ kind: 'recent', q }))
  const s = suggestions.value
  const list: Row[] = [{ kind: 'search', q: term.value }]
  if (!s) return list
  list.push(...s.categories.map((category) => ({ kind: 'category' as const, category })))
  list.push(...s.shops.map((shop) => ({ kind: 'shop' as const, id: shop.id, name: shop.shop_name, count: shop.product_count })))
  list.push(...s.products.map((p) => ({ kind: 'product' as const, ...p })))
  return list
})

const hasMatches = computed(() => rows.value.some((r) => r.kind !== 'search'))

function rowIndex(row: Row) {
  return rows.value.indexOf(row)
}

function categoryPath(category: CategoryRead): string | null {
  const parent = props.categories.find((c) => c.id === category.parent_id)
  return parent ? parent.name : null
}

// Met en gras la partie tapée dans une suggestion (insensible aux accents).
function normalize(text: string) {
  return text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase()
}

function highlight(text: string): { text: string; match: boolean }[] {
  const words = normalize(term.value).split(/\s+/).filter(Boolean)
  if (!words.length) return [{ text, match: false }]
  // normalize() garde la même longueur que le texte d'origine pour les
  // lettres accentuées usuelles (é → e), donc les positions se correspondent.
  const plain = normalize(text)
  const marks = new Array(text.length).fill(false)
  for (const word of words) {
    let from = 0
    let at: number
    while ((at = plain.indexOf(word, from)) !== -1) {
      for (let i = at; i < at + word.length; i++) marks[i] = true
      from = at + word.length
    }
  }
  const parts: { text: string; match: boolean }[] = []
  for (let i = 0; i < text.length; i++) {
    const last = parts[parts.length - 1]
    if (last && last.match === marks[i]) last.text += text[i]
    else parts.push({ text: text[i]!, match: marks[i] })
  }
  return parts
}

// --- Actions ------------------------------------------------------------------

function close() {
  open.value = false
  activeIndex.value = -1
}

function submit(q = model.value) {
  model.value = q
  remember(q)
  close()
  inputRef.value?.blur()
  emit('submit', q.trim())
}

function choose(row: Row) {
  switch (row.kind) {
    case 'search':
    case 'recent':
      submit(row.q)
      break
    case 'category':
      remember(term.value)
      model.value = ''
      close()
      emit('category', row.category.id)
      break
    case 'shop':
      remember(term.value)
      model.value = ''
      close()
      emit('shop', { id: row.id, name: row.name })
      break
    case 'product':
      remember(term.value)
      close()
      navigateTo(`/produits/${row.id}`)
      break
  }
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    close()
    inputRef.value?.blur()
    return
  }
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    open.value = true
    const count = rows.value.length
    if (!count) return
    const step = event.key === 'ArrowDown' ? 1 : -1
    // -1 = retour dans le champ, entre la dernière et la première ligne.
    const next = activeIndex.value + step
    activeIndex.value = next >= count ? -1 : next < -1 ? count - 1 : next
    return
  }
  if (event.key === 'Enter') {
    event.preventDefault()
    const row = rows.value[activeIndex.value]
    if (row) choose(row)
    else submit()
  }
}

function clearInput() {
  model.value = ''
  suggestions.value = null
  emit('submit', '')
  inputRef.value?.focus()
}

function onDocumentPointer(event: PointerEvent) {
  if (open.value && rootRef.value && !rootRef.value.contains(event.target as Node)) close()
}

onMounted(() => {
  readRecent()
  document.addEventListener('pointerdown', onDocumentPointer)
})

onBeforeUnmount(() => {
  clearTimeout(timer)
  document.removeEventListener('pointerdown', onDocumentPointer)
})

defineExpose({ remember })
</script>

<template>
  <div ref="rootRef" class="sbox" :class="{ 'sbox--open': open }">
    <div class="sbox__field">
      <PhMagnifyingGlass :size="19" weight="bold" class="sbox__lens" />
      <input
        ref="inputRef"
        v-model="model"
        type="search"
        enterkeyhint="search"
        autocomplete="off"
        class="sbox__input"
        placeholder="Rechercher un produit, une marque, une boutique…"
        aria-label="Rechercher"
        role="combobox"
        aria-autocomplete="list"
        :aria-expanded="open"
        aria-controls="sbox-panel"
        @focus="open = true"
        @keydown="onKeydown"
      />
      <v-progress-circular v-if="loading" indeterminate size="16" width="2" color="primary" class="mr-1" />
      <button v-if="model" type="button" class="sbox__clear" aria-label="Effacer la recherche" @click="clearInput">
        <PhX :size="14" weight="bold" />
      </button>
    </div>

    <transition name="sbox-pop">
      <div v-if="open" id="sbox-panel" class="sbox__panel" role="listbox">
        <!-- Champ vide : historique + catégories -->
        <template v-if="term.length < 2">
          <div v-if="recent.length" class="sbox__section">
            <div class="sbox__section-head">
              <span>Recherches récentes</span>
              <button type="button" class="sbox__link" @click="clearRecent">Effacer</button>
            </div>
            <div
              v-for="row in rows"
              :key="`r-${row.kind === 'recent' ? row.q : ''}`"
              class="sbox__row"
              :class="{ 'sbox__row--active': rowIndex(row) === activeIndex }"
              role="option"
              @click="choose(row)"
            >
              <PhClockCounterClockwise :size="17" class="sbox__row-icon" />
              <span class="sbox__row-main"><span>{{ row.kind === 'recent' ? row.q : '' }}</span></span>
              <button
                type="button"
                class="sbox__row-remove"
                aria-label="Retirer de l'historique"
                @click.stop="row.kind === 'recent' && forget(row.q)"
              >
                <PhX :size="13" />
              </button>
            </div>
          </div>
          <div v-if="rootCategories.length" class="sbox__section">
            <div class="sbox__section-head"><span>Explorer les catégories</span></div>
            <div class="sbox__cats">
              <button
                v-for="category in rootCategories"
                :key="category.id"
                type="button"
                class="sbox__cat"
                :style="{ '--hue': categoryIcon(category).hue }"
                @click="choose({ kind: 'category', category })"
              >
                <component :is="categoryIcon(category).icon" :size="15" weight="duotone" />
                {{ category.name }}
              </button>
            </div>
          </div>
          <p v-if="!recent.length && !rootCategories.length" class="sbox__hint">
            Tape au moins 2 lettres pour voir des suggestions.
          </p>
        </template>

        <!-- Pendant la frappe -->
        <template v-else>
          <template v-for="row in rows" :key="row.kind + ('id' in row ? row.id : row.kind === 'category' ? row.category.id : '')">
            <div
              class="sbox__row"
              :class="{ 'sbox__row--active': rowIndex(row) === activeIndex, 'sbox__row--search': row.kind === 'search' }"
              role="option"
              :aria-selected="rowIndex(row) === activeIndex"
              @mouseenter="activeIndex = rowIndex(row)"
              @click="choose(row)"
            >
              <template v-if="row.kind === 'search'">
                <PhMagnifyingGlass :size="17" class="sbox__row-icon" />
                <span class="sbox__row-main"><span>Rechercher « <strong>{{ row.q }}</strong> »</span></span>
                <PhArrowUpLeft :size="15" class="sbox__row-go" />
              </template>

              <template v-else-if="row.kind === 'category'">
                <span class="sbox__bubble" :style="{ '--hue': categoryIcon(row.category).hue }">
                  <component :is="categoryIcon(row.category).icon" :size="16" weight="duotone" />
                </span>
                <span class="sbox__row-main">
                  <span><template v-for="(part, i) in highlight(row.category.name)" :key="i"><mark v-if="part.match">{{ part.text }}</mark><template v-else>{{ part.text }}</template></template></span>
                  <small>Catégorie{{ categoryPath(row.category) ? ` · ${categoryPath(row.category)}` : '' }}</small>
                </span>
              </template>

              <template v-else-if="row.kind === 'shop'">
                <span class="sbox__bubble" :style="{ '--hue': 200 }"><PhStorefront :size="16" weight="duotone" /></span>
                <span class="sbox__row-main">
                  <span><template v-for="(part, i) in highlight(row.name)" :key="i"><mark v-if="part.match">{{ part.text }}</mark><template v-else>{{ part.text }}</template></template></span>
                  <small>Boutique · {{ row.count }} produit{{ row.count > 1 ? 's' : '' }}</small>
                </span>
              </template>

              <template v-else-if="row.kind === 'product'">
                <span class="sbox__thumb">
                  <img v-if="row.image" :src="resolveImageUrl(row.image, apiBase)" alt="" loading="lazy" />
                  <PhImage v-else :size="16" />
                </span>
                <span class="sbox__row-main">
                  <span><template v-for="(part, i) in highlight(row.name)" :key="i"><mark v-if="part.match">{{ part.text }}</mark><template v-else>{{ part.text }}</template></template></span>
                  <small class="sbox__price">{{ formatGnf(row.price) }}</small>
                </span>
              </template>
            </div>
          </template>

          <div v-if="!loading && suggestions && !hasMatches" class="sbox__none">
            <template v-if="suggestions.did_you_mean">
              Vouliez-vous dire
              <button type="button" class="sbox__link" @click="submit(suggestions.did_you_mean)">
                {{ suggestions.did_you_mean }}
              </button>
              ?
            </template>
            <template v-else>Aucune suggestion — valide pour chercher quand même.</template>
          </div>
        </template>
      </div>
    </transition>
    <div v-if="open" class="sbox__backdrop" @click="close" />
  </div>
</template>

<style scoped>
.sbox {
  position: relative;
  flex: 1;
  min-width: 0;
}

.sbox--open {
  z-index: 30;
}

.sbox__field {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 8px;
  height: 46px;
  padding: 0 10px 0 14px;
  border-radius: 999px;
  border: 1.5px solid transparent;
  background: var(--color-neutral-900);
  box-shadow: var(--shadow-sm);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.sbox--open .sbox__field {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-100);
}

.sbox__lens {
  flex-shrink: 0;
  color: var(--color-primary);
}

.sbox__input {
  flex: 1;
  min-width: 0;
  height: 100%;
  border: 0;
  outline: none;
  background: none;
  color: var(--color-neutral-200);
  font-size: 14.5px;
}

.sbox__input::placeholder {
  color: var(--color-neutral-500);
}

.sbox__input::-webkit-search-cancel-button {
  display: none;
}

.sbox__clear {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  flex-shrink: 0;
  border: 0;
  border-radius: 50%;
  background: var(--color-neutral-700);
  color: var(--color-neutral-300);
  cursor: pointer;
}

.sbox__panel {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  right: 0;
  z-index: 2;
  max-height: min(70vh, 520px);
  overflow-y: auto;
  padding: 6px;
  border-radius: var(--radius-lg);
  background: var(--color-neutral-900);
  box-shadow: var(--shadow-lg);
  border: 1px solid var(--color-divider);
}

/* Assombrit la page derrière le panneau (surtout utile sur téléphone, où il
   occupe presque tout l'écran) ; un clic dessus referme. */
.sbox__backdrop {
  position: fixed;
  inset: 0;
  z-index: 1;
  background: rgba(10, 12, 20, 0.28);
}

.sbox__section + .sbox__section {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px solid var(--color-divider);
}

.sbox__section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px 4px;
  font-size: 11.5px;
  font-weight: 700;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: var(--color-neutral-500);
}

.sbox__link {
  border: 0;
  background: none;
  padding: 0 2px;
  color: var(--color-primary-300);
  font-weight: 700;
  font-size: inherit;
  text-transform: none;
  letter-spacing: 0;
  cursor: pointer;
}

.sbox__row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 46px;
  padding: 6px 10px;
  border-radius: var(--radius-md);
  cursor: pointer;
  color: var(--color-neutral-300);
}

.sbox__row--active,
.sbox__row:hover {
  background: var(--color-neutral-800);
}

.sbox__row--search {
  color: var(--color-primary-300);
}

.sbox__row-icon {
  flex-shrink: 0;
  color: var(--color-neutral-500);
}

.sbox__row--search .sbox__row-icon {
  color: var(--color-primary);
}

.sbox__row-main {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  font-size: 14px;
  line-height: 1.3;
}

.sbox__row-main > span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sbox__row-main small {
  font-size: 12px;
  color: var(--color-neutral-500);
}

.sbox__row-main mark {
  background: none;
  color: var(--color-neutral-200);
  font-weight: 800;
}

.sbox__price {
  color: var(--color-accent) !important;
  font-weight: 700;
}

.sbox__row-go {
  flex-shrink: 0;
  color: var(--color-neutral-500);
}

.sbox__row-remove {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: 50%;
  background: none;
  color: var(--color-neutral-500);
  cursor: pointer;
}

.sbox__row-remove:hover {
  background: var(--color-neutral-700);
}

.sbox__bubble {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  border-radius: 50%;
  background: hsl(var(--hue) 70% var(--tint-bg));
  color: hsl(var(--hue) 60% var(--tint-fg));
}

.sbox__thumb {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  flex-shrink: 0;
  overflow: hidden;
  border-radius: var(--radius-sm);
  background: #fff;
  border: 1px solid var(--color-divider);
  color: var(--color-neutral-500);
}

.sbox__thumb img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.sbox__cats {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 4px 10px 10px;
}

.sbox__cat {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 0;
  border-radius: 999px;
  background: hsl(var(--hue) 70% var(--tint-bg));
  color: hsl(var(--hue) 60% var(--tint-fg));
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.sbox__none,
.sbox__hint {
  padding: 10px 12px 12px;
  font-size: 13px;
  color: var(--color-neutral-400);
  margin: 0;
}

.sbox-pop-enter-active,
.sbox-pop-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.sbox-pop-enter-from,
.sbox-pop-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
