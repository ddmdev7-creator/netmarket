<script setup lang="ts">
import { PhImage, PhX } from '@phosphor-icons/vue'

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
      <div v-if="images.length > 1" class="gallery__dots">
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
  </div>

  <Teleport to="body">
    <div v-if="lightboxOpen" class="lightbox" @click.self="lightboxOpen = false">
      <button type="button" class="lightbox__close" aria-label="Fermer" @click="lightboxOpen = false">
        <PhX :size="20" />
      </button>
      <div v-if="images.length > 1" class="lightbox__counter">{{ lightboxIndex + 1 }} / {{ images.length }}</div>

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

.gallery__dots {
  position: absolute;
  bottom: 10px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.35);
}

.gallery__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.5);
  border: none;
  padding: 0;
  cursor: pointer;
  transition:
    background 0.15s ease,
    width 0.15s ease;
}

.gallery__dot--active {
  background: var(--color-primary);
  width: 16px;
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
</style>
