<script setup lang="ts">
definePageMeta({ middleware: 'pickup-manager', layout: 'point-retrait' })
</script>

<template>
  <div class="gains-page">
    <h1 class="gains-page__title">Mes gains</h1>
    <WalletDashboard kind="pickup_point" />
  </div>
</template>

<style scoped>
.gains-page {
  max-width: 720px;
  margin: 0 auto;
  padding: 16px;
}

.gains-page__title {
  margin: 0 0 14px;
  font-family: var(--font-heading);
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--color-neutral-200);
}
</style>
