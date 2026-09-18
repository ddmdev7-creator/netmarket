<script setup lang="ts">
import { PhBell, PhHouse, PhPackage, PhShoppingCart, PhUser, PhUserCircle } from '@phosphor-icons/vue'

/**
 * showNav: true uniquement depuis layouts/default.vue (espace acheteur).
 * Une prop explicite plutôt qu'une détection par rôle sur auth.user — ce
 * dernier peut rester null un court instant après le chargement d'une page
 * protégée (fetchMe async), ce qui ferait clignoter ce lien vers la nav
 * acheteur sur les pages vendeur/admin/livreur le temps que l'utilisateur
 * se charge.
 */
const props = withDefaults(defineProps<{ showNav?: boolean }>(), { showNav: false })

const auth = useAuthStore()
const notifications = useNotificationStore()
const cartStore = useCartStore()

const roleLabel = computed(() => {
  switch (auth.user?.role) {
    case 'vendor':
      return 'Vendeur'
    case 'admin':
      return 'Admin'
    default:
      return 'Acheteur'
  }
})

const displayIdentity = computed(() => {
  const user = auth.user
  if (!user) return ''
  if (user.first_name && user.last_name) {
    return `${user.first_name[0].toUpperCase()}. ${user.last_name}`
  }
  return user.phone
})

// Repris de BottomNav (masquée sur desktop, voir BottomNav.vue) : mêmes
// destinations, affichées ici en ligne uniquement à partir de 960px (voir
// .top-bar__nav) — en dessous, la bottom nav reste la seule navigation,
// comme aujourd'hui.
const navItems = [
  { to: '/', label: 'Accueil', icon: PhHouse },
  { to: '/panier', label: 'Panier', icon: PhShoppingCart },
  { to: '/commandes', label: 'Commandes', icon: PhPackage },
  { to: '/profil', label: 'Profil', icon: PhUser },
]
</script>

<template>
  <div v-if="auth.user" class="top-bar">
    <slot name="leading" />

    <nav v-if="props.showNav" class="top-bar__nav">
      <NuxtLink
        v-for="item in navItems"
        :key="item.to"
        :to="item.to"
        class="top-bar__nav-item"
        active-class="top-bar__nav-item--active"
      >
        <v-badge
          v-if="item.to === '/panier' && cartStore.itemCount > 0"
          :content="cartStore.itemCount"
          color="primary"
          offset-x="-4"
          offset-y="-2"
        >
          <component :is="item.icon" :size="17" />
        </v-badge>
        <component :is="item.icon" v-else :size="17" />
        <span>{{ item.label }}</span>
      </NuxtLink>
    </nav>

    <NuxtLink to="/profil" class="top-bar__identity">
      <PhUserCircle :size="18" color="var(--color-neutral-400)" />
      <span class="top-bar__phone">{{ displayIdentity }}</span>
    </NuxtLink>
    <span class="top-bar__role">{{ roleLabel }}</span>
    <LayoutThemeToggle />
    <NuxtLink to="/notifications" class="top-bar__bell" aria-label="Notifications">
      <PhBell :size="19" color="var(--color-neutral-300)" />
      <span v-if="notifications.unreadCount > 0" class="top-bar__badge">
        {{ notifications.unreadCount > 9 ? '9+' : notifications.unreadCount }}
      </span>
    </NuxtLink>
  </div>

  <!-- Visiteur non connecté sur l'espace acheteur (catalogue accessible sans
       compte) : affichée sur toutes les tailles d'écran désormais — logo +
       lien de connexion visibles même sur mobile (les liens de nav internes
       à cette barre restent masqués sous 960px via .top-bar__nav, la bottom
       nav suffit déjà à cette taille). Sans cette barre, un visiteur
       desktop n'aurait plus aucun moyen de naviguer une fois la bottom nav
       masquée (voir BottomNav.vue). -->
  <div v-else-if="props.showNav" class="top-bar top-bar--guest">
    <NuxtLink to="/" class="top-bar__logo">Netmarket</NuxtLink>
    <nav class="top-bar__nav">
      <NuxtLink v-for="item in navItems" :key="item.to" :to="item.to" class="top-bar__nav-item">
        <component :is="item.icon" :size="17" />
        <span>{{ item.label }}</span>
      </NuxtLink>
    </nav>
    <NuxtLink to="/connexion" class="top-bar__login ml-auto">Se connecter</NuxtLink>
  </div>
</template>

<style scoped>
.top-bar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 8px;
  /* The notch/status-bar offset itself now lives on `.v-main` (main.css) —
     applying it here too would double it up. */
  padding: 8px 16px 8px;
  background: var(--color-neutral-900);
  border-bottom: 1px solid var(--color-divider);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
  color: var(--color-neutral-200);
  font-size: 13px;
}

.top-bar__identity {
  display: flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
  color: inherit;
  min-width: 0;
}

.top-bar__phone {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.top-bar__role {
  margin-left: auto;
  color: var(--color-neutral-400);
  font-size: 11.5px;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-sm);
  padding: 2px 8px;
  flex-shrink: 0;
}

.top-bar__bell {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  color: inherit;
}

.top-bar__badge {
  position: absolute;
  top: 0;
  right: 0;
  min-width: 15px;
  height: 15px;
  padding: 0 3px;
  border-radius: 999px;
  background: var(--color-error);
  color: #fff;
  font-size: 9.5px;
  font-weight: 700;
  line-height: 15px;
  text-align: center;
}

/* Nav horizontale (Accueil/Panier/Commandes/Profil) : masquée sur mobile,
   où la bottom nav suffit déjà — visible seulement à partir de 960px,
   quand celle-ci disparaît (voir BottomNav.vue). */
.top-bar__nav {
  display: none;
}

/* Contrairement à .top-bar__nav ci-dessus, cette barre elle-même reste
   visible à toutes les tailles — c'est la seule chose qu'un visiteur non
   connecté voit en haut de l'app, pas la peine d'attendre le desktop pour
   ça (voir le commentaire sur le v-else-if plus haut). */
.top-bar--guest {
  display: flex;
  align-items: center;
  gap: 8px;
}

@media (min-width: 960px) {
  .top-bar__nav {
    /* Pas de margin-right: auto ici -- .top-bar__role a déjà
       margin-left: auto, qui suffit à pousser role/thème/cloche à droite ;
       un deuxième auto-margin créerait un second espace flexible et
       pousserait l'identité au centre au lieu de la laisser collée à nav. */
    display: flex;
    align-items: center;
    gap: 4px;
  }
}

.top-bar__nav-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: var(--radius-sm);
  color: var(--color-neutral-400);
  text-decoration: none;
  font-size: 12.5px;
  font-weight: 600;
  transition: color 0.15s ease, background 0.15s ease;
}

.top-bar__nav-item:hover {
  color: var(--color-neutral-200);
  background: var(--color-neutral-800);
}

.top-bar__nav-item--active {
  color: var(--color-primary);
}

.top-bar__logo {
  font-family: var(--font-heading);
  font-weight: 800;
  font-size: 16px;
  color: var(--color-primary-300);
  text-decoration: none;
  margin-right: 8px;
}

.top-bar__login {
  color: var(--color-primary-300);
  text-decoration: none;
  font-weight: 600;
  font-size: 12.5px;
  padding: 6px 14px;
  border: 1px solid var(--color-divider-strong);
  border-radius: var(--radius-sm);
}
</style>
