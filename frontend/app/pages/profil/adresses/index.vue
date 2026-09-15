<script setup lang="ts">
import { PhArrowLeft, PhCaretRight, PhPlus, PhStar, PhTrash } from '@phosphor-icons/vue'
import type { AddressRead } from '~/types/api'

definePageMeta({ middleware: 'auth', layout: 'blank' })

const router = useRouter()
const { apiFetch } = useApi()
const toast = useToastStore()

const { data: addresses, pending, refresh } = await useAsyncData(
  'my-addresses',
  () => apiFetch<AddressRead[]>('/addresses'),
  { default: () => [], getCachedData: () => undefined },
)

const updatingId = ref<string | null>(null)

async function setDefault(address: AddressRead) {
  updatingId.value = address.id
  try {
    await apiFetch(`/addresses/${address.id}`, { method: 'PATCH', body: { is_default: true } })
    await refresh()
    toast.success('Adresse par défaut mise à jour.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de mettre à jour cette adresse.'))
  } finally {
    updatingId.value = null
  }
}

const confirmDeleteId = ref<string | null>(null)
const deleting = ref(false)
async function deleteAddress() {
  if (!confirmDeleteId.value) return
  deleting.value = true
  try {
    await apiFetch(`/addresses/${confirmDeleteId.value}`, { method: 'DELETE' })
    await refresh()
    toast.success('Adresse supprimée.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de supprimer cette adresse.'))
  } finally {
    deleting.value = false
    confirmDeleteId.value = null
  }
}
</script>

<template>
  <div class="app-shell pa-0" style="padding-bottom: 32px">
    <div class="d-flex align-center pa-2 ga-2">
      <v-btn icon variant="text" @click="router.back()">
        <PhArrowLeft :size="20" />
      </v-btn>
      <h1 class="text-h6">Mes adresses</h1>
      <LayoutHomeLink />
    </div>

    <div class="px-4">
      <v-btn color="primary" block class="mb-4" to="/profil/adresses/nouvelle">
        <PhPlus :size="18" class="mr-1" />
        Nouvelle adresse
      </v-btn>

      <CommonEmptyState v-if="!pending && addresses.length === 0" message="Aucune adresse enregistrée pour l'instant." />

      <v-card v-for="a in addresses" :key="a.id" class="mb-3 pa-0">
        <NuxtLink :to="`/profil/adresses/${a.id}`" class="address-card-link">
          <div class="flex-grow-1">
            <div class="d-flex align-center ga-2 mb-1">
              <span style="font-weight: 600">{{ a.label }}</span>
              <v-chip v-if="a.is_default" color="primary" size="x-small" variant="tonal">
                <PhStar :size="11" weight="fill" class="mr-1" />
                Par défaut
              </v-chip>
            </div>
            <div class="address-card-type mb-1">
              {{ a.delivery_type === 'pickup_point' ? 'Point de retrait' : 'Livraison à domicile' }}
            </div>
            <p class="text-muted mb-0" style="font-size: 13px">{{ a.zone }}</p>
          </div>
          <PhCaretRight :size="16" color="var(--color-neutral-600)" class="flex-shrink-0" />
        </NuxtLink>

        <div class="d-flex ga-2 pa-3 pt-0">
          <v-btn
            v-if="!a.is_default"
            variant="outlined"
            size="small"
            class="flex-grow-1"
            :loading="updatingId === a.id"
            @click="setDefault(a)"
          >
            Définir par défaut
          </v-btn>
          <v-btn variant="outlined" color="error" size="small" :class="{ 'flex-grow-1': a.is_default }" @click="confirmDeleteId = a.id">
            <PhTrash :size="15" />
          </v-btn>
        </div>
      </v-card>
    </div>

    <v-dialog :model-value="!!confirmDeleteId" max-width="340" @update:model-value="(v) => !v && (confirmDeleteId = null)">
      <v-card class="pa-5">
        <div class="text-subtitle-1 mb-2">Supprimer cette adresse ?</div>
        <p class="text-muted mb-4" style="font-size: 13px">Cette action est définitive.</p>
        <div class="d-flex ga-2">
          <v-btn variant="outlined" class="flex-grow-1" @click="confirmDeleteId = null">Annuler</v-btn>
          <v-btn color="error" class="flex-grow-1" :loading="deleting" @click="deleteAddress">Supprimer</v-btn>
        </div>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.address-card-link {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  text-decoration: none;
  color: inherit;
}

.address-card-type {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--color-primary-300);
  opacity: 0.85;
}
</style>
