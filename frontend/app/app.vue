<template>
  <VitePwaManifest />
  <NuxtLayout>
    <NuxtPage />
  </NuxtLayout>
  <LayoutToastHost />
  <CommonIosInstallBanner />
  <!-- Barre de progression fixe en haut d'écran — se déclenche automatiquement
       sur toute navigation/chargement de données de page, indépendamment du
       scroll (position fixed native à ce composant Nuxt). -->
  <NuxtLoadingIndicator color="var(--color-accent)" :height="3" :throttle="150" />
</template>
