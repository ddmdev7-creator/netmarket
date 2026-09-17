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
      <div class="app-shell buyer-shell" :class="{ 'app-shell--catalog': route.path === '/' }">
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
