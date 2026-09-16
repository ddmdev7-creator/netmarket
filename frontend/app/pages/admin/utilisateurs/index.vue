<script setup lang="ts">
import { PhKey, PhTrash, PhUsers } from '@phosphor-icons/vue'
import type { UserRead, UserRole } from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const { apiFetch } = useApi()
const toast = useToastStore()
const auth = useAuthStore()

const { data: users, pending, refresh } = await useAsyncData(
  'admin-users',
  () => apiFetch<UserRead[]>('/admin/users'),
  { default: () => [], getCachedData: () => undefined },
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

const filteredUsers = computed(() =>
  filter.value === 'all' ? users.value : users.value.filter((u) => u.role === filter.value),
)

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

    <v-btn-toggle v-model="filter" mandatory density="comfortable" divided class="mb-4 flex-wrap">
      <v-btn v-for="t in tabs" :key="t.value" :value="t.value" size="small">{{ t.label }}</v-btn>
    </v-btn-toggle>

    <CommonEmptyState v-if="!pending && filteredUsers.length === 0" message="Aucun utilisateur dans cette catégorie." />

    <v-card v-for="user in filteredUsers" :key="user.id" class="mb-2 pa-3">
      <div class="d-flex justify-space-between align-center">
        <div class="d-flex align-center ga-2" style="min-width: 0">
          <PhUsers :size="16" color="var(--color-neutral-500)" style="flex: none" />
          <div style="min-width: 0">
            <div class="user-row__name">{{ displayName(user) }}</div>
            <div class="text-muted user-row__contact">
              {{ user.phone }}<span v-if="user.email"> · {{ user.email }}</span>
            </div>
          </div>
        </div>

        <div class="d-flex align-center ga-2" style="flex: none">
          <v-chip :color="roleMeta[user.role].color" size="small" variant="tonal">
            {{ roleMeta[user.role].label }}
          </v-chip>
          <v-btn variant="text" size="small" icon @click="openResetPassword(user.id)">
            <PhKey :size="16" />
          </v-btn>
          <v-btn
            v-if="user.role !== 'admin' && user.id !== auth.user?.id"
            variant="text"
            color="error"
            size="small"
            icon
            @click="confirmDeleteId = user.id"
          >
            <PhTrash :size="16" />
          </v-btn>
        </div>
      </div>
      <v-chip v-if="!user.is_active" color="default" size="x-small" variant="tonal" class="mt-2">Désactivé</v-chip>
    </v-card>

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
.user-row__name {
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-row__contact {
  font-size: 11.5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
