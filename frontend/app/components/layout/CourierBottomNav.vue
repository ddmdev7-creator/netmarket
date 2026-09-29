<script setup lang="ts">
import { PhPackage, PhUser, PhWallet } from '@phosphor-icons/vue'

const navItems = [
  { to: '/livreur', label: 'Livraisons', icon: PhPackage },
  { to: '/livreur/gains', label: 'Gains', icon: PhWallet },
  { to: '/profil', label: 'Profil', icon: PhUser },
]
</script>

<template>
  <LayoutSpaceNav :items="navItems" />
</template>
