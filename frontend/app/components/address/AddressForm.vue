<script setup lang="ts">
import { PhCheckCircle, PhMapPin } from '@phosphor-icons/vue'
import type { DeliveryType, PickupPointRead } from '~/types/api'

export interface AddressFormValues {
  label: string
  delivery_type: DeliveryType
  zone: string
  pickup_point_id: string | null
  recipient_name: string
  recipient_phone: string
  instructions: string
  latitude: number | null
  longitude: number | null
  is_default: boolean
}

const model = defineModel<AddressFormValues>({ required: true })

const toast = useToastStore()
const auth = useAuthStore()
const { apiFetch } = useApi()
const { locating, locate } = useGeolocation()

// Prérempli avec les infos du compte connecté — seulement si le formulaire
// est vierge (nouvelle adresse), jamais en écrasant une valeur déjà saisie
// ou chargée depuis une adresse existante. Reste librement modifiable : on
// peut très bien faire livrer quelqu'un d'autre. auth.user n'est pas garanti
// déjà chargé selon la page d'origine (le middleware "auth" ne vérifie que
// le token) — on s'assure de le récupérer avant de préremplir.
// Uniquement pour la livraison à domicile : un point de retrait n'a pas de
// destinataire personnel, voir le watcher ci-dessous.
onMounted(async () => {
  if (!auth.user) await auth.fetchMe()
  if (model.value.delivery_type !== 'home_delivery') return
  if (model.value.recipient_name || model.value.recipient_phone) return
  const fullName = [auth.user?.first_name, auth.user?.last_name].filter(Boolean).join(' ')
  if (fullName) model.value.recipient_name = fullName
  if (auth.user?.phone) model.value.recipient_phone = auth.user.phone
})

// Un point de retrait est identifié par ses propres informations (nom,
// zone) — pas par un destinataire personnel : la remise s'y fait au client
// final qui vient chercher son colis lui-même, pas à une personne nommée à
// l'avance. On efface donc ces champs en passant en mode point de retrait,
// pour ne pas figer par erreur les coordonnées personnelles de l'acheteur
// dans une adresse qui doit rester celle du point. À l'inverse, un point de
// retrait n'a pas de sens pour une livraison à domicile — on l'efface aussi.
watch(
  () => model.value.delivery_type,
  (type) => {
    if (type === 'pickup_point') {
      model.value.recipient_name = ''
      model.value.recipient_phone = ''
      // Idem pour zone/position : sans ça, un texte/position saisi avant de
      // basculer en point de retrait reste affiché sous le sélecteur (avant
      // qu'un point soit choisi) et pourrait laisser croire qu'une adresse
      // valide est déjà en place alors qu'aucun point n'a encore été choisi.
      model.value.zone = ''
      model.value.latitude = null
      model.value.longitude = null
    } else {
      model.value.pickup_point_id = null
    }
  },
)

// Les points de retrait sont un annuaire géré par l'admin (précision, lutte
// anti-fraude) — l'acheteur choisit dedans plutôt que de taper une adresse
// libre, contrairement au domicile.
const { data: pickupPoints } = await useAsyncData('address-form-pickup-points', () =>
  apiFetch<PickupPointRead[]>('/pickup-points'), { default: () => [] },
)

function selectPickupPoint(pointId: string | null) {
  model.value.pickup_point_id = pointId
  const point = pickupPoints.value.find((p) => p.id === pointId)
  if (!point) return
  // Le nom du point sert directement de nom d'adresse — pas besoin de le
  // ressaisir, contrairement au domicile où le nom est un choix personnel
  // ("Maison", "Bureau"...).
  model.value.label = point.name
  model.value.zone = `${point.name} — ${point.zone}`
  model.value.latitude = point.latitude
  model.value.longitude = point.longitude
}

const hasPosition = computed(() => model.value.latitude !== null && model.value.longitude !== null)
const isHomeDelivery = computed(() => model.value.delivery_type === 'home_delivery')

// Coordonnées arrondies à ~11m de précision (4 décimales) — largement
// suffisant pour vérifier visuellement qu'on est au bon endroit.
const positionLabel = computed(() =>
  hasPosition.value ? `${model.value.latitude!.toFixed(4)}, ${model.value.longitude!.toFixed(4)}` : '',
)
async function useCurrentPosition() {
  try {
    const { latitude, longitude } = await locate()
    model.value.latitude = latitude
    model.value.longitude = longitude
    toast.success('Position enregistrée.')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Impossible de récupérer votre position.')
  }
}
</script>

<template>
  <div>
    <!-- Pour un point de retrait, le nom du point choisi ci-dessous sert
         directement de nom d'adresse (voir selectPickupPoint) — pas de champ
         séparé à remplir. -->
    <template v-if="isHomeDelivery">
      <label class="field-label">Nom de cette adresse</label>
      <v-text-field v-model="model.label" placeholder="Ex: Maison, Bureau" class="mb-2" />
    </template>

    <label class="field-label">Mode de livraison</label>
    <v-btn-toggle v-model="model.delivery_type" mandatory density="comfortable" divided class="mb-4 d-flex">
      <v-btn value="home_delivery" class="flex-grow-1">Livraison à domicile</v-btn>
      <v-btn value="pickup_point" class="flex-grow-1">Point de retrait</v-btn>
    </v-btn-toggle>

    <!-- Domicile : la position GPS est la source principale, le texte n'est
         qu'un complément optionnel (repère pour le livreur). -->
    <template v-if="isHomeDelivery">
      <v-btn color="primary" block :loading="locating" class="mb-2" @click="useCurrentPosition">
        <PhMapPin :size="17" class="mr-1" />
        {{ hasPosition ? 'Mettre à jour ma position actuelle' : 'Utiliser ma position actuelle' }}
      </v-btn>

      <p class="text-muted mb-2" style="font-size: 11.5px">Ou touchez la carte pour placer le repère vous-même.</p>
      <CommonMapPicker
        v-model:latitude="model.latitude"
        v-model:longitude="model.longitude"
        class="mb-2"
      />

      <div v-if="hasPosition" class="d-flex align-center ga-1 mb-3" style="font-size: 12px">
        <PhCheckCircle :size="14" weight="fill" color="var(--color-success)" />
        <span class="text-muted">{{ positionLabel }}</span>
      </div>
      <v-alert v-else type="warning" variant="tonal" density="compact" class="mb-3">
        Sans position GPS, décris précisément l'endroit ci-dessous.
      </v-alert>

      <label class="field-label">Description / point de repère (optionnel avec une position GPS)</label>
      <v-textarea v-model="model.zone" rows="2" placeholder="Ex: Immeuble bleu, 2ᵉ étage, près du kiosque" class="mb-2" />
    </template>

    <!-- Point de retrait : annuaire géré par l'admin, choix dans la liste
         plutôt que texte libre (précision, cohérence, anti-fraude). -->
    <template v-else>
      <template v-if="pickupPoints.length > 0">
        <label class="field-label">Choisir un point de retrait</label>
        <p class="text-muted mb-2" style="font-size: 11.5px">
          Repérez-vous sur la carte ou recherchez un quartier, puis touchez un point pour voir ses détails.
        </p>
        <CommonPickupPointsMap
          :points="pickupPoints"
          :model-value="model.pickup_point_id"
          class="mb-3"
          @update:model-value="selectPickupPoint"
        />
        <v-select
          :model-value="model.pickup_point_id"
          :items="pickupPoints"
          item-title="name"
          item-value="id"
          placeholder="Sélectionner un point"
          class="mb-1"
          @update:model-value="selectPickupPoint"
        />
        <div v-if="model.zone" class="text-muted mb-3" style="font-size: 12px">{{ model.zone }}</div>
      </template>
      <v-alert v-else type="warning" variant="tonal" density="compact" class="mb-3">
        Aucun point de retrait disponible pour le moment.
      </v-alert>

      <v-alert type="info" variant="tonal" density="compact" class="mb-3">
        Cette adresse affichera uniquement les informations du point de retrait — c'est vous qui viendrez récupérer la commande sur place, pas besoin d'indiquer de destinataire.
      </v-alert>
    </template>

    <template v-if="isHomeDelivery">
      <label class="field-label">Nom du destinataire (optionnel)</label>
      <v-text-field v-model="model.recipient_name" placeholder="Ex: Mamadou Diallo" class="mb-2" />

      <label class="field-label">Téléphone (optionnel)</label>
      <v-text-field v-model="model.recipient_phone" placeholder="+224 6XX XX XX XX" class="mb-2" />
    </template>

    <label class="field-label">Instructions supplémentaires (optionnel)</label>
    <v-textarea v-model="model.instructions" rows="2" placeholder="Ex: Appeler avant d'arriver" class="mb-2" />

    <v-checkbox v-model="model.is_default" label="Définir comme adresse par défaut" density="compact" hide-details class="mb-2" />
  </div>
</template>

