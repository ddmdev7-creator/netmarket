<script setup lang="ts">
import { PhCaretLeft, PhCaretRight, PhImage, PhX } from '@phosphor-icons/vue'

const props = defineProps<{ images: string[]; alt: string }>()

const apiBase = useApiBase()
const resolvedImages = computed(() => props.images.map((v) => resolveImageUrl(v, apiBase)))

const scrollerEl = ref<HTMLElement | null>(null)
const activeIndex = ref(0)

function onScroll() {
  const el = scrollerEl.value
  if (!el || el.clientWidth === 0) return
  activeIndex.value = Math.round(el.scrollLeft / el.clientWidth)
}

function scrollTo(index: number) {
  scrollerEl.value?.scrollTo({ left: index * scrollerEl.value.clientWidth, behavior: 'smooth' })
}

// Changement de variante (autre jeu de photos) : on repart de la 1re photo
// plutôt que de rester sur un index qui n'a plus de sens.
watch(
  () => props.images,
  () => {
    activeIndex.value = 0
    scrollerEl.value?.scrollTo({ left: 0 })
  },
)

function prev() {
  if (activeIndex.value > 0) scrollTo(activeIndex.value - 1)
}
function next() {
  if (activeIndex.value < resolvedImages.value.length - 1) scrollTo(activeIndex.value + 1)
}

// Visionneuse plein écran : même liste d'images, image de départ = celle
// affichée dans la bande au moment du tap — pas de recroping ici
// (object-fit: contain), l'image se voit toujours en entier.
const lightboxOpen = ref(false)
const lightboxIndex = ref(0)
const lightboxScrollerEl = ref<HTMLElement | null>(null)

function openLightbox(index: number) {
  lightboxIndex.value = index
  lightboxOpen.value = true
  // La barre plein écran doit démarrer pile sur l'image tapée — impossible
  // avant que le v-if l'ait montée, d'où le nextTick.
  nextTick(() => {
    lightboxScrollerEl.value?.scrollTo({ left: index * lightboxScrollerEl.value.clientWidth })
  })
}

function onLightboxScroll() {
  const el = lightboxScrollerEl.value
  if (!el || el.clientWidth === 0) return
  lightboxIndex.value = Math.round(el.scrollLeft / el.clientWidth)
}

function lightboxScrollTo(index: number) {
  lightboxScrollerEl.value?.scrollTo({ left: index * lightboxScrollerEl.value.clientWidth, behavior: 'smooth' })
}
function lightboxPrev() {
  if (lightboxIndex.value > 0) lightboxScrollTo(lightboxIndex.value - 1)
}
function lightboxNext() {
  if (lightboxIndex.value < resolvedImages.value.length - 1) lightboxScrollTo(lightboxIndex.value + 1)
}
</script>

<template>
  <div class="gallery">
    <div v-if="images.length === 0" class="gallery__empty">
      <PhImage :size="40" weight="light" color="var(--color-neutral-500)" />
    </div>
    <template v-else>
      <div ref="scrollerEl" class="gallery__scroller" @scroll="onScroll">
        <button
          v-for="(src, i) in resolvedImages"
          :key="src + i"
          type="button"
          class="gallery__slide"
          :style="{ '--bg-src': `url('${src}')` }"
          :aria-label="`Agrandir la photo ${i + 1}`"
          @click="openLightbox(i)"
        >
          <div class="gallery__backdrop" />
          <img :src="src" :alt="`${alt} — photo ${i + 1}`" class="gallery__image" />
        </button>
      </div>
      <template v-if="images.length > 1">
        <button
          type="button"
          class="gallery__nav gallery__nav--prev"
          aria-label="Photo précédente"
          :disabled="activeIndex === 0"
          @click="prev"
        >
          <PhCaretLeft :size="16" weight="bold" />
        </button>
        <button
          type="button"
          class="gallery__nav gallery__nav--next"
          aria-label="Photo suivante"
          :disabled="activeIndex === resolvedImages.length - 1"
          @click="next"
        >
          <PhCaretRight :size="16" weight="bold" />
        </button>

        <div class="gallery__dots">
          <button
            v-for="(src, i) in images"
            :key="src + i"
            type="button"
            class="gallery__dot"
            :class="{ 'gallery__dot--active': i === activeIndex }"
            :aria-label="`Photo ${i + 1}`"
            @click="scrollTo(i)"
          />
        </div>
      </template>
    </template>
  </div>

  <Teleport to="body">
    <div v-if="lightboxOpen" class="lightbox" @click.self="lightboxOpen = false">
      <button type="button" class="lightbox__close" aria-label="Fermer" @click="lightboxOpen = false">
        <PhX :size="20" />
      </button>
      <div v-if="images.length > 1" class="lightbox__counter">{{ lightboxIndex + 1 }} / {{ images.length }}</div>

      <template v-if="images.length > 1">
        <button
          type="button"
          class="lightbox__nav lightbox__nav--prev"
          aria-label="Photo précédente"
          :disabled="lightboxIndex === 0"
          @click="lightboxPrev"
        >
          <PhCaretLeft :size="22" weight="bold" />
        </button>
        <button
          type="button"
          class="lightbox__nav lightbox__nav--next"
          aria-label="Photo suivante"
          :disabled="lightboxIndex === resolvedImages.length - 1"
          @click="lightboxNext"
        >
          <PhCaretRight :size="22" weight="bold" />
        </button>
      </template>

      <div ref="lightboxScrollerEl" class="lightbox__scroller" @scroll="onLightboxScroll">
        <div v-for="(src, i) in resolvedImages" :key="src + i" class="lightbox__slide">
          <img :src="src" :alt="`${alt} — photo ${i + 1}`" class="lightbox__image" />
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.gallery {
  position: relative;
  height: 280px;
  border-radius: var(--radius-lg);
  background: var(--color-neutral-800);
  overflow: hidden;
  margin-top: 8px;
}

/* Fiche produit en deux colonnes sur desktop (voir pages/produits/[id].vue)
   : la galerie prend toute la hauteur de sa colonne plutôt que de rester
   figée à la hauteur pensée pour un écran de téléphone. */
@media (min-width: 960px) {
  .gallery {
    height: 460px;
  }
}

.gallery__empty {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.gallery__scroller {
  height: 100%;
  display: flex;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
}

.gallery__scroller::-webkit-scrollbar {
  display: none;
}

.gallery__slide {
  position: relative;
  flex: 0 0 100%;
  width: 100%;
  height: 100%;
  scroll-snap-align: start;
  border: none;
  padding: 0;
  background: none;
  overflow: hidden;
  cursor: zoom-in;
}

/* Remplit toute la carte avec une version floutée/assombrie de la même
   photo, agrandie légèrement pour que le flou ne laisse pas voir ses bords —
   évite les bandes vides d'un simple "contain" tout en gardant la photo
   nette (ci-dessous) entièrement visible, jamais recadrée. */
.gallery__backdrop {
  position: absolute;
  inset: 0;
  background-image: var(--bg-src);
  background-size: cover;
  background-position: center;
  filter: blur(22px) brightness(0.55);
  transform: scale(1.15);
}

.gallery__image {
  position: relative;
  width: 100%;
  height: 100%;
  object-fit: contain;
}

/* Flèches précédent/suivant, centrées verticalement sur les bords gauche/
   droit — le pattern carrousel classique, en complément des points en bas
   (voir .gallery__dots) et du swipe déjà possible sur .gallery__scroller. */
.gallery__nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  z-index: 2;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.35);
  color: #fff;
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.15s ease, opacity 0.15s ease;
}

.gallery__nav:hover {
  background: rgba(0, 0, 0, 0.55);
}

.gallery__nav:disabled {
  opacity: 0.3;
  cursor: default;
  pointer-events: none;
}

.gallery__nav--prev {
  left: 10px;
}

.gallery__nav--next {
  right: 10px;
}

.gallery__dots {
  position: absolute;
  bottom: 10px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 2;
  display: flex;
  gap: 7px;
  padding: 6px 10px;
  border-radius: 999px;
  /* Quasi opaque (0.6 puis 0.35 se sont révélés encore trop transparents
     sur une photo produit à fond clair, très courant en e-commerce — un
     fond clair sous une pastille semi-transparente noircit à peine et les
     points s'y distinguent mal). 0.8 + un liseré clair donnent un contraste
     fiable quelle que soit la photo derrière. */
  background: rgba(0, 0, 0, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.15);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.3);
}

.gallery__dot {
  /* Visible dot stays 7px (background-clip: content-box keeps the padding
     transparent) — the padding itself is what brings the actual tap target
     up to a reasonable mobile size without changing how this looks. */
  width: 7px;
  height: 7px;
  padding: 8px;
  background-clip: content-box;
  border-radius: 50%;
  /* Blanc plein plutôt que semi-transparent : sur un fond de pastille déjà
     à 80% opaque, un point net se distingue toujours de l'actif ci-dessous
     sans dépendre en plus de la photo affichée. */
  background-color: #fff;
  opacity: 0.55;
  border: none;
  outline: none;
  cursor: pointer;
  /* Sans ça, le chrome natif d'un <button> (surtout Safari iOS) peut
     redessiner sa propre apparence par-dessus background-color/border-radius
     une fois le bouton assez petit — les deux précédents ajustements
     d'opacité (0.35 → 0.6 → 0.8 sur la pastille) ne changeaient rien
     puisque le point restait masqué par ce rendu natif, pas par un manque
     de contraste. */
  appearance: none;
  -webkit-appearance: none;
  transition:
    opacity 0.15s ease,
    background-color 0.15s ease,
    width 0.15s ease;
}

.gallery__dot--active {
  background-color: var(--color-primary);
  opacity: 1;
  width: 18px;
  border-radius: 3px;
}
</style>

<style scoped>
.lightbox {
  position: fixed;
  inset: 0;
  z-index: 100;
  background: rgba(0, 0, 0, 0.92);
  display: flex;
  align-items: center;
}

.lightbox__scroller {
  width: 100%;
  height: 100%;
  display: flex;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
}

.lightbox__scroller::-webkit-scrollbar {
  display: none;
}

.lightbox__slide {
  flex: 0 0 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  scroll-snap-align: start;
}

.lightbox__image {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.lightbox__close {
  position: absolute;
  top: calc(12px + env(safe-area-inset-top, 0px));
  right: 12px;
  z-index: 1;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.lightbox__counter {
  position: absolute;
  top: calc(18px + env(safe-area-inset-top, 0px));
  left: 50%;
  transform: translateX(-50%);
  z-index: 1;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.8);
  background: rgba(255, 255, 255, 0.12);
  padding: 3px 10px;
  border-radius: 999px;
}

.lightbox__nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  z-index: 1;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.15s ease, opacity 0.15s ease;
}

.lightbox__nav:hover {
  background: rgba(255, 255, 255, 0.22);
}

.lightbox__nav:disabled {
  opacity: 0.3;
  cursor: default;
  pointer-events: none;
}

.lightbox__nav--prev {
  left: 12px;
}

.lightbox__nav--next {
  right: 12px;
}
</style>
