import { daylightTheme } from './app/theme/daylight'
import { nocturneTheme } from './app/theme/nocturne'

// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: true },

  modules: ['vuetify-nuxt-module', '@pinia/nuxt', '@vite-pwa/nuxt'],

  css: ['~/assets/styles/main.css'],

  app: {
    head: {
      htmlAttrs: { lang: 'fr' },
      // viewport-fit=cover lets the app draw under the notch/home-indicator so
      // env(safe-area-inset-*) below can push content back in — required for a
      // real edge-to-edge look once installed (standalone display mode).
      viewport: 'width=device-width, initial-scale=1, viewport-fit=cover, maximum-scale=1, user-scalable=no',
      meta: [
        { name: 'description', content: 'Marketplace e-commerce multi-vendeurs pour le marché guinéen' },
        // Valeur par défaut (thème clair "daylight") — mise à jour à l'exécution
        // par useAppTheme() quand l'utilisateur bascule en mode sombre.
        { name: 'theme-color', content: '#F3F4F6' },
        // iOS ignores the Web App Manifest's display mode — these are what actually
        // trigger standalone (no Safari chrome) when added to the home screen.
        { name: 'mobile-web-app-capable', content: 'yes' },
        { name: 'apple-mobile-web-app-capable', content: 'yes' },
        { name: 'apple-mobile-web-app-status-bar-style', content: 'default' },
        { name: 'apple-mobile-web-app-title', content: 'Marketplace' },
      ],
      link: [{ rel: 'apple-touch-icon', href: '/apple-touch-icon.png' }],
    },
  },

  // Écoute sur toutes les interfaces (pas seulement localhost) — sans ça, un
  // téléphone sur le même Wi-Fi ne peut pas du tout charger la page, même si
  // l'API (déjà publiée sur 0.0.0.0 par docker-compose) est déjà accessible.
  devServer: { host: '0.0.0.0' },

  runtimeConfig: {
    public: {
      // Vide par défaut : useApiBase() (app/composables/useApiBase.ts)
      // détecte alors l'hôte à contacter à partir de celui utilisé pour
      // charger la page — voir ce fichier pour le raisonnement complet.
      // Ne renseigner NUXT_PUBLIC_API_BASE que pour forcer une adresse fixe
      // (ex. un vrai nom de domaine en production).
      apiBase: process.env.NUXT_PUBLIC_API_BASE || '',
    },
  },

  vuetify: {
    vuetifyOptions: {
      theme: {
        defaultTheme: 'daylight',
        themes: { daylight: daylightTheme, nocturne: nocturneTheme },
      },
      defaults: {
        VCard: { rounded: 'lg', elevation: 2 },
        VBtn: { rounded: 'lg' },
        VChip: { rounded: 'pill' },
        VTextField: { variant: 'outlined', density: 'comfortable' },
        VTextarea: { variant: 'outlined', density: 'comfortable' },
      },
    },
  },

  pwa: {
    registerType: 'autoUpdate',
    manifest: {
      name: 'Marketplace Guinée',
      short_name: 'Marketplace',
      description: 'Marketplace e-commerce multi-vendeurs pour le marché guinéen',
      lang: 'fr',
      theme_color: '#F3F4F6',
      background_color: '#F3F4F6',
      display: 'standalone',
      orientation: 'portrait',
      start_url: '/',
      scope: '/',
      icons: [
        { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
        { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
        { src: '/icons/icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
      ],
    },
    workbox: {
      navigateFallback: '/',
      globPatterns: ['**/*.{js,css,html,png,svg,ico,woff2}'],
      // Catalogue en cache-first courte durée : lecture rapide même sur réseau
      // lent, sans servir des prix/stocks trop obsolètes.
      runtimeCaching: [
        {
          urlPattern: ({ url }: { url: URL }) => url.pathname.startsWith('/products') || url.pathname.startsWith('/categories'),
          handler: 'NetworkFirst',
          options: {
            cacheName: 'api-catalogue',
            networkTimeoutSeconds: 3,
            expiration: { maxEntries: 100, maxAgeSeconds: 300 },
          },
        },
      ],
    },
    devOptions: { enabled: false },
  },
})
