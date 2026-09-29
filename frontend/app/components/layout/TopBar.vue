<script setup lang="ts">
import {
  PhArrowLeft,
  PhBell,
  PhCaretDown,
  PhChartBar,
  PhHeart,
  PhHouse,
  PhMoon,
  PhPackage,
  PhShieldCheck,
  PhShoppingCart,
  PhSignOut,
  PhStorefront,
  PhSun,
  PhTruck,
  PhUser,
  PhWallet,
  PhWarehouse,
} from '@phosphor-icons/vue'
import type { Component } from 'vue'

/**
 * Barre du haut commune à tous les espaces.
 *  - showNav : navigation acheteur (Accueil, Favoris, Commandes) sur ordinateur ;
 *    sur téléphone, c'est la barre du bas qui s'en charge.
 *  - showCart : icône panier même sur téléphone (pages sans barre du bas).
 *  - back : flèche de retour (pages « focus » : fiche produit, commande…).
 *  - space : libellé de l'espace (vendeur, admin…) à côté du logo.
 * Le menu du compte regroupe profil, espace du rôle, thème et déconnexion.
 */
const props = withDefaults(
  defineProps<{ showNav?: boolean; showCart?: boolean; back?: boolean; space?: string | null }>(),
  { showNav: false, showCart: false, back: false, space: null },
)

const auth = useAuthStore()
const notifications = useNotificationStore()
const cartStore = useCartStore()
const route = useRoute()
const router = useRouter()
const { theme, toggle: toggleTheme } = useAppTheme()

const navItems = [
  { to: '/', label: 'Accueil', icon: PhHouse },
  { to: '/favoris', label: 'Favoris', icon: PhHeart },
  { to: '/commandes', label: 'Commandes', icon: PhPackage },
]

function isActive(to: string) {
  return to === '/' ? route.path === '/' : route.path.startsWith(to)
}

const isBuyerSide = computed(() => !auth.user || auth.user.role === 'buyer')

// Espace propre au rôle (le menu y mène, et ramène à la boutique depuis celui-ci).
const roleSpace = computed<{ to: string; label: string; icon: Component } | null>(() => {
  switch (auth.user?.role) {
    case 'vendor':
      return { to: '/vendeur', label: 'Espace vendeur', icon: PhStorefront }
    case 'courier':
      return { to: '/livreur', label: 'Espace livreur', icon: PhTruck }
    case 'pickup_point_manager':
      return { to: '/point-retrait', label: 'Mon point de retrait', icon: PhWarehouse }
    case 'admin':
      return { to: '/admin', label: 'Administration', icon: PhShieldCheck }
    default:
      return null
  }
})

const roleLabel = computed(() => {
  switch (auth.user?.role) {
    case 'vendor':
      return 'Vendeur'
    case 'admin':
      return 'Admin'
    case 'courier':
      return 'Livreur'
    case 'pickup_point_manager':
      return 'Point de retrait'
    default:
      return 'Acheteur'
  }
})

const displayName = computed(() => {
  const user = auth.user
  if (!user) return ''
  if (user.first_name) return [user.first_name, user.last_name].filter(Boolean).join(' ')
  return user.phone
})

const initials = computed(() => {
  const user = auth.user
  if (!user) return ''
  if (user.first_name) return `${user.first_name[0] ?? ''}${user.last_name?.[0] ?? ''}`.toUpperCase()
  return user.phone.slice(-2)
})

const logoTo = computed(() => (props.space && roleSpace.value ? roleSpace.value.to : '/'))

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push('/')
}

async function logout() {
  auth.logout()
  await navigateTo('/connexion')
}

// Ombre plus marquée dès qu'on a défilé : la barre se détache du contenu.
const scrolled = ref(false)
function onScroll() {
  scrolled.value = window.scrollY > 4
}
onMounted(() => {
  onScroll()
  window.addEventListener('scroll', onScroll, { passive: true })
})
onBeforeUnmount(() => window.removeEventListener('scroll', onScroll))
</script>

<template>
  <header class="tb" :class="{ 'tb--scrolled': scrolled }">
    <div class="tb__inner">
      <slot name="leading" />
      <button v-if="back" type="button" class="tb__icon-btn" aria-label="Retour" @click="goBack">
        <PhArrowLeft :size="20" />
      </button>

      <NuxtLink :to="logoTo" class="tb__brand" :class="{ 'tb__brand--compact': space || back }" aria-label="Netmarket — accueil">
        <span class="tb__logo">N</span>
        <span class="tb__wordmark">Netmarket</span>
      </NuxtLink>
      <span v-if="space" class="tb__space">{{ space }}</span>

      <nav v-if="showNav && isBuyerSide" class="tb__nav" aria-label="Navigation principale">
        <NuxtLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="tb__nav-item"
          :class="{ 'is-active': isActive(item.to) }"
        >
          <component :is="item.icon" :size="18" :weight="isActive(item.to) ? 'fill' : 'regular'" />
          <span>{{ item.label }}</span>
        </NuxtLink>
      </nav>

      <div class="tb__actions">
        <NuxtLink
          v-if="isBuyerSide && (showNav || showCart)"
          to="/panier"
          class="tb__icon-btn"
          :class="{ 'tb__icon-btn--mobile-hidden': !showCart, 'is-active': isActive('/panier') }"
          aria-label="Panier"
        >
          <span :key="cartStore.bumpTick" class="tb__bump" :class="{ 'is-bump': cartStore.bumpTick > 0 }">
            <PhShoppingCart :size="21" :weight="isActive('/panier') ? 'fill' : 'regular'" />
          </span>
          <span v-if="cartStore.itemCount > 0" class="tb__badge tb__badge--primary">
            {{ cartStore.itemCount > 99 ? '99+' : cartStore.itemCount }}
          </span>
        </NuxtLink>

        <template v-if="auth.user">
          <NuxtLink to="/notifications" class="tb__icon-btn" aria-label="Notifications">
            <PhBell :size="21" :weight="notifications.unreadCount ? 'fill' : 'regular'" />
            <span v-if="notifications.unreadCount > 0" class="tb__badge">
              {{ notifications.unreadCount > 9 ? '9+' : notifications.unreadCount }}
            </span>
          </NuxtLink>

          <v-menu location="bottom end" offset="8">
            <template #activator="{ props: menuProps }">
              <button v-bind="menuProps" type="button" class="tb__account" aria-label="Mon compte">
                <span class="tb__avatar">{{ initials }}</span>
                <span class="tb__who">
                  <span class="tb__name">{{ displayName }}</span>
                  <span class="tb__role">{{ roleLabel }}</span>
                </span>
                <PhCaretDown :size="14" class="tb__caret" />
              </button>
            </template>
            <div class="tb-menu">
              <div class="tb-menu__head">
                <span class="tb__avatar tb__avatar--lg">{{ initials }}</span>
                <span class="tb-menu__id">
                  <strong>{{ displayName }}</strong>
                  <span>{{ auth.user.phone }} · {{ roleLabel }}</span>
                </span>
              </div>
              <NuxtLink v-if="roleSpace && !space" :to="roleSpace.to" class="tb-menu__item tb-menu__item--accent">
                <component :is="roleSpace.icon" :size="18" /> {{ roleSpace.label }}
              </NuxtLink>
              <NuxtLink v-if="space" to="/" class="tb-menu__item tb-menu__item--accent">
                <PhStorefront :size="18" /> Visiter le marché
              </NuxtLink>
              <NuxtLink to="/profil" class="tb-menu__item"><PhUser :size="18" /> Mon profil</NuxtLink>
              <template v-if="isBuyerSide">
                <NuxtLink to="/commandes" class="tb-menu__item"><PhPackage :size="18" /> Mes commandes</NuxtLink>
                <NuxtLink to="/favoris" class="tb-menu__item"><PhHeart :size="18" /> Mes favoris</NuxtLink>
                <NuxtLink to="/ndjouribank" class="tb-menu__item"><PhWallet :size="18" /> NdjouriBank</NuxtLink>
              </template>
              <NuxtLink v-if="auth.user.role === 'vendor'" to="/vendeur/gains" class="tb-menu__item">
                <PhChartBar :size="18" /> Mes gains
              </NuxtLink>
              <button type="button" class="tb-menu__item" @click="toggleTheme">
                <component :is="theme === 'dark' ? PhSun : PhMoon" :size="18" />
                {{ theme === 'dark' ? 'Mode clair' : 'Mode sombre' }}
              </button>
              <div class="tb-menu__sep" />
              <button type="button" class="tb-menu__item tb-menu__item--danger" @click="logout">
                <PhSignOut :size="18" /> Se déconnecter
              </button>
            </div>
          </v-menu>
        </template>

        <template v-else>
          <button
            type="button"
            class="tb__icon-btn"
            :aria-label="theme === 'dark' ? 'Passer au mode clair' : 'Passer au mode sombre'"
            @click="toggleTheme"
          >
            <component :is="theme === 'dark' ? PhSun : PhMoon" :size="19" />
          </button>
          <NuxtLink :to="{ path: '/connexion', query: { redirect: route.fullPath } }" class="tb__login">Se connecter</NuxtLink>
          <NuxtLink to="/inscription" class="tb__signup">Créer un compte</NuxtLink>
        </template>
      </div>
    </div>
  </header>
</template>

<style scoped>
.tb {
  position: sticky;
  top: 0;
  z-index: 20;
  background: color-mix(in srgb, var(--color-neutral-900) 88%, transparent);
  backdrop-filter: saturate(160%) blur(12px);
  -webkit-backdrop-filter: saturate(160%) blur(12px);
  border-bottom: 1px solid var(--color-divider);
  transition: box-shadow 0.2s ease;
}

.tb--scrolled {
  box-shadow: var(--shadow-md);
}

.tb__inner {
  display: flex;
  align-items: center;
  gap: 6px;
  max-width: 1280px;
  height: 58px;
  margin: 0 auto;
  padding: 0 12px;
}

@media (min-width: 960px) {
  .tb__inner {
    height: 64px;
    padding: 0 24px;
    gap: 10px;
  }
}

/* --- Marque --- */
.tb__brand {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  text-decoration: none;
}

.tb__logo {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--color-primary), #4f46e5);
  color: #fff;
  font-family: var(--font-heading);
  font-weight: 800;
  font-size: 17px;
  box-shadow: var(--shadow-glow-primary);
}

.tb__wordmark {
  font-family: var(--font-heading);
  font-weight: 800;
  font-size: 18px;
  letter-spacing: -0.01em;
  color: var(--color-neutral-200);
}

.tb__space {
  flex-shrink: 0;
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--color-primary-100);
  color: var(--color-primary-300);
  font-size: 11.5px;
  font-weight: 700;
}

@media (max-width: 420px) {
  /* Téléphone étroit en espace pro : le libellé d'espace suffit, le mot "Netmarket" saute. */
  .tb__brand--compact .tb__wordmark {
    display: none;
  }
}

/* --- Navigation (ordinateur) --- */
.tb__nav {
  display: none;
}

@media (min-width: 960px) {
  .tb__nav {
    display: flex;
    align-items: center;
    gap: 2px;
    margin-left: 18px;
  }
}

.tb__nav-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 8px 14px;
  border-radius: 999px;
  color: var(--color-neutral-400);
  text-decoration: none;
  font-size: 14px;
  font-weight: 600;
  transition: color 0.15s ease, background 0.15s ease;
}

.tb__nav-item:hover {
  color: var(--color-neutral-200);
  background: var(--color-neutral-800);
}

.tb__nav-item.is-active {
  color: var(--color-primary-300);
  background: var(--color-primary-100);
}

/* --- Actions à droite --- */
.tb__actions {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
}

.tb__icon-btn {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  flex-shrink: 0;
  border: 0;
  border-radius: 50%;
  background: none;
  color: var(--color-neutral-300);
  text-decoration: none;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}

.tb__icon-btn:hover {
  background: var(--color-neutral-800);
}

.tb__icon-btn.is-active {
  color: var(--color-primary-300);
}

@media (max-width: 959px) {
  .tb__icon-btn--mobile-hidden {
    display: none;
  }
}

.tb__badge {
  position: absolute;
  top: 5px;
  right: 4px;
  min-width: 17px;
  height: 17px;
  padding: 0 4px;
  border-radius: 999px;
  border: 2px solid var(--color-neutral-900);
  background: var(--color-error);
  color: #fff;
  font-size: 9.5px;
  font-weight: 800;
  line-height: 13px;
  text-align: center;
}

.tb__badge--primary {
  background: var(--color-primary);
}

.tb__bump {
  display: inline-flex;
}

.tb__bump.is-bump {
  animation: tb-bump 0.5s cubic-bezier(0.3, 1.6, 0.5, 1);
}

@keyframes tb-bump {
  30% {
    transform: scale(1.35) translateY(-2px);
  }
  100% {
    transform: none;
  }
}

/* --- Compte --- */
.tb__account {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: 4px;
  padding: 4px 8px 4px 4px;
  border: 1px solid var(--color-divider);
  border-radius: 999px;
  background: var(--color-neutral-900);
  color: inherit;
  cursor: pointer;
  transition: border-color 0.15s ease;
}

.tb__account:hover {
  border-color: var(--color-divider-strong);
}

.tb__avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  border-radius: 50%;
  background: linear-gradient(135deg, #f59e0b, #ea580c);
  color: #fff;
  font-size: 12.5px;
  font-weight: 800;
}

.tb__avatar--lg {
  width: 42px;
  height: 42px;
  font-size: 15px;
}

.tb__who {
  display: none;
  flex-direction: column;
  align-items: flex-start;
  line-height: 1.15;
  max-width: 150px;
}

@media (min-width: 960px) {
  .tb__who {
    display: flex;
  }
}

.tb__name {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 700;
  color: var(--color-neutral-200);
}

.tb__role {
  font-size: 11px;
  color: var(--color-neutral-400);
}

.tb__caret {
  color: var(--color-neutral-500);
}

@media (max-width: 959px) {
  .tb__account {
    padding: 2px;
    border: 0;
    background: none;
  }

  .tb__caret {
    display: none;
  }
}

/* --- Visiteur --- */
.tb__login,
.tb__signup {
  flex-shrink: 0;
  padding: 8px 14px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 700;
  text-decoration: none;
}

.tb__login {
  color: var(--color-primary-300);
}

.tb__signup {
  background: var(--color-primary);
  color: #fff;
}

@media (max-width: 600px) {
  .tb__signup {
    display: none;
  }

  .tb__login {
    border: 1px solid var(--color-divider-strong);
  }
}

/* --- Menu du compte --- */
.tb-menu {
  min-width: 260px;
  padding: 6px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-divider);
  background: var(--color-neutral-900);
  box-shadow: var(--shadow-lg);
}

.tb-menu__head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 10px 12px;
  margin-bottom: 4px;
  border-bottom: 1px solid var(--color-divider);
}

.tb-menu__id {
  display: flex;
  flex-direction: column;
  min-width: 0;
  font-size: 12px;
  color: var(--color-neutral-400);
}

.tb-menu__id strong {
  font-size: 14px;
  color: var(--color-neutral-200);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tb-menu__item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 10px;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  color: var(--color-neutral-300);
  font: inherit;
  font-size: 13.5px;
  font-weight: 600;
  text-align: left;
  text-decoration: none;
  cursor: pointer;
}

.tb-menu__item:hover {
  background: var(--color-neutral-800);
}

.tb-menu__item--accent {
  color: var(--color-primary-300);
}

.tb-menu__item--danger {
  color: var(--color-error);
}

.tb-menu__sep {
  height: 1px;
  margin: 4px 6px;
  background: var(--color-divider);
}

@media (prefers-reduced-motion: reduce) {
  .tb__bump.is-bump {
    animation: none;
  }
}
</style>
