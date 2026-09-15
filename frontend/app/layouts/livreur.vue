<template>
  <v-app>
    <v-main>
      <div class="app-shell" style="padding-bottom: 76px">
        <LayoutTopBar />
        <slot />
      </div>
    </v-main>
    <LayoutCourierBottomNav />
    <LayoutDeliveryRequestModal />
  </v-app>
</template>
