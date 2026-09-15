<script setup lang="ts">
import { PhShareFat, PhX } from '@phosphor-icons/vue'

// iOS Safari never fires `beforeinstallprompt` and never shows an install
// banner on its own (Apple doesn't implement that API) — the only path is
// Share → "Sur l'écran d'accueil", which most users never discover on their
// own. This nudges them toward it instead of leaving the feature invisible.
const DISMISS_KEY = 'ios-install-banner-dismissed-at'
const RESHOW_AFTER_DAYS = 14

const show = ref(false)

onMounted(() => {
  const isIOS =
    /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    // iPadOS 13+ reports as "MacIntel" in the UA string; touch points is what
    // actually distinguishes it from a real Mac.
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
  // `standalone` is an iOS-only, non-standard Navigator property (absent
  // from lib.dom's types) — true once launched from an already-installed
  // home screen icon.
  const isStandalone = (window.navigator as { standalone?: boolean }).standalone === true
  if (!isIOS || isStandalone) return

  const dismissedAt = localStorage.getItem(DISMISS_KEY)
  if (dismissedAt && Date.now() - Number(dismissedAt) < RESHOW_AFTER_DAYS * 24 * 60 * 60 * 1000) return

  show.value = true
})

function dismiss() {
  show.value = false
  localStorage.setItem(DISMISS_KEY, String(Date.now()))
}
</script>

<template>
  <div v-if="show" class="ios-install-banner">
    <PhShareFat :size="22" color="var(--color-primary)" />
    <p>
      Installez l'app : appuyez sur <strong>Partager</strong> puis
      « <strong>Sur l'écran d'accueil</strong> »
    </p>
    <button class="ios-install-banner__close" aria-label="Fermer" @click="dismiss">
      <PhX :size="16" />
    </button>
  </div>
</template>

<style scoped>
.ios-install-banner {
  position: fixed;
  bottom: calc(64px + env(safe-area-inset-bottom, 0px));
  left: 50%;
  transform: translateX(-50%);
  width: calc(100% - 24px);
  max-width: 456px;
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider-strong);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  padding: 12px 12px 12px 14px;
  z-index: 15;
}

.ios-install-banner p {
  flex: 1;
  margin: 0;
  font-size: 13px;
  line-height: 1.4;
  color: var(--color-neutral-200);
}

.ios-install-banner__close {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  color: var(--color-neutral-400);
  background: transparent;
  border: none;
  cursor: pointer;
}
</style>
