<script setup lang="ts">
import {
  PhBell,
  PhCaretRight,
  PhChartBar,
  PhMapPin,
  PhMotorcycle,
  PhPackage,
  PhPencilSimple,
  PhCheckCircle,
  PhQuestion,
  PhSignOut,
  PhStorefront,
} from '@phosphor-icons/vue'
import type { CourierDetailRead } from '~/types/api'

definePageMeta({ middleware: 'auth' })

const auth = useAuthStore()
const cartStore = useCartStore()
const notifications = useNotificationStore()
const router = useRouter()
const { apiFetch, apiFetchBlob } = useApi()

await useAsyncData('profil-me', () => auth.fetchMe())

// Photo de vérification du livreur (voir CourierDetailRead.face_photo_key),
// réutilisée comme photo de profil plutôt que les initiales par défaut --
// mais seulement une fois son compte approuvé : avant ça, cette photo n'est
// qu'une pièce de vérification en cours d'examen, pas encore "sa" photo de
// profil. Chargée à part (pas de blocage du rendu de la page si l'appel
// échoue) : /couriers/{id}/documents/{key} n'est jamais public, contrairement
// aux photos produit (voir resolveImageUrl), donc pas de simple <img src>.
const courierPhotoUrl = ref<string | null>(null)
const courierApproved = ref(false)
if (auth.user?.role === 'courier') {
  apiFetch<CourierDetailRead>('/couriers/me')
    .then((courier) => {
      courierApproved.value = courier.status === 'approved'
      if (courier.status === 'approved' && courier.face_photo_key) {
        return apiFetchBlob(`/couriers/${courier.id}/documents/${courier.face_photo_key}`)
      }
      return null
    })
    .then((blob) => {
      if (blob) courierPhotoUrl.value = URL.createObjectURL(blob)
    })
    .catch(() => {
      // Pas grave — l'avatar retombe sur les initiales.
    })
}
onBeforeUnmount(() => {
  if (courierPhotoUrl.value) URL.revokeObjectURL(courierPhotoUrl.value)
})

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
  <!-- Pas de .app-shell ici : layouts/default.vue en fournit déjà un (avec
       app-shell--catalog pour cette route, voir ce fichier) -- un deuxième
       wrapper imbriqué ici l'aurait juste re-plafonné à 720px par défaut,
       annulant l'élargissement du bandeau du haut au-dessus. .detail-card
       (voir main.css -- motif partagé avec adresses/notifications/etc.)
       recentre LE CONTENU de cette page en une carte détachée du fond, sans
       replafonner LayoutTopBar avec -- impose son propre padding (plus de
       .pa-4 ici), la marge sous la bottom nav mobile vient déjà de
       .buyer-shell (layouts/default.vue). -->
  <div class="detail-card">
    <h1 class="text-h6 mb-4">Profil</h1>

    <div class="d-flex align-center ga-3 mb-4">
      <div class="avatar">
        <img v-if="courierPhotoUrl" :src="courierPhotoUrl" alt="Photo de profil" class="avatar__photo" />
        <template v-else>{{ initials }}</template>
      </div>
      <div>
        <div class="d-flex align-center ga-2">
          <span class="text-body">{{ displayName }}</span>
          <v-chip v-if="courierApproved" size="x-small" color="success" variant="tonal">
            <PhCheckCircle :size="12" weight="fill" class="mr-1" />
            Livreur approuvé
          </v-chip>
        </div>
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
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--color-primary-800);
  color: var(--color-primary-100);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  font-family: var(--font-heading);
  font-size: 18px;
}

.avatar__photo {
  width: 100%;
  height: 100%;
  object-fit: cover;
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

/* Distinct de .list-item tout court (couleur d'icône seule ne suffisait
   pas : "Mes commandes"/"Devenir vendeur" utilisent la même teinte neutre
   pour leur icône alors qu'ils sont bien cliquables) -- l'opacité réduite
   et l'absence de chevron signalent sans ambiguïté que cette ligne ne mène
   nulle part pour l'instant. */
.list-item--disabled {
  color: var(--color-neutral-400);
  opacity: 0.6;
  cursor: default;
}
</style>
