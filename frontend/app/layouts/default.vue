<script setup lang="ts">
const auth = useAuthStore()
const cartStore = useCartStore()
const route = useRoute()

onMounted(() => {
  if (auth.isAuthenticated) cartStore.fetchCart()
})
</script>

<template>
  <v-app>
    <v-main>
      <!-- app-shell--catalog (pas de plafond, voir main.css) pour les pages
           qui recentrent elles-mêmes leur contenu à l'intérieur (accueil :
           .home-page ; panier : .cart-inner ; profil : .profil-inner) --
           sans ça, LayoutTopBar (ici, dans ce même wrapper) resterait
           plafonné à 720px sur desktop même si la page elle-même s'étire,
           un bandeau du haut plus étroit que le contenu en dessous. -->
      <div
        class="app-shell buyer-shell"
        :class="{ 'app-shell--catalog': ['/', '/panier', '/profil'].includes(route.path) }"
      >
        <LayoutTopBar show-nav />
        <slot />
      </div>
    </v-main>
    <LayoutBottomNav />
  </v-app>
</template>

<style scoped>
/* Réserve la place de LayoutBottomNav (fixe, en bas) -- superflu sur
   desktop où cette barre est masquée (voir BottomNav.vue). */
.buyer-shell {
  padding-bottom: 76px;
}

@media (min-width: 960px) {
  .buyer-shell {
    padding-bottom: 24px;
  }
}
</style>
