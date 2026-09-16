<script setup lang="ts">
import { PhList } from '@phosphor-icons/vue'

const { mdAndUp } = useDisplay()
// Ouvert par défaut sur desktop (barre latérale permanente), fermé par
// défaut sur mobile (tiroir qui se superpose au contenu) — voir template :
// :permanent bascule le comportement du v-navigation-drawer selon la taille
// d'écran, ce ref ne contrôle que l'état visible/caché.
const drawerOpen = ref(mdAndUp.value)
watch(mdAndUp, (isDesktop) => { drawerOpen.value = isDesktop })
</script>

<template>
  <v-app>
    <v-navigation-drawer v-model="drawerOpen" :permanent="mdAndUp" width="240" border="0" class="admin-drawer">
      <LayoutAdminSidebar @navigate="() => { if (!mdAndUp) drawerOpen = false }" />
    </v-navigation-drawer>

    <v-main>
      <LayoutTopBar>
        <template #leading>
          <button v-if="!mdAndUp" type="button" class="admin-menu-btn" aria-label="Ouvrir le menu" @click="drawerOpen = true">
            <PhList :size="20" />
          </button>
        </template>
      </LayoutTopBar>
      <div class="admin-shell">
        <slot />
      </div>
    </v-main>
  </v-app>
</template>

<style scoped>
.admin-drawer {
  background: var(--color-neutral-900);
  border-right: 1px solid var(--color-divider);
}

.admin-menu-btn {
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
