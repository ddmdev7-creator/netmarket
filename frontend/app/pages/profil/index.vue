<script setup lang="ts">
import {
  PhBell,
  PhCaretRight,
  PhChartBar,
  PhMapPin,
  PhMotorcycle,
  PhPackage,
  PhPencilSimple,
  PhQuestion,
  PhSignOut,
  PhStorefront,
} from '@phosphor-icons/vue'

definePageMeta({ middleware: 'auth' })

const auth = useAuthStore()
const cartStore = useCartStore()
const notifications = useNotificationStore()
const router = useRouter()

await useAsyncData('profil-me', () => auth.fetchMe())

const initials = computed(() => {
  const u = auth.user
  if (u?.first_name || u?.last_name) {
    return `${u.first_name?.[0] ?? ''}${u.last_name?.[0] ?? ''}`.toUpperCase()
  }
  return (u?.phone ?? '').slice(-2)
})

const displayName = computed(() => {
  const u = auth.user
  if (!u) return ''
  const full = [u.first_name, u.last_name].filter(Boolean).join(' ')
  return full || u.phone
})

async function logout() {
  auth.logout()
  cartStore.reset()
  await router.push('/connexion')
}
</script>

<template>
  <div class="app-shell pa-4" style="padding-bottom: 76px">
    <h1 class="text-h6 mb-4">Profil</h1>

    <div class="d-flex align-center ga-3 mb-4">
      <div class="avatar">{{ initials }}</div>
      <div>
        <div class="text-body">{{ displayName }}</div>
        <div class="text-muted text-meta">{{ auth.user?.phone }}</div>
      </div>
    </div>

    <NuxtLink to="/profil/modifier" class="list-item">
      <PhPencilSimple :size="18" color="var(--color-primary)" />
      <span>Modifier mon profil</span>
      <PhCaretRight :size="16" color="var(--color-neutral-600)" class="ml-auto" />
    </NuxtLink>

    <NuxtLink to="/profil/adresses" class="list-item">
      <PhMapPin :size="18" color="var(--color-primary)" />
      <span>Mes adresses</span>
      <PhCaretRight :size="16" color="var(--color-neutral-600)" class="ml-auto" />
    </NuxtLink>

    <v-divider class="mb-1" />

    <NuxtLink to="/commandes" class="list-item">
      <PhPackage :size="18" color="var(--color-neutral-400)" />
      <span>Mes commandes</span>
      <PhCaretRight :size="16" color="var(--color-neutral-600)" class="ml-auto" />
    </NuxtLink>

    <NuxtLink v-if="auth.user?.role === 'vendor'" to="/vendeur" class="list-item">
      <PhStorefront :size="18" color="var(--color-neutral-400)" />
      <span>Mon espace vendeur</span>
      <PhCaretRight :size="16" color="var(--color-neutral-600)" class="ml-auto" />
    </NuxtLink>
    <NuxtLink v-else-if="auth.user?.role === 'buyer'" to="/vendeur/inscription" class="list-item">
      <PhStorefront :size="18" color="var(--color-neutral-400)" />
      <span>Devenir vendeur</span>
      <PhCaretRight :size="16" color="var(--color-neutral-600)" class="ml-auto" />
    </NuxtLink>

    <NuxtLink v-if="auth.user?.role === 'courier'" to="/livreur" class="list-item">
      <PhMotorcycle :size="18" color="var(--color-neutral-400)" />
      <span>Mon espace livreur</span>
      <PhCaretRight :size="16" color="var(--color-neutral-600)" class="ml-auto" />
    </NuxtLink>
    <NuxtLink v-else-if="auth.user?.role === 'buyer'" to="/livreur/inscription" class="list-item">
      <PhMotorcycle :size="18" color="var(--color-neutral-400)" />
      <span>Devenir livreur</span>
      <PhCaretRight :size="16" color="var(--color-neutral-600)" class="ml-auto" />
    </NuxtLink>

    <!-- Pas de "Devenir gestionnaire" : ces comptes sont créés uniquement par
         l'admin (voir /admin/points-retrait), pas d'auto-inscription. -->
    <NuxtLink v-if="auth.user?.role === 'pickup_point_manager'" to="/point-retrait" class="list-item">
      <PhPackage :size="18" color="var(--color-neutral-400)" />
      <span>Mon espace point de retrait</span>
      <PhCaretRight :size="16" color="var(--color-neutral-600)" class="ml-auto" />
    </NuxtLink>

    <NuxtLink v-if="auth.user?.role === 'admin'" to="/admin" class="list-item">
      <PhChartBar :size="18" color="var(--color-neutral-400)" />
      <span>Espace admin</span>
      <PhCaretRight :size="16" color="var(--color-neutral-600)" class="ml-auto" />
    </NuxtLink>

    <NuxtLink to="/notifications" class="list-item">
      <PhBell :size="18" color="var(--color-neutral-400)" />
      <span>Notifications</span>
      <v-chip v-if="notifications.unreadCount > 0" size="x-small" color="primary" class="ml-auto">
        {{ notifications.unreadCount }}
      </v-chip>
      <PhCaretRight v-else :size="16" color="var(--color-neutral-600)" class="ml-auto" />
    </NuxtLink>

    <div class="list-item list-item--disabled">
      <PhQuestion :size="18" color="var(--color-neutral-400)" />
      <span>Aide &amp; support</span>
      <v-chip size="x-small" variant="tonal" class="ml-auto">Bientôt</v-chip>
    </div>

    <v-divider class="my-2" />

    <button class="list-item" style="color: var(--color-primary-300); width: 100%; text-align: left" @click="logout">
      <PhSignOut :size="18" color="var(--color-primary-300)" />
      <span>Se déconnecter</span>
    </button>
  </div>
</template>

<style scoped>
.avatar {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: var(--color-primary-800);
  color: var(--color-primary-100);
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-heading);
  font-size: 18px;
}

.list-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 13px 0;
  font-size: 13.5px;
  text-decoration: none;
  color: inherit;
  border: none;
  background: none;
}

.list-item--disabled {
  color: var(--color-neutral-400);
}
</style>
