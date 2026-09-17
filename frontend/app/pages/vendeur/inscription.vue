<script setup lang="ts">
import { PhArrowLeft, PhMapPin } from '@phosphor-icons/vue'
import type { VendorRead } from '~/types/api'

definePageMeta({ middleware: 'auth', layout: 'blank' })

const auth = useAuthStore()
const router = useRouter()
const { apiFetch } = useApi()
const toast = useToastStore()
const { locating, locate } = useGeolocation()

// Already a vendor (or came back to this page after registering) — nothing
// to do here, send them to whichever step is next.
if (auth.user?.role === 'vendor') {
  await router.replace(auth.user.email_verified ? '/vendeur' : '/vendeur/verification-email')
}

const shopName = ref('')
const zone = ref('')
const email = ref(auth.user?.email ?? '')
const latitude = ref<number | null>(null)
const longitude = ref<number | null>(null)
const submitting = ref(false)

const hasPosition = computed(() => latitude.value !== null && longitude.value !== null)
const positionLabel = computed(() =>
  hasPosition.value ? `${latitude.value!.toFixed(4)}, ${longitude.value!.toFixed(4)}` : '',
)

async function useCurrentPosition() {
  try {
    const position = await locate()
    latitude.value = position.latitude
    longitude.value = position.longitude
    toast.success('Position enregistrée.')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Impossible de récupérer ta position.')
  }
}

async function submit() {
  if (shopName.value.trim().length < 2) {
    toast.error('Le nom de la boutique doit contenir au moins 2 caractères.')
    return
  }
  if (!email.value.trim().includes('@')) {
    toast.error('Indique un email valide — il sert à confirmer la création de la boutique.')
    return
  }
  submitting.value = true
  try {
    await apiFetch<VendorRead>('/vendors/me', {
      method: 'POST',
      body: {
        shop_name: shopName.value.trim(),
        zone: zone.value.trim() || undefined,
        email: email.value.trim(),
        latitude: latitude.value,
        longitude: longitude.value,
      },
    })
    await auth.fetchMe()
    await router.push('/vendeur/verification-email')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de créer la boutique.'))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="app-shell pa-0">
    <div class="d-flex align-center pa-2 ga-2">
      <v-btn icon variant="text" @click="router.back()">
        <PhArrowLeft :size="20" />
      </v-btn>
      <h1 class="text-h6">Devenir vendeur</h1>
      <LayoutHomeLink />
    </div>

    <div class="px-4 pt-2">
      <p class="text-muted mb-5" style="font-size: 13px">
        Crée ta boutique pour publier des produits sur la marketplace. Un code de vérification te sera envoyé par
        email, puis elle devra être validée par un administrateur avant que tu puisses vendre.
      </p>

      <v-form @submit.prevent="submit">
        <label class="field-label">Nom de la boutique</label>
        <v-text-field v-model="shopName" placeholder="Ex: Boutique Conakry Market" class="mb-2" />

        <label class="field-label">Zone (optionnel)</label>
        <v-text-field v-model="zone" placeholder="Ex: Kaloum" class="mb-2" />

        <label class="field-label">Email</label>
        <v-text-field v-model="email" type="email" placeholder="ex: boutique@exemple.com" class="mb-2" />

        <label class="field-label">Position de la boutique (optionnel)</label>
        <p class="text-muted mb-2" style="font-size: 11.5px">
          Utilisée pour proposer la livraison au livreur disponible le plus proche. Modifiable plus tard.
        </p>
        <v-btn color="primary" variant="tonal" block :loading="locating" class="mb-2" @click="useCurrentPosition">
          <PhMapPin :size="17" class="mr-1" />
          {{ hasPosition ? 'Mettre à jour ma position actuelle' : 'Utiliser ma position actuelle' }}
        </v-btn>
        <p class="text-muted mb-2" style="font-size: 11.5px">Ou touche la carte pour placer le repère toi-même.</p>
        <CommonMapPicker v-model:latitude="latitude" v-model:longitude="longitude" class="mb-2" />
        <div v-if="hasPosition" class="mb-4" style="font-size: 12px">
          <span class="text-muted">{{ positionLabel }}</span>
        </div>

        <v-btn type="submit" color="primary" block size="large" class="mt-2" :loading="submitting">Créer ma boutique</v-btn>
      </v-form>
    </div>
  </div>
</template>
