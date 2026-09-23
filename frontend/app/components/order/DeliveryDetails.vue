<script setup lang="ts">
import { PhMapPin, PhUser } from '@phosphor-icons/vue'
import type { DeliveryType, PickupPointContactRead } from '~/types/api'

// Rendu partagé de l'adresse d'une commande, réutilisé partout où une
// commande s'affiche (acheteur, vendeur, livreur, gestionnaire de point) —
// zone/instructions sur leur propre ligne plutôt qu'un seul bloc de texte,
// puis, selon delivery_type, soit le(s) gestionnaire(s) du point de retrait
// (en direct, jamais figé — voir backend _attach_pickup_point_contacts),
// soit le destinataire à domicile (figé, comme le reste de l'adresse).
//
// zone/address : `zone` est le champ structuré (peut être absent sur une
// commande passée avant son ajout) ; `address` est l'ancien texte combiné,
// utilisé en repli.
const props = withDefaults(
  defineProps<{
    zone: string | null
    address: string
    instructions: string | null
    deliveryType: DeliveryType
    recipientName?: string | null
    recipientPhone?: string | null
    pickupPointContacts?: PickupPointContactRead[]
    note?: string | null
    /** false sur le tableau de bord du gestionnaire lui-même : pas besoin de se lister comme son propre contact. */
    showParty?: boolean
    /** false sur le tableau de bord du livreur (voir livreur/index.vue) : ce
     * repli n'apporte rien à quelqu'un qui vient justement déposer le colis
     * à ce point, pas besoin de vérifier qui le réceptionnera. */
    showEmptyManagerNote?: boolean
  }>(),
  {
    recipientName: null,
    recipientPhone: null,
    pickupPointContacts: () => [],
    note: null,
    showParty: true,
    showEmptyManagerNote: true,
  },
)
</script>

<template>
  <div>
    <div class="d-flex ga-2 mb-1" style="font-size: 12.5px">
      <PhMapPin :size="15" class="mt-1 flex-shrink-0" color="var(--color-primary)" />
      <span class="text-muted">{{ props.zone || props.address }}</span>
    </div>
    <div v-if="props.instructions" class="text-muted mb-1" style="font-size: 11.5px; padding-left: 23px">
      Instructions : {{ props.instructions }}
    </div>

    <div v-if="props.showParty" class="text-muted" style="font-size: 11.5px; padding-left: 23px">
      <template v-if="props.deliveryType === 'pickup_point'">
        <div>Point de retrait</div>
        <div v-if="props.pickupPointContacts.length" class="mt-1">
          <div v-for="c in props.pickupPointContacts" :key="c.phone" class="d-flex align-center ga-1">
            <PhUser :size="12" />
            <span>{{ c.name ?? 'Gestionnaire' }} · {{ c.phone }}</span>
          </div>
        </div>
        <div v-else-if="props.showEmptyManagerNote" class="mt-1">Aucun gestionnaire assigné pour l'instant</div>
      </template>
      <template v-else>
        <div>Livraison à domicile</div>
        <div v-if="props.recipientName || props.recipientPhone" class="d-flex align-center ga-1 mt-1">
          <PhUser :size="12" />
          <span>{{ props.recipientName }}<span v-if="props.recipientPhone"> · {{ props.recipientPhone }}</span></span>
        </div>
      </template>
    </div>

    <div v-if="props.note" class="text-muted mt-1" style="font-size: 11px; padding-left: 23px">{{ props.note }}</div>
  </div>
</template>
