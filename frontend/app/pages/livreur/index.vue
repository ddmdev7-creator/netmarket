<script setup lang="ts">
import { PhCheckCircle, PhMagnifyingGlass, PhQrCode } from '@phosphor-icons/vue'
import type { CourierDetailRead, CourierSubOrderRead } from '~/types/api'

definePageMeta({ middleware: 'courier', layout: 'livreur' })

const { apiFetch } = useApi()
const toast = useToastStore()
const { locating, locate } = useGeolocation()

const { data: deliveries, pending, refresh } = await useAsyncData(
  'courier-deliveries',
  () => apiFetch<CourierSubOrderRead[]>('/orders/courier-deliveries'),
  { default: () => [], getCachedData: hydrateThenRefetch },
)

// Temps réel : toute notification reçue pendant que la page est ouverte
// (nouvelle affectation, statut d'une livraison…) relit la liste — la
// demande de livraison acceptée depuis la fenêtre la rafraîchit aussi
// (refreshNuxtData('courier-deliveries') dans DeliveryRequestModal).
const notifications = useNotificationStore()
watch(
  () => notifications.items[0]?.id,
  (id, previous) => {
    if (id && id !== previous) refresh()
  },
)

const { data: myCourier } = await useAsyncData(
  'courier-me-availability',
  () => apiFetch<CourierDetailRead>('/couriers/me'),
  { getCachedData: hydrateThenRefetch },
)
const isOnline = ref(false)
const togglingAvailability = ref(false)
watch(myCourier, (c) => { if (c) isOnline.value = c.is_online }, { immediate: true })

async function toggleAvailability(value: boolean) {
  togglingAvailability.value = true
  try {
    let position: { latitude: number; longitude: number } | null = null
    if (value) {
      try {
        position = await locate()
      } catch (e) {
        // Erreur de géolocalisation (message déjà en français, voir
        // useGeolocation) — distincte d'une erreur API, pas de fallback
        // générique à appliquer ici.
        toast.error(e instanceof Error ? e.message : 'Impossible de récupérer ta position.')
        isOnline.value = false
        return
      }
    }

    const updated = await apiFetch<CourierDetailRead>('/couriers/me/availability', {
      method: 'PATCH',
      body: value ? { is_online: true, latitude: position!.latitude, longitude: position!.longitude } : { is_online: false },
    })
    isOnline.value = updated.is_online
    if (value) toast.success('Tu es maintenant disponible pour recevoir des livraisons.')
  } catch (e) {
    isOnline.value = !value // repli visuel : l'appel a échoué, le switch ne doit pas rester sur la valeur non confirmée
    toast.error(apiErrorMessage(e, 'Impossible de mettre à jour ta disponibilité.'))
  } finally {
    togglingAvailability.value = false
  }
}

const scannerOpen = ref(false)

// La remise au client se confirme uniquement par scan de son QR (aucun
// bouton manuel — voir backend update_sub_order_status).
async function handleDecode(code: string) {
  try {
    const updated = await apiFetch<CourierSubOrderRead>('/orders/sub-orders/confirm-delivery', {
      method: 'POST',
      body: { code },
    })
    await refresh()
    toast.success(`Livraison confirmée — ${shortId(updated.order_id)}.`)
  } catch (e) {
    toast.error(apiErrorMessage(e, 'QR code invalide ou expiré.'))
  }
}

function shortId(orderId: string) {
  return `#GN-${orderId.slice(0, 5).toUpperCase()}`
}
function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

// Résumé d'une ligne plutôt que le détail de chaque article (nom + variante
// + quantité) : utile pour vérifier le colis au retrait, pas pour un simple
// coup d'œil sur la carte -- les deux ou trois premiers noms suffisent à
// reconnaître la commande.
function itemsSummary(so: CourierSubOrderRead): string {
  const names = so.items.map((i) => i.product_name)
  if (names.length <= 2) return names.join(', ')
  return `${names.slice(0, 2).join(', ')} +${names.length - 2}`
}

// La liste (toute l'historique assigné à ce livreur, jamais paginée côté
// API) devenait vite un long défilement une fois quelques dizaines de
// livraisons terminées accumulées — séparées en deux onglets comme
// commandes/index.vue (acheteur), "À livrer" reste court et concentré sur
// ce qui demande une action.
const tab = ref<'ongoing' | 'done'>('ongoing')
const ongoing = computed(() => deliveries.value.filter((so) => !['delivered', 'cancelled'].includes(so.status)))
const done = computed(() => deliveries.value.filter((so) => ['delivered', 'cancelled'].includes(so.status)))

const search = ref('')
const visible = computed(() => {
  const list = tab.value === 'ongoing' ? ongoing.value : done.value
  const query = search.value.trim().toLowerCase()
  if (!query) return list
  return list.filter((so) =>
    [shortId(so.order_id), so.shop_name, so.delivery_address, so.recipient_name ?? '']
      .join(' ')
      .toLowerCase()
      .includes(query),
  )
})
</script>

<template>
  <!-- Pas de .app-shell ici : layouts/livreur.vue en fournit déjà un (avec
       app-shell--catalog, voir ce fichier) -- un deuxième wrapper imbriqué
       ici replafonnerait à 720px, annulant l'élargissement du bandeau du
       haut. .livreur-inner recentre LE CONTENU sur une largeur confortable
       (même motif que .cart-inner, panier.vue) : les livraisons deviennent
       une vraie grille de cartes (auto-fill) plutôt qu'un unique bloc où
       tout s'empile dans un long défilement continu. -->
  <div class="livreur-inner" style="padding-bottom: 76px">
    <div class="px-4 pt-3">
      <div class="d-flex justify-space-between align-center flex-wrap ga-2 mb-1">
        <div class="d-flex align-center ga-2 flex-wrap">
          <h1 class="text-h6 mb-0" style="white-space: nowrap">Mes livraisons</h1>
          <v-chip v-if="myCourier?.status === 'approved'" size="x-small" color="success" variant="tonal">
            <PhCheckCircle :size="12" weight="fill" class="mr-1" />
            Approuvé
          </v-chip>
        </div>
        <div class="d-flex align-center ga-2">
          <span class="text-muted text-meta">{{ isOnline ? 'Disponible' : 'Indisponible' }}</span>
          <v-switch
            :model-value="isOnline"
            color="primary"
            density="compact"
            hide-details
            :loading="togglingAvailability || locating"
            :disabled="togglingAvailability || locating"
            @update:model-value="toggleAvailability"
          />
        </div>
      </div>

      <v-alert v-if="myCourier && myCourier.status !== 'approved'" type="warning" variant="tonal" density="compact" class="mb-3">
        <template v-if="myCourier.status === 'pending'">Ton profil est en cours de vérification par un administrateur.</template>
        <template v-else-if="myCourier.status === 'rejected'">Ton profil a été rejeté{{ myCourier.admin_note ? ` — ${myCourier.admin_note}` : '' }}.</template>
        <template v-else>Ton compte est suspendu.</template>
      </v-alert>

      <template v-if="!pending && deliveries.length > 0">
        <v-btn-toggle v-model="tab" mandatory density="comfortable" divided class="mb-3">
          <v-btn value="ongoing">À livrer ({{ ongoing.length }})</v-btn>
          <v-btn value="done">Terminées ({{ done.length }})</v-btn>
        </v-btn-toggle>

        <v-text-field
          v-model="search"
          placeholder="Rechercher par commande, boutique, adresse…"
          density="compact"
          variant="solo-filled"
          hide-details
          clearable
          class="livreur-search mb-4"
        >
          <template #prepend-inner>
            <PhMagnifyingGlass :size="16" color="var(--color-neutral-500)" />
          </template>
        </v-text-field>
      </template>

      <CommonEmptyState v-if="!pending && deliveries.length === 0" message="Aucune livraison assignée pour le moment." />
      <CommonEmptyState
        v-else-if="!pending && visible.length === 0"
        :message="tab === 'ongoing' ? 'Aucune livraison à livrer pour le moment.' : 'Aucune livraison ne correspond à cette recherche.'"
      />
    </div>

    <!-- À livrer : une carte par livraison, détail complet -- c'est ce qui
         demande une action. -->
    <div v-if="tab === 'ongoing'" class="px-4 deliveries-grid">
      <div v-for="so in visible" :key="so.id" class="delivery-card grid-card">
        <div class="d-flex justify-space-between align-center mb-2">
          <span class="delivery-card__code">{{ shortId(so.order_id) }}</span>
          <StatusBadge :status="so.status" />
        </div>
        <div class="mb-2">
          <span class="delivery-card__shop">{{ so.shop_name }}</span>
          <span class="delivery-card__date"> · {{ formatDate(so.created_at) }}</span>
        </div>

        <div class="delivery-card__items mb-3">
          {{ so.items.length }} article{{ so.items.length > 1 ? 's' : '' }}
          <span class="delivery-card__items-list"> — {{ itemsSummary(so) }}</span>
        </div>

        <OrderDeliveryDetails
          class="mb-3"
          :zone="so.delivery_zone"
          :address="so.delivery_address"
          :instructions="so.delivery_instructions"
          :delivery-type="so.delivery_type"
          :recipient-name="so.recipient_name"
          :recipient-phone="so.recipient_phone"
          :pickup-point-contacts="so.pickup_point_contacts"
          :show-empty-manager-note="false"
        />

        <template v-if="so.status === 'shipped' && so.delivery_type === 'pickup_point'">
          <div v-if="so.dropoff_handoff_ready" class="qr-block mb-2">
            <div class="qr-block__label">
              <PhQrCode :size="15" weight="bold" />
              Code de dépôt — à faire scanner par le point
            </div>
            <OrderDeliveryQrCode :sub-order-id="so.id" />
          </div>
        </template>

        <div v-else-if="so.status === 'shipped'" class="d-flex ga-2">
          <v-btn color="primary" size="small" class="flex-grow-1" @click="scannerOpen = true">
            <PhQrCode :size="16" class="mr-1" />
            Scanner le QR du client
          </v-btn>
        </div>
      </div>
    </div>

    <!-- Terminées : cartes compactes, rien n'y est plus actionnable --
         inutile de réafficher l'adresse/les instructions complètes pour un
         historique. -->
    <div v-else class="px-4 deliveries-grid deliveries-grid--compact">
      <div v-for="so in visible" :key="so.id" class="delivery-card delivery-card--compact grid-card">
        <div class="d-flex justify-space-between align-center">
          <span class="delivery-card__code">{{ shortId(so.order_id) }}</span>
          <StatusBadge :status="so.status" />
        </div>
        <div class="mt-1">
          <span class="delivery-card__shop delivery-card__shop--compact">{{ so.shop_name }}</span>
          <span class="delivery-card__date"> · {{ formatDate(so.created_at) }} · {{ so.items.length }} article{{ so.items.length > 1 ? 's' : '' }}</span>
        </div>
      </div>
    </div>

    <VendorQrScannerDialog v-model="scannerOpen" @decode="handleDecode" />
  </div>
</template>

<style scoped>
/* .app-shell plafonne à 720px par défaut (voir main.css) -- trop étroit
   pour que la grille de cartes ci-dessous profite de plusieurs colonnes sur
   grand écran. Même largeur que .cart-inner (panier.vue). */
@media (min-width: 960px) {
  .livreur-inner {
    max-width: 1120px;
    margin: 0 auto;
  }
}

.deliveries-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 14px;
}

@media (min-width: 960px) {
  .deliveries-grid {
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 20px;
  }

  /* Cartes "Terminées" plus denses (pas de bouton/QR à loger) -- profitent
     d'une colonne plus étroite pour en montrer davantage à la fois. */
  .deliveries-grid--compact {
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 12px;
  }
}

.delivery-card {
  padding: 16px;
}

.delivery-card--compact {
  padding: 12px 14px;
}

/* Échelle de taille propre à cette page (plus généreuse que le reste de
   l'app) -- un livreur lit souvent son téléphone en extérieur, en plein
   soleil ou en mouvement : mieux vaut un texte trop grand que trop petit.
   Chaque rôle (numéro de commande / boutique / date / articles) a aussi sa
   propre couleur plutôt qu'un bloc de texte uniforme, pour repérer
   l'information voulue d'un coup d'œil. */
.delivery-card__code {
  font-family: var(--font-heading);
  font-weight: 700;
  font-size: 16px;
  letter-spacing: 0.01em;
  color: var(--color-primary-300);
}

.delivery-card__shop {
  font-family: var(--font-heading);
  font-weight: 700;
  font-size: 15px;
  color: var(--color-accent);
}

.delivery-card__shop--compact {
  font-size: 13.5px;
}

.delivery-card__date {
  font-size: 13px;
  color: var(--color-neutral-400);
}

.delivery-card__items {
  font-family: var(--font-heading);
  font-weight: 700;
  font-size: 15px;
  color: var(--color-success);
}

.delivery-card__items-list {
  font-family: var(--font-body);
  font-weight: 400;
  color: var(--color-neutral-400);
}

@media (min-width: 960px) {
  .delivery-card__code {
    font-size: 19px;
  }

  .delivery-card__shop {
    font-size: 17px;
  }

  .delivery-card__shop--compact {
    font-size: 14.5px;
  }

  .delivery-card__date {
    font-size: 14.5px;
  }

  .delivery-card__items {
    font-size: 17px;
  }

  .delivery-card__items-list {
    font-size: 14.5px;
  }
}

/* Boîte mise en valeur pour le code de dépôt (point de retrait) : c'est la
   seule action qui compte une fois le colis expédié dans ce cas -- un
   encart distinct plutôt qu'un QR nu, pour qu'il saute aux yeux dans la
   carte. */
.qr-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 14px;
  background: color-mix(in srgb, var(--color-primary) 7%, transparent);
  border: 1px solid var(--color-primary-800);
  border-radius: var(--radius-lg);
}

.qr-block__label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: var(--font-heading);
  font-weight: 700;
  font-size: 12.5px;
  text-align: center;
  color: var(--color-primary-300);
}

/* Le champ de recherche en variant="solo-filled" (voir template) se
   détache déjà du fond gris par son propre remplissage -- ce léger relief
   en plus le distingue mieux encore d'une simple ligne de texte. */
.livreur-search :deep(.v-field) {
  box-shadow: var(--shadow-sm);
}
</style>
