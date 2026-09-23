<template>
  <v-app>
    <v-main>
      <!-- app-shell--catalog (pas de plafond, voir main.css) : seule page à
           utiliser ce layout, .detail-card (voir livreur/index.vue) recentre
           LE CONTENU en une carte détachée, sans replafonner LayoutTopBar
           avec -- même motif que layouts/default.vue pour profil/commandes. -->
      <div class="app-shell app-shell--catalog" style="padding-bottom: 76px">
        <LayoutTopBar />
        <slot />
      </div>
    </v-main>
    <LayoutCourierBottomNav />
    <LayoutDeliveryRequestModal />
  </v-app>
</template>
