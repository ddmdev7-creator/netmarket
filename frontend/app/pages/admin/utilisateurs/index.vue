<script setup lang="ts">
import { PhEnvelopeSimple, PhKey, PhPhone, PhTrash } from '@phosphor-icons/vue'
import type { UserRead, UserRole } from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const { apiFetch } = useApi()
const toast = useToastStore()
const auth = useAuthStore()

const { data: users, pending, refresh } = await useAsyncData(
  'admin-users',
  () => apiFetch<UserRead[]>('/admin/users'),
  { default: () => [], getCachedData: hydrateThenRefetch },
)

const roleMeta: Record<UserRole, { label: string; color: string }> = {
  buyer: { label: 'Acheteur', color: 'info' },
  vendor: { label: 'Vendeur', color: 'success' },
  courier: { label: 'Livreur', color: 'warning' },
  pickup_point_manager: { label: 'Gestionnaire point retrait', color: 'secondary' },
  admin: { label: 'Administrateur', color: 'error' },
}

const filter = ref<UserRole | 'all'>('all')
const tabs: { value: UserRole | 'all'; label: string }[] = [
  { value: 'all', label: 'Tous' },
  { value: 'buyer', label: 'Acheteurs' },
  { value: 'vendor', label: 'Vendeurs' },
  { value: 'courier', label: 'Livreurs' },
  { value: 'pickup_point_manager', label: 'Points retrait' },
  { value: 'admin', label: 'Admins' },
]

// null quand le champ est vidé par sa croix (clearable).
const search = ref<string | null>('')
const searchTerm = computed(() => (search.value ?? '').trim())

// Insensible à la casse et aux accents ; les espaces du téléphone sont ignorés.
function normalize(value: string): string {
  return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
}

const filteredUsers = computed(() => {
  const term = normalize(searchTerm.value)
  const digits = term.replace(/[\s+]/g, '')
  return users.value.filter((u) => {
    if (filter.value !== 'all' && u.role !== filter.value) return false
    if (!term) return true
    const name = normalize([u.first_name, u.last_name].filter(Boolean).join(' '))
    const email = normalize(u.email ?? '')
    const phone = u.phone.replace(/[\s+]/g, '')
    return name.includes(term) || email.includes(term) || (!!digits && phone.includes(digits))
  })
})

// Pastille d'initiales, teinte par rôle (repère visuel ; le rôle reste écrit
// en clair dans la puce à côté).
const roleAvatar: Record<UserRole, string> = {
  buyer: '#2a78d6',
  vendor: '#199e70',
  courier: '#c98500',
  pickup_point_manager: '#8a5cd6',
  admin: '#d63b3b',
}

function initials(user: UserRead): string {
  const letters = [user.first_name, user.last_name].filter(Boolean).map((part) => part!.trim()[0] ?? '')
  return (letters.join('') || user.phone.slice(-2)).toUpperCase()
}

function displayName(user: UserRead): string {
  const full = [user.first_name, user.last_name].filter(Boolean).join(' ')
  return full || user.phone
}

const confirmDeleteId = ref<string | null>(null)
const deleting = ref(false)
const confirmTarget = computed(() => users.value.find((u) => u.id === confirmDeleteId.value) ?? null)

async function deleteUser() {
  if (!confirmDeleteId.value) return
  deleting.value = true
  try {
    await apiFetch(`/admin/users/${confirmDeleteId.value}`, { method: 'DELETE' })
    await refresh()
    toast.success('Compte supprimé.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de supprimer ce compte.'))
  } finally {
    deleting.value = false
    confirmDeleteId.value = null
  }
}

const resetPasswordId = ref<string | null>(null)
const resetTarget = computed(() => users.value.find((u) => u.id === resetPasswordId.value) ?? null)
const newPassword = ref('')
const resetting = ref(false)

function openResetPassword(userId: string) {
  newPassword.value = ''
  resetPasswordId.value = userId
}

async function resetPassword() {
  if (!resetPasswordId.value) return
  if (newPassword.value.length < 8) {
    toast.error('Le mot de passe doit contenir au moins 8 caractères.')
    return
  }
  resetting.value = true
  try {
    await apiFetch(`/admin/users/${resetPasswordId.value}/password`, {
      method: 'PATCH',
      body: { new_password: newPassword.value },
    })
    toast.success('Mot de passe réinitialisé.')
    resetPasswordId.value = null
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de réinitialiser ce mot de passe.'))
  } finally {
    resetting.value = false
  }
}
</script>

<template>
  <div class="dashboard-shell">
    <h1 class="text-h6 mb-4">Utilisateurs ({{ users.length }})</h1>

    <CommonSearchBar
      v-model="search"
      placeholder="Rechercher par nom, téléphone ou e-mail…"
      :count="filteredUsers.length"
      class="mb-3"
    />

    <v-btn-toggle v-model="filter" mandatory density="comfortable" divided class="mb-4 flex-wrap">
      <v-btn v-for="t in tabs" :key="t.value" :value="t.value" size="small">{{ t.label }}</v-btn>
    </v-btn-toggle>

    <CommonEmptyState
      v-if="!pending && filteredUsers.length === 0"
      :message="searchTerm ? 'Aucun utilisateur ne correspond à cette recherche.' : 'Aucun utilisateur dans cette catégorie.'"
    />

    <div class="user-grid">
      <article v-for="user in filteredUsers" :key="user.id" class="user-card" :class="{ 'user-card--inactive': !user.is_active }">
        <header class="user-card__head">
          <span class="user-card__avatar" :style="{ background: roleAvatar[user.role] }">{{ initials(user) }}</span>
          <v-chip :color="roleMeta[user.role].color" size="x-small" variant="tonal">{{ roleMeta[user.role].label }}</v-chip>
        </header>
        <div class="user-card__name" :title="displayName(user)">{{ displayName(user) }}</div>
        <div class="user-card__line"><PhPhone :size="13" /> {{ user.phone }}</div>
        <div class="user-card__line" :title="user.email ?? ''">
          <PhEnvelopeSimple :size="13" />
          <span class="user-card__ellipsis">{{ user.email ?? 'Pas d’e-mail' }}</span>
        </div>
        <div class="user-card__flags">
          <v-chip v-if="!user.is_active" size="x-small" variant="tonal">Désactivé</v-chip>
          <v-chip v-if="user.email && !user.email_verified" size="x-small" variant="tonal" color="warning">E-mail non vérifié</v-chip>
          <v-chip v-if="user.is_pickup_point_manager && user.role !== 'pickup_point_manager'" size="x-small" variant="tonal" color="secondary">Gère un point</v-chip>
        </div>
        <footer class="user-card__actions">
          <v-btn variant="text" size="small" @click="openResetPassword(user.id)">
            <PhKey :size="15" class="mr-1" /> Mot de passe
          </v-btn>
          <v-btn
            v-if="user.role !== 'admin' && user.id !== auth.user?.id"
            variant="text"
            color="error"
            size="small"
            icon
            aria-label="Supprimer le compte"
            @click="confirmDeleteId = user.id"
          >
            <PhTrash :size="15" />
          </v-btn>
        </footer>
      </article>
    </div>

    <v-dialog :model-value="!!confirmDeleteId" max-width="360" @update:model-value="(v) => !v && (confirmDeleteId = null)">
      <v-card class="pa-5">
        <div class="text-subtitle-1 mb-2">Supprimer ce compte ?</div>
        <p class="text-muted mb-4" style="font-size: 13px">
          Supprime définitivement <strong>{{ confirmTarget ? displayName(confirmTarget) : '' }}</strong> et tout ce
          qui lui est rattaché (boutique et produits si c'est un vendeur, commandes, panier, avis, adresses...).
          Cette action est irréversible.
        </p>
        <div class="d-flex ga-2">
          <v-btn variant="outlined" class="flex-grow-1" @click="confirmDeleteId = null">Annuler</v-btn>
          <v-btn color="error" class="flex-grow-1" :loading="deleting" @click="deleteUser">Supprimer</v-btn>
        </div>
      </v-card>
    </v-dialog>

    <v-dialog :model-value="!!resetPasswordId" max-width="380" @update:model-value="(v) => !v && (resetPasswordId = null)">
      <v-card class="pa-5">
        <div class="text-subtitle-1 mb-2">Réinitialiser le mot de passe</div>
        <p class="text-muted mb-3" style="font-size: 13px">
          Nouveau mot de passe pour <strong>{{ resetTarget ? displayName(resetTarget) : '' }}</strong>
          ({{ resetTarget?.phone }}) — à transmettre à la personne concernée.
        </p>
        <v-text-field
          v-model="newPassword"
          type="text"
          placeholder="8 caractères minimum"
          density="compact"
          variant="outlined"
          class="mb-3"
          autofocus
        />
        <div class="d-flex ga-2">
          <v-btn variant="outlined" class="flex-grow-1" @click="resetPasswordId = null">Annuler</v-btn>
          <v-btn color="primary" class="flex-grow-1" :loading="resetting" @click="resetPassword">Réinitialiser</v-btn>
        </div>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
/* 4 cartes par ligne sur grand écran, moins sur tablette et mobile. */
.user-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
}

@media (min-width: 600px) {
  .user-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (min-width: 960px) {
  .user-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (min-width: 1280px) {
  .user-grid {
    grid-template-columns: repeat(4, 1fr);
  }
}

.user-card {
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-md);
  background: var(--color-neutral-900);
  box-shadow: var(--shadow-sm);
}

.user-card--inactive {
  opacity: 0.65;
}

.user-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}

.user-card__avatar {
  width: 40px;
  height: 40px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  color: #fff;
  font-family: var(--font-heading);
  font-size: 14px;
  font-weight: 800;
}

.user-card__name {
  margin-bottom: 4px;
  font-size: 14.5px;
  font-weight: 800;
  color: var(--color-neutral-200);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-card__line {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  font-size: 12.5px;
  color: var(--color-neutral-400);
}

.user-card__ellipsis {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-card__flags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 8px;
  min-height: 0;
}

.user-card__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: auto;
  padding-top: 10px;
  border-top: 1px solid var(--color-divider);
}
</style>
