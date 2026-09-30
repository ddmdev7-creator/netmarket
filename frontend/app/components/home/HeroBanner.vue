<script setup lang="ts">
import { PhHandCoins, PhMapPinArea, PhSealCheck } from '@phosphor-icons/vue'

// Arguments de confiance plutôt que des promotions : c'est ce qui manque
// le plus à un visiteur qui découvre la plateforme (payer, récupérer, à qui
// il achète).
const slides = [
  {
    icon: PhHandCoins,
    title: 'Paiement 100 % sécurisé',
    text: 'Mobile money, carte ou solde NdjouriBank — remboursé si vous annulez.',
    from: '#0a66f5',
    to: '#4f46e5',
  },
  {
    icon: PhMapPinArea,
    title: 'Livré chez vous ou en point de retrait',
    text: 'Suivez votre colis en temps réel jusqu’à la remise.',
    from: '#0e9f6e',
    to: '#0a7c86',
  },
  {
    icon: PhSealCheck,
    title: 'Des vendeurs vérifiés',
    text: 'Chaque boutique est validée par Ndjouri avant de vendre.',
    from: '#e0822e',
    to: '#d9480f',
  },
]

const trackRef = ref<HTMLElement | null>(null)
const active = ref(0)
let timer: ReturnType<typeof setInterval> | undefined
let observer: IntersectionObserver | null = null

function goTo(index: number) {
  const track = trackRef.value
  if (!track) return
  track.scrollTo({ left: index * track.clientWidth, behavior: 'smooth' })
}

function startAutoplay() {
  stopAutoplay()
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  timer = setInterval(() => goTo((active.value + 1) % slides.length), 5000)
}

function stopAutoplay() {
  if (timer) clearInterval(timer)
}

onMounted(() => {
  const track = trackRef.value
  if (!track) return
  observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) active.value = Number((entry.target as HTMLElement).dataset.index)
      }
    },
    { root: track, threshold: 0.6 },
  )
  for (const el of Array.from(track.children)) observer.observe(el)
  startAutoplay()
})

onBeforeUnmount(() => {
  stopAutoplay()
  observer?.disconnect()
})
</script>

<template>
  <section class="hero" aria-label="Pourquoi NdjouriMarket" @pointerdown="stopAutoplay" @pointerup="startAutoplay">
    <div ref="trackRef" class="hero__track">
      <div
        v-for="(slide, i) in slides"
        :key="slide.title"
        :data-index="i"
        class="hero__slide"
        :style="{ background: `linear-gradient(120deg, ${slide.from}, ${slide.to})` }"
      >
        <div class="hero__text">
          <h2 class="hero__title">{{ slide.title }}</h2>
          <p class="hero__sub">{{ slide.text }}</p>
        </div>
        <component :is="slide.icon" class="hero__icon" :size="64" weight="duotone" />
      </div>
    </div>
    <div class="hero__dots">
      <button
        v-for="(slide, i) in slides"
        :key="slide.title"
        type="button"
        class="hero__dot"
        :class="{ 'hero__dot--active': active === i }"
        :aria-label="`Voir : ${slide.title}`"
        @click="goTo(i)"
      />
    </div>
  </section>
</template>

<style scoped>
.hero {
  position: relative;
}

.hero__track {
  display: flex;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  scrollbar-width: none;
  border-radius: var(--radius-lg);
}

.hero__track::-webkit-scrollbar {
  display: none;
}

.hero__slide {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 0 0 100%;
  min-height: 118px;
  padding: 18px 20px 26px;
  scroll-snap-align: start;
  color: #fff;
  overflow: hidden;
}

/* Halo décoratif : donne du relief au dégradé sans image à charger. */
.hero__slide::after {
  content: '';
  position: absolute;
  right: -40px;
  top: -50px;
  width: 180px;
  height: 180px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.12);
}

.hero__text {
  flex: 1;
  min-width: 0;
  z-index: 1;
}

.hero__title {
  font-family: var(--font-heading);
  font-size: 18px;
  font-weight: 800;
  line-height: 1.2;
  margin: 0 0 6px;
}

.hero__sub {
  font-size: 13px;
  line-height: 1.4;
  opacity: 0.92;
  margin: 0;
}

.hero__icon {
  flex-shrink: 0;
  z-index: 1;
  opacity: 0.95;
}

.hero__dots {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 9px;
  display: flex;
  justify-content: center;
  gap: 6px;
}

.hero__dot {
  width: 7px;
  height: 7px;
  padding: 0;
  border: 0;
  /* Zone de toucher plus large que le point visible. */
  box-sizing: content-box;
  background-clip: content-box !important;
  border: 8px solid transparent;
  margin: -8px -4px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.5);
  cursor: pointer;
  transition: width 0.2s ease, background 0.2s ease;
}

.hero__dot--active {
  width: 20px;
  background: #fff;
}

@media (min-width: 960px) {
  .hero__slide {
    min-height: 150px;
    padding: 26px 40px 30px;
  }

  .hero__title {
    font-size: 24px;
  }

  .hero__sub {
    font-size: 15px;
  }
}
</style>
