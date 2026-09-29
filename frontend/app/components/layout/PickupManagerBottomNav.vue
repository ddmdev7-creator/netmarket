<script setup lang="ts">
import { PhPackage, PhStorefront, PhUser, PhWallet } from '@phosphor-icons/vue'

const navItems = [
  { to: '/point-retrait', label: 'Colis', icon: PhPackage },
  { to: '/point-retrait/mon-point', label: 'Mon point', icon: PhStorefront },
  { to: '/point-retrait/gains', label: 'Gains', icon: PhWallet },
  { to: '/profil', label: 'Profil', icon: PhUser },
]
</script>

<template>
  <LayoutSpaceNav :items="navItems" />
</template>
