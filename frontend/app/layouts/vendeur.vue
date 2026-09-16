<script setup lang="ts">
import { PhList } from '@phosphor-icons/vue'

const { mdAndUp } = useDisplay()
// Même logique que layouts/admin.vue : sidebar permanente sur desktop,
// tiroir masqué par défaut sur mobile.
const drawerOpen = ref(mdAndUp.value)
watch(mdAndUp, (isDesktop) => { drawerOpen.value = isDesktop })
</script>

<template>
  <v-app>
    <v-navigation-drawer v-model="drawerOpen" :permanent="mdAndUp" width="240" border="0" class="vendor-drawer">
      <LayoutVendorSidebar @navigate="() => { if (!mdAndUp) drawerOpen = false }" />
    </v-navigation-drawer>

    <v-main>
      <LayoutTopBar>
        <template #leading>
          <button v-if="!mdAndUp" type="button" class="vendor-menu-btn" aria-label="Ouvrir le menu" @click="drawerOpen = true">
            <PhList :size="20" />
          </button>
        </template>
      </LayoutTopBar>
      <div class="dashboard-shell">
        <slot />
      </div>
    </v-main>
  </v-app>
</template>

<style scoped>
.vendor-drawer {
  background: var(--color-neutral-900);
  border-right: 1px solid var(--color-divider);
}

.vendor-menu-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  background: none;
  border: none;
  color: inherit;
}
</style>
