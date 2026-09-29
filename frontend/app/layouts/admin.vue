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

/* --- Fiches détaillées (utilisateur, livreur, point de retrait) ------------ */
.pf-head {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 20px;
}

.pf-back {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 1px solid var(--color-divider);
  background: var(--color-neutral-900);
  color: var(--color-neutral-300);
  text-decoration: none;
}

.pf-avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  flex-shrink: 0;
  border-radius: 20px;
  background: linear-gradient(135deg, hsl(var(--hue, 220) 75% 55%), hsl(calc(var(--hue, 220) + 40) 70% 50%));
  color: #fff;
  font-family: var(--font-heading);
  font-size: 22px;
  font-weight: 800;
  overflow: hidden;
}

.pf-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.pf-title {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-width: 200px;
}

.pf-title h1 {
  margin: 0;
}

.pf-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.pf-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--color-neutral-800);
  color: var(--color-neutral-300);
  font-size: 12px;
  font-weight: 700;
}

.pf-tag--success { background: hsl(150 70% var(--tint-bg)); color: hsl(150 55% var(--tint-fg)); }
.pf-tag--warning { background: hsl(38 90% var(--tint-bg)); color: hsl(30 75% var(--tint-fg)); }
.pf-tag--error { background: hsl(355 80% var(--tint-bg)); color: hsl(355 65% var(--tint-fg)); }
.pf-tag--primary { background: var(--color-primary-100); color: var(--color-primary-300); }

.pf-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.pf-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 10px;
  margin-bottom: 18px;
}

.pf-stat {
  padding: 14px 16px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-divider);
  background: var(--color-neutral-900);
  box-shadow: var(--shadow-sm);
}

.pf-stat strong {
  display: block;
  font-family: var(--font-heading);
  font-size: 20px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}

.pf-stat span {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--color-neutral-400);
}

.pf-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 16px;
}

@media (min-width: 1100px) {
  .pf-grid {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    align-items: start;
  }
}

.pf-card {
  padding: 18px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-divider);
  background: var(--color-neutral-900);
  box-shadow: var(--shadow-sm);
}

.pf-card__title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin: 0 0 12px;
  font-family: var(--font-heading);
  font-size: 15px;
  font-weight: 800;
}

.pf-kv {
  display: grid;
  grid-template-columns: minmax(110px, 36%) 1fr;
  gap: 8px 12px;
  margin: 0;
  font-size: 13.5px;
}

.pf-kv dt {
  color: var(--color-neutral-400);
}

.pf-kv dd {
  margin: 0;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.pf-list {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  list-style: none;
}

.pf-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 0;
  border-top: 1px solid var(--color-divider);
  font-size: 13px;
  color: inherit;
  text-decoration: none;
}

.pf-row:first-child {
  border-top: 0;
}

a.pf-row:hover {
  color: var(--color-primary-300);
}

.pf-row__main {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.pf-row__main small {
  color: var(--color-neutral-400);
}

.pf-empty {
  margin: 0;
  font-size: 13px;
  color: var(--color-neutral-400);
}

.pf-form {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}
.pf-form__full {
  grid-column: 1 / -1;
}

.pf-card__title > span,
.pf-kv dt {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.pf-note {
  margin: 12px 0 0;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  background: hsl(38 90% var(--tint-bg));
  color: hsl(30 75% var(--tint-fg));
  font-size: 12.5px;
  font-weight: 600;
}

.pf-docs {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
  gap: 10px;
}

.pf-doc {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 0;
  border: 0;
  background: none;
  color: inherit;
  text-align: left;
  cursor: zoom-in;
}

.pf-doc img,
.pf-doc::before {
  width: 100%;
  aspect-ratio: 4 / 3;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-divider);
  background: var(--color-neutral-800);
  object-fit: cover;
}

.pf-doc:not(:has(img))::before {
  content: '';
  display: block;
}

.pf-doc span {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--color-neutral-400);
}

.pf-viewer {
  display: block;
  width: 100%;
  max-height: 70vh;
  object-fit: contain;
  border-radius: var(--radius-md);
  background: var(--color-neutral-800);
}

.pf-avatar--photo {
  background: var(--color-neutral-800);
  color: var(--color-neutral-400);
}

@media (min-width: 1100px) {
  .pf-card--wide {
    grid-column: 1 / -1;
  }
}

.pf-kv a {
  color: var(--color-primary);
  text-decoration: none;
}

.pf-kv a:hover {
  text-decoration: underline;
}
</style>
