<script setup lang="ts">
/**
 * NdjouriBank côté acheteur : solde, recharge via le portail Djomy et
 * historique (recharges, commandes payées avec le solde, remboursements).
 * Le solde se dépense sur Ndjouri uniquement, il n'est pas retirable.
 * Données : backend app/wallets/buyer_service.py (GET /ndjouribank…).
 */
import {
  PhArrowCircleDown,
  PhArrowCircleUp,
  PhHourglassMedium,
  PhInfo,
  PhLockSimple,
  PhPlusCircle,
  PhWallet,
} from '@phosphor-icons/vue'
import type { BuyerWalletRead, Page, TopUpRead, TopUpStarted, WalletEntryRead } from '~/types/api'

definePageMeta({ middleware: 'auth' })

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const { apiFetch } = useApi()
const toast = useToastStore()

// Arrivée directe (retour du portail Djomy = rechargement complet) : le
// profil n'est pas encore chargé — même motif que pages/profil/index.vue.
await useAsyncData('ndjouribank-me', () => auth.fetchMe())

const { data: wallet, pending, refresh: refreshWallet } = await useAsyncData(
  'ndjouribank',
  () => apiFetch<BuyerWalletRead>('/ndjouribank'),
  // Un solde n'est jamais servi depuis un cache de navigation.
  { getCachedData: (key, nuxtApp) => (nuxtApp.isHydrating ? nuxtApp.payload.data[key] : undefined) },
)

// --- Historique et recharges --------------------------------------------------

const entries = ref<WalletEntryRead[]>([])
const entriesPage = ref(1)
const entriesPages = ref(1)
const loadingEntries = ref(false)
const topups = ref<TopUpRead[]>([])
const pendingTopups = computed(() => topups.value.filter((t) => t.status === 'pending'))

async function loadEntries(reset = false) {
  loadingEntries.value = true
  try {
    const page = reset ? 1 : entriesPage.value + 1
    const result = await apiFetch<Page<WalletEntryRead>>('/ndjouribank/entries', { query: { page, page_size: 20 } })
    entries.value = reset ? result.items : [...entries.value, ...result.items]
    entriesPage.value = page
    entriesPages.value = result.pages
  } finally {
    loadingEntries.value = false
  }
}

async function loadTopups() {
  topups.value = await apiFetch<TopUpRead[]>('/ndjouribank/topups')
}

async function refreshAll() {
  await refreshWallet()
  await Promise.all([loadEntries(true), loadTopups()])
}

// Retour du portail Djomy : le webhook peut ne pas être encore arrivé, on
// relit le statut de la recharge avant d'afficher le solde.
async function syncTopup(topupId: string, announce: boolean) {
  try {
    const topup = await apiFetch<TopUpRead>(`/ndjouribank/topups/${topupId}/sync`, { method: 'POST' })
    if (announce) {
      if (topup.status === 'paid') toast.success(`Recharge de ${formatGnf(topup.amount)} créditée sur ton solde.`)
      else if (topup.status === 'pending')
        toast.info('Paiement en cours de confirmation — ton solde sera crédité dès sa réception.')
      else toast.error("La recharge n'a pas abouti, aucun montant n'a été débité.")
    }
  } catch {
    // Pas bloquant : le statut sera relu au prochain affichage.
  }
}

onMounted(async () => {
  const returning = typeof route.query.topup === 'string' ? route.query.topup : null
  if (returning) {
    await syncTopup(returning, true)
    router.replace({ query: {} })
    await refreshWallet()
  }
  await Promise.all([loadEntries(true), loadTopups()])
})

async function recheck(topup: TopUpRead) {
  await syncTopup(topup.id, true)
  await refreshAll()
}

// --- Recharge -------------------------------------------------------------------

const QUICK_AMOUNTS = [10000, 25000, 50000, 100000]
const topupOpen = ref(false)
const topupAmount = ref('')
const payerPhone = ref(auth.user?.phone ?? '')
watch(
  () => auth.user?.phone,
  (phone) => {
    if (phone && !payerPhone.value) payerPhone.value = phone
  },
)
const starting = ref(false)

const parsedAmount = computed(() => Number(topupAmount.value.replace(/\s/g, '')) || 0)
const room = computed(() => (wallet.value ? Math.max(wallet.value.max_balance - wallet.value.balance, 0) : 0))
const topupError = computed(() => {
  if (!wallet.value || !parsedAmount.value) return null
  if (parsedAmount.value < wallet.value.topup_min) return `Minimum ${formatGnf(wallet.value.topup_min)}.`
  if (parsedAmount.value > wallet.value.topup_max) return `Maximum ${formatGnf(wallet.value.topup_max)} par recharge.`
  if (parsedAmount.value > room.value) return `Ton solde est plafonné : tu peux encore recharger ${formatGnf(room.value)}.`
  return null
})

function openTopup(amount?: number) {
  topupAmount.value = amount ? String(amount) : ''
  topupOpen.value = true
}

async function startTopup() {
  if (!parsedAmount.value || topupError.value) return
  if (!payerPhone.value.trim()) {
    toast.error('Indique le numéro qui va payer (mobile money ou carte).')
    return
  }
  starting.value = true
  try {
    const started = await apiFetch<TopUpStarted>('/ndjouribank/topups', {
      method: 'POST',
      body: { amount: parsedAmount.value, payer_phone: payerPhone.value.trim() },
    })
    window.location.href = started.redirect_url
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de démarrer la recharge.'))
    starting.value = false
  }
}

function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <div class="detail-card">
    <h1 class="text-h6 mb-4">NdjouriBank</h1>

    <v-skeleton-loader v-if="pending && !wallet" type="card, list-item-three-line" />
    <CommonEmptyState v-else-if="!wallet" message="Impossible de charger ton solde pour le moment." />

    <!-- Service pas encore ouvert et rien à dépenser : simple présentation. -->
    <section v-else-if="!wallet.enabled && wallet.balance === 0" class="soon">
      <PhLockSimple :size="28" class="soon__icon" />
      <h2 class="soon__title">Bientôt disponible</h2>
      <p class="soon__text">
        Avec NdjouriBank, tu pourras recharger un solde depuis ton mobile money, payer tes commandes en un clic et être
        remboursé instantanément en cas d'annulation.
      </p>
    </section>

    <template v-else>
      <section class="balance-hero">
        <div class="balance-hero__top">
          <span class="balance-hero__label"><PhWallet :size="18" weight="fill" /> Mon solde</span>
          <v-btn size="small" variant="text" class="balance-hero__refresh" @click="refreshAll">Actualiser</v-btn>
        </div>
        <div class="balance-hero__amount">{{ formatGnf(wallet.balance) }}</div>
        <v-btn
          v-if="wallet.enabled"
          color="white"
          variant="flat"
          class="balance-hero__cta"
          :disabled="room < wallet.topup_min"
          @click="openTopup()"
        >
          <PhPlusCircle :size="18" class="mr-1" />
          Recharger
        </v-btn>
        <p v-if="!wallet.enabled" class="balance-hero__hint">
          Les recharges sont momentanément fermées — ton solde reste utilisable pour payer.
        </p>
        <p v-else-if="room < wallet.topup_min" class="balance-hero__hint">
          Plafond de {{ formatGnf(wallet.max_balance) }} atteint.
        </p>
      </section>

      <div v-if="wallet.enabled" class="quick">
        <button v-for="amount in QUICK_AMOUNTS" :key="amount" type="button" class="quick__chip" @click="openTopup(amount)">
          + {{ formatGnf(amount) }}
        </button>
      </div>

      <section v-if="pendingTopups.length" class="panel">
        <h2 class="panel__title mb-2">Recharges en attente</h2>
        <div v-for="t in pendingTopups" :key="t.id" class="entry">
          <PhHourglassMedium :size="22" class="entry__icon--pending" />
          <div class="entry__main">
            <div class="entry__title">{{ formatGnf(t.amount) }}</div>
            <div class="text-muted text-fine">{{ formatDateTime(t.created_at) }} · {{ t.payer_phone }}</div>
          </div>
          <v-btn size="small" variant="tonal" color="primary" @click="recheck(t)">Vérifier</v-btn>
        </div>
      </section>

      <section class="panel">
        <h2 class="panel__title mb-2">Historique</h2>
        <p v-if="!entries.length && !loadingEntries" class="text-muted text-meta mb-0">
          Aucun mouvement pour l'instant.
        </p>
        <div v-for="e in entries" :key="e.id" class="entry">
          <component
            :is="e.amount >= 0 ? PhArrowCircleDown : PhArrowCircleUp"
            :size="22"
            weight="fill"
            :class="e.amount >= 0 ? 'entry__icon--in' : 'entry__icon--out'"
          />
          <div class="entry__main">
            <div class="entry__title">{{ TRANSACTION_KIND_LABELS[e.kind] }}</div>
            <div class="entry__desc">
              <NuxtLink v-if="e.order_id" :to="`/commandes/${e.order_id}`" class="entry__link">{{ e.description }}</NuxtLink>
              <template v-else>{{ e.description }}</template>
            </div>
            <div class="text-muted text-fine">{{ formatDateTime(e.created_at) }}</div>
          </div>
          <div class="entry__amount" :class="e.amount >= 0 ? 'entry__amount--in' : 'entry__amount--out'">
            {{ e.amount >= 0 ? '+' : '−' }}{{ formatGnf(Math.abs(e.amount)) }}
          </div>
        </div>
        <v-btn
          v-if="entriesPage < entriesPages"
          variant="text"
          block
          class="mt-2"
          :loading="loadingEntries"
          @click="loadEntries()"
        >
          Voir plus
        </v-btn>
      </section>

      <p class="info-note">
        <PhInfo :size="15" />
        <span>
          Ton solde NdjouriBank sert à payer tes commandes sur Ndjouri. Il n'est pas retirable vers un compte mobile money.
        </span>
      </p>
    </template>

    <v-dialog v-model="topupOpen" max-width="420">
      <v-card v-if="wallet" class="pa-5">
        <h2 class="dialog-title">Recharger mon solde</h2>
        <div class="quick quick--dialog">
          <button
            v-for="amount in QUICK_AMOUNTS"
            :key="amount"
            type="button"
            class="quick__chip"
            :class="{ 'quick__chip--active': parsedAmount === amount }"
            @click="topupAmount = String(amount)"
          >
            {{ formatGnf(amount) }}
          </button>
        </div>
        <v-text-field
          v-model="topupAmount"
          label="Montant"
          suffix="GNF"
          inputmode="numeric"
          variant="outlined"
          class="mb-2"
          :error-messages="topupError ?? undefined"
        />
        <v-text-field
          v-model="payerPhone"
          label="Numéro qui paie (mobile money ou carte)"
          placeholder="Ex. 622000000"
          variant="outlined"
          hide-details="auto"
        />
        <p class="text-muted text-fine mt-2 mb-0">
          Tu vas être redirigé vers le portail de paiement (Orange Money, MTN MoMo, carte…). Ton solde est crédité dès
          la confirmation du paiement.
        </p>
        <div class="d-flex justify-end ga-2 mt-4">
          <v-btn variant="text" @click="topupOpen = false">Annuler</v-btn>
          <v-btn color="primary" :loading="starting" :disabled="!parsedAmount || !!topupError" @click="startTopup">
            Payer {{ parsedAmount ? formatGnf(parsedAmount) : '' }}
          </v-btn>
        </div>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.soon {
  padding: 28px 20px;
  border: 1px dashed var(--color-divider);
  border-radius: var(--radius-lg);
  text-align: center;
}

.soon__icon {
  color: var(--color-primary);
}

.soon__title {
  margin: 8px 0 6px;
  font-family: var(--font-heading);
  font-size: 18px;
  font-weight: 800;
}

.soon__text {
  margin: 0 auto;
  max-width: 420px;
  font-size: 13.5px;
  color: var(--color-neutral-400);
}

.balance-hero {
  padding: 20px;
  border-radius: var(--radius-lg);
  color: #fff;
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-800) 100%);
  box-shadow: var(--shadow-md);
}

.balance-hero__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.balance-hero__label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13.5px;
  font-weight: 600;
  opacity: 0.9;
}

.balance-hero__refresh {
  color: #fff !important;
  opacity: 0.85;
}

.balance-hero__amount {
  margin: 6px 0 16px;
  font-family: var(--font-heading);
  font-size: 32px;
  font-weight: 800;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
}

.balance-hero__cta {
  color: var(--color-primary) !important;
  font-weight: 700;
}

.balance-hero__hint {
  margin: 8px 0 0;
  font-size: 12px;
  opacity: 0.85;
}

.quick {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 12px 0;
}

.quick--dialog {
  margin-top: 0;
}

.quick__chip {
  padding: 6px 12px;
  border: 1px solid var(--color-divider);
  border-radius: 999px;
  background: var(--color-neutral-900);
  color: var(--color-neutral-200);
  font-size: 13px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
}

.quick__chip--active {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.panel {
  margin-bottom: 12px;
  padding: 16px;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-md);
  background: var(--color-neutral-900);
}

.panel__title {
  margin: 0;
  font-family: var(--font-heading);
  font-size: 15px;
  font-weight: 800;
  color: var(--color-neutral-200);
}

.entry {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  border-top: 1px solid var(--color-divider);
}

.entry__main {
  flex: 1;
  min-width: 0;
}

.entry__icon--in {
  flex: none;
  color: var(--color-success);
}

.entry__icon--out {
  flex: none;
  color: var(--color-neutral-500);
}

.entry__icon--pending {
  flex: none;
  color: var(--color-accent);
}

.entry__title {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--color-neutral-200);
}

.entry__desc {
  font-size: 12.5px;
  color: var(--color-neutral-300);
  overflow-wrap: anywhere;
}

.entry__link {
  color: inherit;
}

.entry__amount {
  flex: none;
  font-family: var(--font-heading);
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}

.entry__amount--in {
  color: var(--color-success);
}

.entry__amount--out {
  color: var(--color-neutral-300);
}

.info-note {
  display: flex;
  gap: 8px;
  margin: 4px 0 0;
  font-size: 12.5px;
  color: var(--color-neutral-400);
}

.info-note svg {
  flex: none;
  margin-top: 2px;
}

.dialog-title {
  margin: 0 0 12px;
  font-family: var(--font-heading);
  font-size: 18px;
  font-weight: 800;
}
</style>
