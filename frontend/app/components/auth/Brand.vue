<template>
  <NuxtLink to="/" class="auth-mark" aria-label="NdjouriMarket — accueil">
    <span class="auth-mark__logo">N</span>
    <span class="auth-mark__name">Ndjouri<span class="auth-mark__accent">Market</span></span>
  </NuxtLink>
</template>

<style scoped>
.auth-mark {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: inherit;
  text-decoration: none;
}

.auth-mark__logo {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: linear-gradient(135deg, var(--color-primary), #4f46e5);
  color: #fff;
  font-family: var(--font-heading);
  font-size: 20px;
  font-weight: 800;
  box-shadow: var(--shadow-glow-primary);
}

.auth-mark__name {
  font-family: var(--font-heading);
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.02em;
  white-space: nowrap;
}

.auth-mark__accent {
  color: var(--color-primary);
}
</style>
