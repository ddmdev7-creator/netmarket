<script setup lang="ts">
/**
 * Bascule Liste / Carte des écrans admin vendeurs, livreurs et points de
 * retrait — même emplacement et même libellé partout.
 */
import { PhListBullets, PhMapTrifold } from '@phosphor-icons/vue'

const view = defineModel<'list' | 'map'>({ required: true })
</script>

<template>
  <v-btn-toggle v-model="view" mandatory density="compact" divided variant="outlined" aria-label="Affichage">
    <v-btn value="list" size="small">
      <PhListBullets :size="16" class="mr-1" />
      Liste
    </v-btn>
    <v-btn value="map" size="small">
      <PhMapTrifold :size="16" class="mr-1" />
      Carte
    </v-btn>
  </v-btn-toggle>
</template>
