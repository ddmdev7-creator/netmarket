<script setup lang="ts">
/**
 * Portefeuille d'un bénéficiaire (boutique, livreur ou point de retrait) :
 * solde, retraits vers le mobile money, moyen de réception et historique.
 * Partagé par /vendeur/gains, /livreur/gains et /point-retrait/gains — seul
 * `kind` change. Données : backend app/wallets (GET /wallets/mine…).
 */
import {
  PhArrowCircleDown,
  PhArrowCircleUp,
  PhClock,
  PhHourglassMedium,
  PhInfo,
  PhPencilSimple,
  PhWallet,
} from '@phosphor-icons/vue'
import type { Page, WalletEntryRead, WalletKind, WalletRead, WithdrawalRead } from '~/types/api'

const props = defineProps<{ kind: WalletKind }>()

const { apiFetch } = useApi()
const toast = useToastStore()

const { data: wallets, pending, refresh: refreshWallets } = await useAsyncData(
  `my-wallets-${props.kind}`,
  () => apiFetch<WalletRead[]>('/wallets/mine'),
  {
    default: () => [] as WalletRead[],
    // Données du rendu serveur à l'hydratation, puis toujours fraîches (un
    // solde ne doit jamais être servi depuis un cache de navigation).
    getCachedData: hydrateThenRefetch,
  },
)
const wallet = computed(() => wallets.value.find((w) => w.kind === props.kind) ?? null)

// --- Retraits et historique -------------------------------------------------

const withdrawals = ref<WithdrawalRead[]>([])
const entries = ref<WalletEntryRead[]>([])
const entriesPage = ref(1)
const entriesPages = ref(1)
const loadingEntries = ref(false)

async function loadWithdrawals() {
  if (!wallet.value) return
  withdrawals.value = await apiFetch<WithdrawalRead[]>(`/wallets/${wallet.value.id}/withdrawals`)
}

async function loadEntries(reset = false) {
  if (!wallet.value) return
  loadingEntries.value = true
  try {
    const page = reset ? 1 : entriesPage.value + 1
    const result = await apiFetch<Page<WalletEntryRead>>(`/wallets/${wallet.value.id}/entries`, {
      query: { page, page_size: 20 },
    })
    entries.value = reset ? result.items : [...entries.value, ...result.items]
    entriesPage.value = page
    entriesPages.value = result.pages
  } finally {
    loadingEntries.value = false
  }
}

async function refreshAll() {
  await refreshWallets()
  await Promise.all([loadWithdrawals(), loadEntries(true)])
}

onMounted(() => Promise.all([loadWithdrawals(), loadEntries(true)]))

// --- Moyen de réception ---------------------------------------------------------

const methodOpen = ref(false)
const methodForm = reactive({ payout_provider: 'OM' as WalletRead['payout_provider'], payout_account_number: '', payout_beneficiary_name: '' })
const savingMethod = ref(false)

function openMethod() {
  if (!wallet.value) return
  methodForm.payout_provider = wallet.value.payout_provider ?? 'OM'
  methodForm.payout_account_number = wallet.value.payout_account_number ?? ''
  methodForm.payout_beneficiary_name = wallet.value.payout_beneficiary_name ?? ''
  methodOpen.value = true
}

async function saveMethod() {
  if (!wallet.value) return
  const number = methodForm.payout_account_number.replace(/\D/g, '')
  if (number.length < 8) {
    toast.error('Numéro invalide : saisissez le numéro local, ex. 622000000.')
    return
  }
  savingMethod.value = true
  try {
    await apiFetch(`/wallets/${wallet.value.id}/payout-method`, {
      method: 'PUT',
      body: { ...methodForm, payout_account_number: number },
    })
    toast.success('Moyen de réception enregistré.')
    methodOpen.value = false
    await refreshWallets()
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'enregistrer ce moyen de réception."))
  } finally {
    savingMethod.value = false
  }
}

const hasMethod = computed(() => !!wallet.value?.payout_provider && !!wallet.value?.payout_account_number)

// --- Retrait ----------------------------------------------------------------------

const withdrawOpen = ref(false)
const withdrawAmount = ref('')
const requesting = ref(false)

const parsedAmount = computed(() => Number(withdrawAmount.value.replace(/\s/g, '')) || 0)
const estimatedFee = computed(() =>
  wallet.value ? Math.ceil((parsedAmount.value * wallet.value.withdrawal_fee_percent) / 100) : 0,
)
const withdrawError = computed(() => {
  if (!wallet.value || !parsedAmount.value) return null
  if (parsedAmount.value < wallet.value.min_withdrawal_amount)
    return `Minimum ${formatGnf(wallet.value.min_withdrawal_amount)}.`
  if (parsedAmount.value > wallet.value.balance.available) return 'Montant supérieur à votre solde disponible.'
  return null
})

function openWithdraw() {
  if (!hasMethod.value) {
    toast.error("Renseignez d'abord votre moyen de réception.")
    openMethod()
    return
  }
  withdrawAmount.value = wallet.value ? String(wallet.value.balance.available) : ''
  withdrawOpen.value = true
}

async function requestWithdrawal() {
  if (!wallet.value || withdrawError.value || !parsedAmount.value) return
  requesting.value = true
  try {
    await apiFetch(`/wallets/${wallet.value.id}/withdrawals`, { method: 'POST', body: { amount: parsedAmount.value } })
    toast.success("Demande envoyée — elle sera traitée après validation par l'équipe Ndjouri.")
    withdrawOpen.value = false
    await refreshAll()
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de demander ce retrait.'))
  } finally {
    requesting.value = false
  }
}

async function cancelWithdrawal(withdrawal: WithdrawalRead) {
  try {
    await apiFetch(`/wallets/withdrawals/${withdrawal.id}/cancel`, { method: 'POST' })
    toast.success('Retrait annulé, le montant est de retour sur votre solde.')
    await refreshAll()
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'annuler ce retrait."))
  }
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' })
}
function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <div>
    <v-skeleton-loader v-if="pending && !wallet" type="card, list-item-three-line" />
    <CommonEmptyState v-else-if="!wallet" message="Aucun portefeuille associé à ce compte." />

    <template v-else>
      <!-- Solde -->
      <section class="balance-hero">
        <div class="balance-hero__top">
          <span class="balance-hero__label"><PhWallet :size="18" weight="fill" /> Solde disponible</span>
          <v-btn size="small" variant="text" class="balance-hero__refresh" @click="refreshAll">Actualiser</v-btn>
        </div>
        <div class="balance-hero__amount">{{ formatGnf(wallet.balance.available) }}</div>
        <v-btn
          color="white"
          variant="flat"
          class="balance-hero__cta"
          :disabled="wallet.balance.available < wallet.min_withdrawal_amount"
          @click="openWithdraw"
        >
          <PhArrowCircleUp :size="18" class="mr-1" />
          Retirer vers mon mobile money
        </v-btn>
        <p v-if="wallet.balance.available < wallet.min_withdrawal_amount" class="balance-hero__hint">
          Retrait possible à partir de {{ formatGnf(wallet.min_withdrawal_amount) }}.
        </p>
      </section>

      <div class="stats">
        <div class="stat">
          <PhHourglassMedium :size="20" class="stat__icon stat__icon--pending" />
          <div>
            <div class="stat__value">{{ formatGnf(wallet.balance.pending) }}</div>
            <div class="stat__label">En attente — disponible {{ wallet.earnings_hold_days }} j après la livraison</div>
          </div>
        </div>
        <div class="stat">
          <PhClock :size="20" class="stat__icon stat__icon--progress" />
          <div>
            <div class="stat__value">{{ formatGnf(wallet.withdrawals_in_progress) }}</div>
            <div class="stat__label">Retraits en cours de traitement</div>
          </div>
        </div>
      </div>

      <!-- Moyen de réception -->
      <section class="panel">
        <div class="panel__head">
          <h2 class="panel__title">Moyen de réception</h2>
          <v-btn size="small" variant="tonal" color="primary" @click="openMethod">
            <PhPencilSimple :size="14" class="mr-1" />
            {{ hasMethod ? 'Modifier' : 'Ajouter' }}
          </v-btn>
        </div>
        <p v-if="hasMethod" class="panel__line">
          <strong>{{ payoutProviderLabel(wallet.payout_provider) }}</strong> · {{ wallet.payout_account_number }}
          <span class="text-muted"> · {{ wallet.payout_beneficiary_name }}</span>
        </p>
        <p v-else class="panel__line text-muted">Aucun — ajoutez le compte sur lequel recevoir vos retraits.</p>
      </section>

      <!-- Retraits -->
      <section v-if="withdrawals.length" class="panel">
        <h2 class="panel__title mb-2">Mes retraits</h2>
        <div v-for="w in withdrawals" :key="w.id" class="withdrawal">
          <div class="withdrawal__main">
            <div class="withdrawal__amount">{{ formatGnf(w.net_amount) }}</div>
            <div class="text-muted text-meta">
              {{ formatDate(w.created_at) }} · {{ payoutProviderLabel(w.payout_provider) }} {{ w.payout_account_number }}
              <span v-if="w.fee"> · frais {{ formatGnf(w.fee) }}</span>
            </div>
            <div v-if="w.admin_note" class="withdrawal__note">{{ w.admin_note }}</div>
          </div>
          <div class="withdrawal__side">
            <v-chip size="small" variant="tonal" :color="WITHDRAWAL_STATUS_META[w.status].color">
              {{ WITHDRAWAL_STATUS_META[w.status].label }}
            </v-chip>
            <button v-if="w.status === 'pending'" type="button" class="link-btn" @click="cancelWithdrawal(w)">
              Annuler
            </button>
          </div>
        </div>
      </section>

      <!-- Historique -->
      <section class="panel">
        <h2 class="panel__title mb-2">Historique</h2>
        <p v-if="!entries.length && !loadingEntries" class="text-muted text-meta mb-0">
          Aucun mouvement pour l'instant. Vos gains apparaissent ici dès qu'une commande payée en ligne est livrée.
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
            <div class="entry__desc">{{ e.description }}</div>
            <div class="text-muted text-fine">
              {{ formatDateTime(e.created_at) }}
              <span v-if="e.is_pending" class="entry__pending"> · disponible le {{ formatDate(e.available_at) }}</span>
            </div>
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
          Seules les commandes <strong>payées en ligne</strong> alimentent ce solde pour l'instant. Les commandes payées
          à la livraison continuent d'être réglées comme aujourd'hui.
        </span>
      </p>

      <!-- Dialogue : moyen de réception -->
      <v-dialog v-model="methodOpen" max-width="420">
        <v-card class="pa-5">
          <h2 class="dialog-title">Moyen de réception</h2>
          <v-select
            v-model="methodForm.payout_provider"
            :items="PAYOUT_PROVIDERS"
            label="Opérateur"
            variant="outlined"
            class="mb-2"
          />
          <v-text-field
            v-model="methodForm.payout_account_number"
            label="Numéro du compte"
            placeholder="622000000"
            inputmode="numeric"
            variant="outlined"
            class="mb-2"
          />
          <v-text-field
            v-model="methodForm.payout_beneficiary_name"
            label="Nom du titulaire"
            variant="outlined"
            hint="Tel qu'enregistré chez l'opérateur."
            persistent-hint
          />
          <div class="d-flex justify-end ga-2 mt-4">
            <v-btn variant="text" @click="methodOpen = false">Annuler</v-btn>
            <v-btn color="primary" :loading="savingMethod" @click="saveMethod">Enregistrer</v-btn>
          </div>
        </v-card>
      </v-dialog>

      <!-- Dialogue : retrait -->
      <v-dialog v-model="withdrawOpen" max-width="420">
        <v-card class="pa-5">
          <h2 class="dialog-title">Retirer mon argent</h2>
          <p class="text-muted text-meta mb-3">
            Vers {{ payoutProviderLabel(wallet.payout_provider) }} {{ wallet.payout_account_number }} ·
            disponible : <strong>{{ formatGnf(wallet.balance.available) }}</strong>
          </p>
          <v-text-field
            v-model="withdrawAmount"
            label="Montant à retirer"
            suffix="GNF"
            inputmode="numeric"
            variant="outlined"
            :error-messages="withdrawError ?? undefined"
          />
          <dl v-if="parsedAmount && !withdrawError" class="recap">
            <div><dt>Montant débité</dt><dd>{{ formatGnf(parsedAmount) }}</dd></div>
            <div v-if="wallet.withdrawal_fee_percent">
              <dt>Frais d'envoi ({{ wallet.withdrawal_fee_percent }} %)</dt><dd>− {{ formatGnf(estimatedFee) }}</dd>
            </div>
            <div class="recap__total"><dt>Vous recevrez</dt><dd>{{ formatGnf(parsedAmount - estimatedFee) }}</dd></div>
          </dl>
          <p class="text-muted text-fine mt-2 mb-0">
            Le montant est réservé dès la demande. Le versement part après validation par l'équipe Ndjouri.
          </p>
          <div class="d-flex justify-end ga-2 mt-4">
            <v-btn variant="text" @click="withdrawOpen = false">Annuler</v-btn>
            <v-btn
              color="primary"
              :loading="requesting"
              :disabled="!parsedAmount || !!withdrawError"
              @click="requestWithdrawal"
            >
              Confirmer le retrait
            </v-btn>
          </div>
        </v-card>
      </v-dialog>
    </template>
  </div>
</template>

<style scoped>
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

.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
  margin: 12px 0;
}

.stat {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-md);
  background: var(--color-neutral-900);
}

.stat__icon {
  flex: none;
}

.stat__icon--pending {
  color: var(--color-accent);
}

.stat__icon--progress {
  color: var(--color-primary);
}

.stat__value {
  font-family: var(--font-heading);
  font-size: 17px;
  font-weight: 800;
  color: var(--color-neutral-200);
}

.stat__label {
  font-size: 12px;
  color: var(--color-neutral-400);
}

.panel {
  margin-bottom: 12px;
  padding: 16px;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-md);
  background: var(--color-neutral-900);
}

.panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.panel__title {
  margin: 0;
  font-family: var(--font-heading);
  font-size: 15px;
  font-weight: 800;
  color: var(--color-neutral-200);
}

.panel__line {
  margin: 8px 0 0;
  font-size: 13.5px;
  color: var(--color-neutral-300);
}

.withdrawal,
.entry {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  border-top: 1px solid var(--color-divider);
}

.withdrawal__main,
.entry__main {
  flex: 1;
  min-width: 0;
}

.withdrawal__amount {
  font-family: var(--font-heading);
  font-weight: 800;
  color: var(--color-neutral-200);
}

.withdrawal__note {
  margin-top: 2px;
  font-size: 12px;
  color: var(--color-error);
}

.withdrawal__side {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}

.link-btn {
  border: none;
  background: none;
  padding: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-primary-300);
  cursor: pointer;
}

.entry__icon--in {
  flex: none;
  color: var(--color-success);
}

.entry__icon--out {
  flex: none;
  color: var(--color-neutral-500);
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

.entry__pending {
  color: var(--color-accent);
  font-weight: 600;
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

.recap {
  display: grid;
  gap: 4px;
  margin: 0;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: var(--color-neutral-800);
  font-size: 13px;
}

.recap > div {
  display: flex;
  justify-content: space-between;
}

.recap dd {
  margin: 0;
  font-variant-numeric: tabular-nums;
}

.recap__total {
  padding-top: 4px;
  border-top: 1px solid var(--color-divider);
  font-weight: 800;
}
</style>
