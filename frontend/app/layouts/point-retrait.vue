<template>
  <v-app>
    <v-main>
      <LayoutTopBar space="Point de retrait" />
      <div class="app-shell" style="padding-bottom: 76px">
        <slot />
      </div>
    </v-main>
    <LayoutPickupManagerBottomNav />
  </v-app>
</template>
