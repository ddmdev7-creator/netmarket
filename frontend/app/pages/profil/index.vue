<script setup lang="ts">
import {
  PhBell,
  PhCaretRight,
  PhChartBar,
  PhCheckCircle,
  PhHeart,
  PhMapPin,
  PhMotorcycle,
  PhPackage,
  PhPencilSimple,
  PhQuestion,
  PhSignOut,
  PhStorefront,
  PhWallet,
  PhWarehouse,
} from '@phosphor-icons/vue'
import type { Component } from 'vue'
import type { BuyerWalletRead, CourierDetailRead, OrderRead } from '~/types/api'

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
// Entrée NdjouriBank : visible si le service est ouvert ou s'il reste un
// solde à dépenser. Chargée sans bloquer la page.
const buyerWallet = ref<BuyerWalletRead | null>(null)
apiFetch<BuyerWalletRead>('/ndjouribank')
  .then((w) => {
    buyerWallet.value = w
  })
  .catch(() => {})
const showWallet = computed(() => !!buyerWallet.value && (buyerWallet.value.enabled || buyerWallet.value.balance > 0))

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

// Compteurs des tuiles (chargés sans bloquer la page).
const favorites = useFavoritesStore()
favorites.ensureLoaded().catch(() => {})
const orders = ref<OrderRead[] | null>(null)
apiFetch<OrderRead[]>('/orders')
  .then((list) => {
    orders.value = list
  })
  .catch(() => {})
const activeOrders = computed(
  () => orders.value?.filter((o) => !['delivered', 'cancelled'].includes(o.status)).length ?? 0,
)

interface Space {
  to: string
  label: string
  hint: string
  icon: Component
  hue: number
}

const role = computed(() => auth.user?.role)
const isPointManager = computed(() => role.value === 'pickup_point_manager' || !!auth.user?.is_pickup_point_manager)

// Espaces professionnels déjà ouverts…
const spaces = computed<Space[]>(() => [
  ...(role.value === 'vendor' ? [{ to: '/vendeur', label: 'Espace vendeur', hint: 'Commandes, produits, gains', icon: PhStorefront, hue: 150 }] : []),
  ...(role.value === 'courier' ? [{ to: '/livreur', label: 'Espace livreur', hint: 'Courses et gains', icon: PhMotorcycle, hue: 30 }] : []),
  ...(isPointManager.value ? [{ to: '/point-retrait', label: 'Point de retrait', hint: 'Colis à remettre', icon: PhWarehouse, hue: 270 }] : []),
  ...(role.value === 'admin' ? [{ to: '/admin', label: 'Administration', hint: 'Pilotage de Netmarket', icon: PhChartBar, hue: 355 }] : []),
])

// …et ceux qu'un acheteur peut rejoindre.
const joinable = computed<Space[]>(() =>
  role.value !== 'buyer'
    ? []
    : [
        { to: '/vendeur/inscription', label: 'Devenir vendeur', hint: 'Ouvrez votre boutique', icon: PhStorefront, hue: 150 },
        { to: '/livreur/inscription', label: 'Devenir livreur', hint: 'Livrez et soyez payé', icon: PhMotorcycle, hue: 30 },
        ...(isPointManager.value
          ? []
          : [{ to: '/point-retrait/candidature', label: 'Devenir point de retrait', hint: 'Accueillez des colis', icon: PhWarehouse, hue: 270 }]),
      ],
)

async function logout() {
  auth.logout()
  cartStore.reset()
  await router.push('/connexion')
}
</script>

<template>
  <div class="pf">
    <!-- En-tête : identité + raccourci d'édition. -->
    <section class="pf-hero">
      <div class="pf-hero__avatar">
        <img v-if="courierPhotoUrl" :src="courierPhotoUrl" alt="Photo de profil" />
        <template v-else>{{ initials }}</template>
      </div>
      <div class="pf-hero__who">
        <h1 class="pf-hero__name">{{ displayName }}</h1>
        <div class="pf-hero__meta">
          <span>{{ auth.user?.phone }}</span>
          <span v-if="auth.user?.email">{{ auth.user.email }}</span>
        </div>
        <span v-if="courierApproved" class="pf-hero__chip">
          <PhCheckCircle :size="12" weight="fill" /> Livreur approuvé
        </span>
      </div>
      <NuxtLink to="/profil/modifier" class="pf-hero__edit" aria-label="Modifier mon profil">
        <PhPencilSimple :size="16" /> <span>Modifier</span>
      </NuxtLink>
    </section>

    <!-- Tuiles : l'essentiel d'un coup d'œil. -->
    <div class="pf-tiles">
      <NuxtLink to="/commandes" class="pf-tile" style="--hue: 215">
        <PhPackage :size="20" weight="duotone" />
        <strong>{{ orders ? orders.length : '—' }}</strong>
        <span>Commandes<template v-if="activeOrders"> · {{ activeOrders }} en cours</template></span>
      </NuxtLink>
      <NuxtLink to="/favoris" class="pf-tile" style="--hue: 350">
        <PhHeart :size="20" weight="duotone" />
        <strong>{{ favorites.count }}</strong>
        <span>Favoris</span>
      </NuxtLink>
      <NuxtLink v-if="showWallet && buyerWallet" to="/ndjouribank" class="pf-tile" style="--hue: 150">
        <PhWallet :size="20" weight="duotone" />
        <strong>{{ formatGnf(buyerWallet.balance) }}</strong>
        <span>NdjouriBank</span>
      </NuxtLink>
      <NuxtLink to="/notifications" class="pf-tile" style="--hue: 38">
        <PhBell :size="20" weight="duotone" />
        <strong>{{ notifications.unreadCount }}</strong>
        <span>Non lue{{ notifications.unreadCount > 1 ? 's' : '' }}</span>
      </NuxtLink>
    </div>

    <div class="pf-cols">
      <section class="pf-section">
        <h2 class="pf-section__title">Mon compte</h2>
        <NuxtLink to="/profil/modifier" class="pf-link">
          <span class="pf-link__icon" style="--hue: 215"><PhPencilSimple :size="17" /></span>
          <span class="pf-link__text"><strong>Informations personnelles</strong><small>Nom, e-mail, mot de passe</small></span>
          <PhCaretRight :size="16" class="pf-link__caret" />
        </NuxtLink>
        <NuxtLink to="/profil/adresses" class="pf-link">
          <span class="pf-link__icon" style="--hue: 150"><PhMapPin :size="17" /></span>
          <span class="pf-link__text"><strong>Mes adresses</strong><small>Domicile et points de retrait</small></span>
          <PhCaretRight :size="16" class="pf-link__caret" />
        </NuxtLink>
        <NuxtLink to="/commandes" class="pf-link">
          <span class="pf-link__icon" style="--hue: 265"><PhPackage :size="17" /></span>
          <span class="pf-link__text"><strong>Mes commandes</strong><small>Suivi et historique</small></span>
          <PhCaretRight :size="16" class="pf-link__caret" />
        </NuxtLink>
        <NuxtLink to="/notifications" class="pf-link">
          <span class="pf-link__icon" style="--hue: 38"><PhBell :size="17" /></span>
          <span class="pf-link__text"><strong>Notifications</strong><small>Commandes, livraisons, promotions</small></span>
          <span v-if="notifications.unreadCount" class="pf-link__badge">{{ notifications.unreadCount }}</span>
          <PhCaretRight v-else :size="16" class="pf-link__caret" />
        </NuxtLink>
        <div class="pf-link pf-link--disabled">
          <span class="pf-link__icon" style="--hue: 200"><PhQuestion :size="17" /></span>
          <span class="pf-link__text"><strong>Aide &amp; support</strong><small>Bientôt disponible</small></span>
        </div>
      </section>

      <div class="pf-side">
        <section v-if="spaces.length" class="pf-section">
          <h2 class="pf-section__title">Mes espaces</h2>
          <NuxtLink v-for="space in spaces" :key="space.to" :to="space.to" class="pf-space" :style="{ '--hue': space.hue }">
            <span class="pf-space__icon"><component :is="space.icon" :size="20" weight="fill" /></span>
            <span class="pf-link__text"><strong>{{ space.label }}</strong><small>{{ space.hint }}</small></span>
            <PhCaretRight :size="16" class="pf-link__caret" />
          </NuxtLink>
        </section>

        <section v-if="joinable.length" class="pf-section">
          <h2 class="pf-section__title">Gagner avec Netmarket</h2>
          <NuxtLink v-for="space in joinable" :key="space.to" :to="space.to" class="pf-link">
            <span class="pf-link__icon" :style="{ '--hue': space.hue }"><component :is="space.icon" :size="17" /></span>
            <span class="pf-link__text"><strong>{{ space.label }}</strong><small>{{ space.hint }}</small></span>
            <PhCaretRight :size="16" class="pf-link__caret" />
          </NuxtLink>
        </section>

        <button type="button" class="pf-logout" @click="logout">
          <PhSignOut :size="18" /> Se déconnecter
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pf {
  max-width: 1040px;
  margin: 0 auto;
  padding: 16px 16px 24px;
}

@media (min-width: 960px) {
  .pf {
    padding: 28px 24px 48px;
  }
}

.pf-hero {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
  border-radius: var(--radius-lg);
  background: linear-gradient(125deg, var(--color-primary), #4f46e5 70%, #7c3aed);
  color: #fff;
  box-shadow: var(--shadow-md);
}

.pf-hero__avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  flex-shrink: 0;
  overflow: hidden;
  border-radius: 50%;
  border: 3px solid rgb(255 255 255 / 0.5);
  background: rgb(255 255 255 / 0.18);
  font-family: var(--font-heading);
  font-size: 22px;
  font-weight: 800;
}

.pf-hero__avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.pf-hero__who {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  gap: 2px;
}

.pf-hero__name {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-heading);
  font-size: 20px;
  font-weight: 800;
}

.pf-hero__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 12px;
  font-size: 13px;
  opacity: 0.88;
}

.pf-hero__chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  align-self: flex-start;
  margin-top: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgb(255 255 255 / 0.2);
  font-size: 11.5px;
  font-weight: 700;
}

.pf-hero__edit {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  padding: 8px 14px;
  border-radius: 999px;
  background: #fff;
  color: var(--color-primary);
  font-size: 13px;
  font-weight: 700;
  text-decoration: none;
}

@media (max-width: 480px) {
  .pf-hero__edit span {
    display: none;
  }

  .pf-hero__edit {
    padding: 10px;
  }
}

.pf-tiles {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin: 14px 0;
}

@media (min-width: 720px) {
  .pf-tiles {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

.pf-tile {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 14px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-divider);
  background: var(--color-neutral-900);
  box-shadow: var(--shadow-sm);
  color: inherit;
  text-decoration: none;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.pf-tile:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.pf-tile svg {
  margin-bottom: 4px;
  color: hsl(var(--hue) 65% 50%);
}

.pf-tile strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-heading);
  font-size: 18px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}

.pf-tile span {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-neutral-400);
}

.pf-cols {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 14px;
}

@media (min-width: 900px) {
  .pf-cols {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    align-items: start;
  }
}

.pf-side {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.pf-section {
  padding: 8px 16px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-divider);
  background: var(--color-neutral-900);
  box-shadow: var(--shadow-sm);
}

.pf-section__title {
  margin: 10px 0 4px;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-neutral-500);
}

.pf-link,
.pf-space {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 11px 0;
  border-top: 1px solid var(--color-divider);
  color: inherit;
  text-decoration: none;
}

.pf-section__title + .pf-link,
.pf-section__title + .pf-space {
  border-top: 0;
}

.pf-link:hover .pf-link__text strong,
.pf-space:hover .pf-link__text strong {
  color: var(--color-primary-300);
}

.pf-link--disabled {
  opacity: 0.55;
}

.pf-link__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  border-radius: 11px;
  background: hsl(var(--hue) 70% var(--tint-bg));
  color: hsl(var(--hue) 60% var(--tint-fg));
}

.pf-space__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  border-radius: 12px;
  background: linear-gradient(135deg, hsl(var(--hue) 70% 50%), hsl(calc(var(--hue) + 30) 70% 45%));
  color: #fff;
}

.pf-link__text {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.pf-link__text strong {
  font-size: 14px;
  font-weight: 700;
}

.pf-link__text small {
  font-size: 12px;
  color: var(--color-neutral-400);
}

.pf-link__caret {
  color: var(--color-neutral-500);
}

.pf-link__badge {
  min-width: 22px;
  padding: 1px 7px;
  border-radius: 999px;
  background: var(--color-primary);
  color: #fff;
  font-size: 11px;
  font-weight: 800;
  text-align: center;
}

.pf-logout {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-divider);
  background: var(--color-neutral-900);
  color: var(--color-error);
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
}

.pf-logout:hover {
  background: hsl(355 80% var(--tint-bg));
}
</style>
