<script setup lang="ts">
/**
 * Pages « focus » (fiche produit, commande, notifications, adresses…) : barre
 * du haut avec flèche de retour, sans barre de navigation du bas — ces pages
 * ont souvent leur propre barre d'action ancrée en bas (acheter, commander).
 * Réglages par page via definePageMeta({ topbar: { nav, cart } }).
 */
const route = useRoute()
const options = computed(() => {
  const meta = (route.meta.topbar ?? {}) as { back?: boolean; nav?: boolean; cart?: boolean }
  return { back: meta.back ?? true, nav: meta.nav ?? true, cart: meta.cart ?? true }
})
</script>

<template>
  <v-app>
    <v-main>
      <LayoutTopBar :back="options.back" :show-nav="options.nav" :show-cart="options.cart" />
      <slot />
    </v-main>
  </v-app>
</template>
