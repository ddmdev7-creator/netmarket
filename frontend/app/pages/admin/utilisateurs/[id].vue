<script setup lang="ts">
import {
  PhArrowLeft,
  PhEnvelopeSimple,
  PhKey,
  PhMapPin,
  PhMotorcycle,
  PhPackage,
  PhPhone,
  PhStorefront,
  PhTrash,
  PhWallet,
  PhWarehouse,
} from '@phosphor-icons/vue'
import type { AdminUserProfile, UserRole } from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const toast = useToastStore()
const { apiFetch } = useApi()
const userId = route.params.id as string

const { data: profile, error } = await useAsyncData(`admin-user-${userId}`, () =>
  apiFetch<AdminUserProfile>(`/admin/users/${userId}/profile`),
)

const ROLE_META: Record<UserRole, { label: string; hue: number }> = {
  buyer: { label: 'Acheteur', hue: 215 },
  vendor: { label: 'Vendeur', hue: 150 },
  courier: { label: 'Livreur', hue: 30 },
  pickup_point_manager: { label: 'Gestionnaire de point', hue: 270 },
  admin: { label: 'Administrateur', hue: 355 },
}

const ACCOUNT_STATUS: Record<string, { label: string; tone: string }> = {
  pending: { label: 'En attente', tone: 'warning' },
  approved: { label: 'Validé', tone: 'success' },
  rejected: { label: 'Refusé', tone: 'error' },
  suspended: { label: 'Suspendu', tone: 'error' },
}
const VEHICLES: Record<string, string> = { moto: 'Moto', taxi: 'Taxi', voiture: 'Voiture' }

const name = computed(() => {
  const p = profile.value
  if (!p) return ''
  return [p.first_name, p.last_name].filter(Boolean).join(' ') || p.phone
})
const initials = computed(() => {
  const p = profile.value
  if (!p) return ''
  if (p.first_name) return `${p.first_name[0] ?? ''}${p.last_name?.[0] ?? ''}`.toUpperCase()
  return p.phone.slice(-2)
})
const isSelf = computed(() => profile.value?.id === auth.user?.id)

function formatDate(iso: string | null, withTime = false) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('fr-FR', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    ...(withTime ? { hour: '2-digit', minute: '2-digit' } : {}),
  })
}

// --- Édition -------------------------------------------------------------------

const editOpen = ref(false)
const saving = ref(false)
const form = ref({ first_name: '', last_name: '', email: '' })
function openEdit() {
  const p = profile.value!
  form.value = { first_name: p.first_name ?? '', last_name: p.last_name ?? '', email: p.email ?? '' }
  editOpen.value = true
}
async function save() {
  saving.value = true
  try {
    profile.value = await apiFetch<AdminUserProfile>(`/admin/users/${userId}`, {
      method: 'PATCH',
      body: { first_name: form.value.first_name, last_name: form.value.last_name, email: form.value.email.trim() || null },
    })
    editOpen.value = false
    toast.success('Fiche mise à jour.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible d’enregistrer.'))
  } finally {
    saving.value = false
  }
}

const toggling = ref(false)
async function toggleActive() {
  if (!profile.value) return
  toggling.value = true
  try {
    profile.value = await apiFetch<AdminUserProfile>(`/admin/users/${userId}`, {
      method: 'PATCH',
      body: { is_active: !profile.value.is_active },
    })
    toast.success(profile.value.is_active ? 'Compte réactivé.' : 'Compte désactivé : il ne peut plus se connecter.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de changer le statut du compte.'))
  } finally {
    toggling.value = false
  }
}

// --- Mot de passe et suppression -----------------------------------------------------

const passwordOpen = ref(false)
const newPassword = ref('')
async function resetPassword() {
  try {
    await apiFetch(`/admin/users/${userId}/password`, { method: 'PATCH', body: { new_password: newPassword.value } })
    passwordOpen.value = false
    newPassword.value = ''
    toast.success('Mot de passe réinitialisé.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de réinitialiser le mot de passe.'))
  }
}

const deleteOpen = ref(false)
async function deleteUser() {
  try {
    await apiFetch(`/admin/users/${userId}`, { method: 'DELETE' })
    toast.success('Compte supprimé.')
    await router.push('/admin/utilisateurs')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de supprimer ce compte.'))
  }
}
</script>

<template>
  <div class="dashboard-shell">
    <CommonEmptyState v-if="error" title="Utilisateur introuvable" message="Ce compte n'existe plus." />
    <template v-else-if="profile">
      <header class="pf-head">
        <NuxtLink to="/admin/utilisateurs" class="pf-back" aria-label="Retour aux utilisateurs"><PhArrowLeft :size="18" /></NuxtLink>
        <span class="pf-avatar" :style="{ '--hue': ROLE_META[profile.role].hue }">{{ initials }}</span>
        <div class="pf-title">
          <h1 class="text-h6">{{ name }}</h1>
          <div class="pf-tags">
            <span class="pf-tag pf-tag--primary">{{ ROLE_META[profile.role].label }}</span>
            <span class="pf-tag" :class="profile.is_active ? 'pf-tag--success' : 'pf-tag--error'">
              {{ profile.is_active ? 'Compte actif' : 'Compte désactivé' }}
            </span>
            <span v-if="profile.email && !profile.email_verified" class="pf-tag pf-tag--warning">E-mail non vérifié</span>
            <span class="pf-tag">Inscrit le {{ formatDate(profile.created_at) }}</span>
          </div>
        </div>
        <div class="pf-actions">
          <v-btn variant="tonal" color="primary" @click="openEdit">Modifier</v-btn>
          <v-btn v-if="!isSelf" variant="outlined" :color="profile.is_active ? 'warning' : 'success'" :loading="toggling" @click="toggleActive">
            {{ profile.is_active ? 'Désactiver' : 'Réactiver' }}
          </v-btn>
          <v-btn variant="text" @click="passwordOpen = true"><PhKey :size="16" class="mr-1" /> Mot de passe</v-btn>
          <v-btn v-if="!isSelf && profile.role !== 'admin'" variant="text" color="error" @click="deleteOpen = true">
            <PhTrash :size="16" class="mr-1" /> Supprimer
          </v-btn>
        </div>
      </header>

      <div class="pf-stats">
        <div class="pf-stat"><strong>{{ profile.orders_count }}</strong><span>Commandes</span></div>
        <div class="pf-stat"><strong>{{ formatGnf(profile.orders_total) }}</strong><span>Total commandé</span></div>
        <div class="pf-stat"><strong>{{ profile.last_order_at ? formatDate(profile.last_order_at) : '—' }}</strong><span>Dernière commande</span></div>
        <div v-if="profile.buyer_wallet" class="pf-stat">
          <strong>{{ formatGnf(profile.buyer_wallet.available) }}</strong><span>Solde NdjouriBank</span>
        </div>
      </div>

      <div class="pf-grid">
        <section class="pf-card">
          <h2 class="pf-card__title">Coordonnées</h2>
          <dl class="pf-kv">
            <dt><PhPhone :size="14" /> Téléphone</dt>
            <dd><a :href="`tel:${profile.phone}`">{{ profile.phone }}</a></dd>
            <dt><PhEnvelopeSimple :size="14" /> E-mail</dt>
            <dd>{{ profile.email ?? '—' }}</dd>
            <dt>Prénom</dt>
            <dd>{{ profile.first_name ?? '—' }}</dd>
            <dt>Nom</dt>
            <dd>{{ profile.last_name ?? '—' }}</dd>
          </dl>
        </section>

        <section class="pf-card">
          <h2 class="pf-card__title">Rôles et espaces liés</h2>
          <ul class="pf-list">
            <NuxtLink v-if="profile.vendor" to="/admin/vendeurs" class="pf-row">
              <PhStorefront :size="18" />
              <span class="pf-row__main"><strong>{{ profile.vendor.shop_name }}</strong><small>Boutique · {{ profile.vendor.zone ?? 'zone non renseignée' }}</small></span>
              <span class="pf-tag" :class="`pf-tag--${ACCOUNT_STATUS[profile.vendor.status]?.tone}`">{{ ACCOUNT_STATUS[profile.vendor.status]?.label ?? profile.vendor.status }}</span>
            </NuxtLink>
            <NuxtLink v-if="profile.courier" :to="`/admin/livreurs/${profile.courier.id}`" class="pf-row">
              <PhMotorcycle :size="18" />
              <span class="pf-row__main"><strong>Fiche livreur</strong><small>{{ VEHICLES[profile.courier.vehicle_type] ?? profile.courier.vehicle_type }} · {{ profile.courier.is_online ? 'en ligne' : 'hors ligne' }}</small></span>
              <span class="pf-tag" :class="`pf-tag--${ACCOUNT_STATUS[profile.courier.status]?.tone}`">{{ ACCOUNT_STATUS[profile.courier.status]?.label ?? profile.courier.status }}</span>
            </NuxtLink>
            <NuxtLink v-if="profile.managed_point" :to="`/admin/points-retrait/${profile.managed_point.pickup_point_id}`" class="pf-row">
              <PhWarehouse :size="18" />
              <span class="pf-row__main"><strong>{{ profile.managed_point.name }}</strong><small>Gère ce point de retrait</small></span>
            </NuxtLink>
            <li v-if="!profile.vendor && !profile.courier && !profile.managed_point" class="pf-empty">Aucun espace professionnel lié.</li>
          </ul>
        </section>

        <section class="pf-card">
          <h2 class="pf-card__title"><span><PhPackage :size="16" /> Dernières commandes</span></h2>
          <ul class="pf-list">
            <NuxtLink v-for="o in profile.recent_orders" :key="o.id" :to="`/admin/commandes/${o.id}`" class="pf-row">
              <span class="pf-row__main">
                <OrderNumber :id="o.id" />
                <small>{{ formatDate(o.created_at, true) }} · {{ o.item_count }} article{{ o.item_count > 1 ? 's' : '' }}</small>
              </span>
              <strong>{{ formatGnf(o.total) }}</strong>
              <StatusBadge :status="o.status" />
            </NuxtLink>
            <li v-if="!profile.recent_orders.length" class="pf-empty">Aucune commande.</li>
          </ul>
        </section>

        <section class="pf-card">
          <h2 class="pf-card__title"><span><PhMapPin :size="16" /> Adresses</span></h2>
          <ul class="pf-list">
            <li v-for="(a, i) in profile.addresses" :key="i" class="pf-row">
              <span class="pf-row__main">
                <strong>{{ a.label }}<template v-if="a.is_default"> · par défaut</template></strong>
                <small>{{ a.delivery_type === 'pickup_point' ? 'Point de retrait' : 'Domicile' }} · {{ a.zone || 'Position GPS' }}</small>
              </span>
            </li>
            <li v-if="!profile.addresses.length" class="pf-empty">Aucune adresse enregistrée.</li>
          </ul>
          <p v-if="profile.buyer_wallet" class="pf-empty mt-3">
            <PhWallet :size="14" /> NdjouriBank : {{ formatGnf(profile.buyer_wallet.available) }} disponibles
          </p>
        </section>
      </div>

      <v-dialog v-model="editOpen" max-width="460">
        <v-card class="pa-5">
          <h2 class="text-subtitle-1 mb-4">Modifier la fiche</h2>
          <div class="pf-form">
            <v-text-field v-model="form.first_name" label="Prénom" hide-details />
            <v-text-field v-model="form.last_name" label="Nom" hide-details />
          </div>
          <v-text-field v-model="form.email" label="E-mail" type="email" class="mt-3" hint="Un nouvel e-mail devra être vérifié." persistent-hint />
          <div class="d-flex ga-2 mt-4">
            <v-btn variant="outlined" class="flex-grow-1" @click="editOpen = false">Annuler</v-btn>
            <v-btn color="primary" class="flex-grow-1" :loading="saving" @click="save">Enregistrer</v-btn>
          </div>
        </v-card>
      </v-dialog>

      <v-dialog v-model="passwordOpen" max-width="400">
        <v-card class="pa-5">
          <h2 class="text-subtitle-1 mb-3">Nouveau mot de passe</h2>
          <v-text-field v-model="newPassword" label="Mot de passe (8 caractères minimum)" type="password" hide-details />
          <div class="d-flex ga-2 mt-4">
            <v-btn variant="outlined" class="flex-grow-1" @click="passwordOpen = false">Annuler</v-btn>
            <v-btn color="primary" class="flex-grow-1" :disabled="newPassword.length < 8" @click="resetPassword">Enregistrer</v-btn>
          </div>
        </v-card>
      </v-dialog>

      <v-dialog v-model="deleteOpen" max-width="380">
        <v-card class="pa-5">
          <h2 class="text-subtitle-1 mb-2">Supprimer ce compte ?</h2>
          <p class="text-muted mb-4" style="font-size: 13px">Action définitive. Pour bloquer l'accès sans rien perdre, désactivez plutôt le compte.</p>
          <div class="d-flex ga-2">
            <v-btn variant="outlined" class="flex-grow-1" @click="deleteOpen = false">Annuler</v-btn>
            <v-btn color="error" class="flex-grow-1" @click="deleteUser">Supprimer</v-btn>
          </div>
        </v-card>
      </v-dialog>
    </template>
  </div>
</template>
