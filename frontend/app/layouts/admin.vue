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
    <v-navigation-drawer v-model="drawerOpen" :permanent="mdAndUp" width="260" border="0" class="admin-drawer">
      <LayoutAdminSidebar @navigate="() => { if (!mdAndUp) drawerOpen = false }" />
    </v-navigation-drawer>

    <v-main>
      <LayoutTopBar space="Administration">
        <template #leading>
          <button v-if="!mdAndUp" type="button" class="admin-menu-btn" aria-label="Ouvrir le menu" @click="drawerOpen = true">
            <PhList :size="20" />
          </button>
        </template>
      </LayoutTopBar>
      <div class="admin-shell admin-main">
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
  width: 42px;
  height: 42px;
  flex-shrink: 0;
  border-radius: 50%;
  background: none;
  border: none;
  color: var(--color-neutral-300);
  cursor: pointer;
}

.admin-menu-btn:hover {
  background: var(--color-neutral-800);
}
</style>

<!-- Styles communs à toutes les pages d'administration (non scopés, limités
     à .admin-main) : titres, cartes, tableaux et onglets homogènes. -->
<style>
.admin-main h1.text-h6 {
  font-family: var(--font-heading);
  font-size: 26px !important;
  font-weight: 800 !important;
  letter-spacing: -0.02em;
  line-height: 1.2;
  color: var(--color-neutral-200);
}

@media (max-width: 600px) {
  .admin-main h1.text-h6 {
    font-size: 21px !important;
  }
}

.admin-main .v-card:not(.v-card--variant-text) {
  border-radius: var(--radius-lg);
}

.admin-main .v-card--variant-flat,
.admin-main .v-card--variant-elevated {
  border: 1px solid var(--color-divider);
  box-shadow: var(--shadow-sm);
}

.admin-main .v-table {
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-divider);
  background: var(--color-neutral-900);
  overflow: hidden;
}

.admin-main .v-table thead th {
  font-size: 11.5px !important;
  font-weight: 800 !important;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--color-neutral-500) !important;
  background: var(--color-neutral-800) !important;
}

.admin-main .v-table tbody tr:hover > td {
  background: color-mix(in srgb, var(--color-primary) 5%, transparent);
}

.admin-main .v-tabs {
  border-bottom: 1px solid var(--color-divider);
}

.admin-main .v-tab {
  text-transform: none !important;
  letter-spacing: 0 !important;
  font-weight: 700;
}

.admin-main .v-chip {
  font-weight: 700;
}

/* Filtres segmentés (v-btn-toggle) : pastilles lisibles, l'active en couleur. */
.admin-main .v-btn-group {
  height: auto !important;
  padding: 3px;
  gap: 2px;
  border: 1px solid var(--color-divider) !important;
  border-radius: 999px !important;
  background: var(--color-neutral-900);
  box-shadow: var(--shadow-sm);
  flex-wrap: wrap;
}

.admin-main .v-btn-group .v-btn {
  height: 34px !important;
  padding: 0 14px !important;
  border: 0 !important;
  border-radius: 999px !important;
  color: var(--color-neutral-400);
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: none;
}

.admin-main .v-btn-group .v-btn--active {
  background: var(--color-primary) !important;
  color: #fff !important;
}

.admin-main .v-btn-group .v-btn--active > .v-btn__overlay {
  opacity: 0 !important;
}

/* Champs : coins arrondis et fond de carte, comme le reste de l'interface. */
.admin-main .v-field--variant-outlined {
  border-radius: 12px;
  background: var(--color-neutral-900);
}

/* Boutons : tailles homogènes d'une page à l'autre, sans capitales forcées. */
.admin-main .v-btn {
  text-transform: none;
  letter-spacing: 0;
  font-weight: 700;
}

.admin-main .v-btn--size-default {
  font-size: 14px !important;
}

.admin-main .v-btn--size-small {
  font-size: 12.5px !important;
}

.admin-main .v-btn--size-x-small {
  font-size: 12px !important;
}

.admin-main .empty-state {
  border-radius: var(--radius-lg);
  border: 1px dashed var(--color-divider-strong);
  background: var(--color-neutral-900);
}
</style>
