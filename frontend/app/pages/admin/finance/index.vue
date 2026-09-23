<script setup lang="ts">
/**
 * Compte principal : l'argent détenu chez Djomy et à qui il revient, les
 * demandes de retrait à valider, les portefeuilles des bénéficiaires, le
 * journal comptable et les règles de répartition. Backend : app/wallets.
 *
 * La trésorerie affichée est celle du grand livre (Djomy n'expose pas de
 * lecture du solde marchand) : elle se rapproche du relevé Djomy.
 */
import {
  PhArrowsClockwise,
  PhCheckCircle,
  PhClock,
  PhGear,
  PhListChecks,
  PhWallet,
  PhWarningCircle,
  PhX,
} from '@phosphor-icons/vue'
import type {
  AdminFinanceOverview,
  AdminWalletRead,
  AdminWithdrawalRead,
  EarningsSettings,
  LedgerTransactionRead,
  Page,
  WithdrawalStatus,
} from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const { apiFetch } = useApi()
const toast = useToastStore()
// Données du rendu serveur à l'hydratation, puis toujours fraîches.
const noCache = {
  getCachedData: (key: string, nuxtApp: ReturnType<typeof useNuxtApp>) =>
    nuxtApp.isHydrating ? nuxtApp.payload.data[key] : undefined,
}

const { data: overview, refresh: refreshOverview } = await useAsyncData(
  'admin-finance-overview',
  () => apiFetch<AdminFinanceOverview>('/admin/finance/overview'),
  noCache,
)

const tab = ref<'withdrawals' | 'wallets' | 'journal' | 'settings'>('withdrawals')

// --- Composition de la trésorerie ------------------------------------------------
// Barre empilée unique (part d'un tout) : 5 catégories, couleurs catégorielles
// validées (clair/sombre) avec libellés + montants toujours visibles.

const segments = computed(() => {
  const o = overview.value
  if (!o) return []
  return [
    { key: 'escrow', label: 'Séquestre (commandes non livrées)', value: o.escrow, color: 'var(--fin-1)' },
    { key: 'beneficiaries', label: 'Dû aux vendeurs, livreurs et points', value: o.beneficiaries_total, color: 'var(--fin-2)' },
    { key: 'reserved', label: 'Retraits en cours', value: o.withdrawals_reserved, color: 'var(--fin-3)' },
    { key: 'revenue', label: 'Revenus Ndjouri', value: o.platform_revenue, color: 'var(--fin-4)' },
    { key: 'buyers', label: 'Soldes NdjouriBank des acheteurs', value: o.buyer_wallets_total, color: 'var(--fin-5)' },
  ]
})
const positiveTotal = computed(() => segments.value.reduce((sum, s) => sum + Math.max(0, s.value), 0))

// --- Retraits -------------------------------------------------------------------

const withdrawalFilter = ref<WithdrawalStatus | 'all'>('pending')
const withdrawals = ref<AdminWithdrawalRead[]>([])
const loadingWithdrawals = ref(false)

async function loadWithdrawals() {
  loadingWithdrawals.value = true
  try {
    withdrawals.value = await apiFetch<AdminWithdrawalRead[]>('/admin/finance/withdrawals', {
      query: withdrawalFilter.value === 'all' ? {} : { status: withdrawalFilter.value },
    })
  } finally {
    loadingWithdrawals.value = false
  }
}
watch(withdrawalFilter, loadWithdrawals)

const busyId = ref<string | null>(null)
const confirmTarget = ref<AdminWithdrawalRead | null>(null)
const rejectTarget = ref<AdminWithdrawalRead | null>(null)
const rejectReason = ref('')

async function act(withdrawal: AdminWithdrawalRead, action: 'approve' | 'reject' | 'sync', body?: object) {
  busyId.value = withdrawal.id
  try {
    const updated = await apiFetch<AdminWithdrawalRead>(`/admin/finance/withdrawals/${withdrawal.id}/${action}`, {
      method: 'POST',
      body,
    })
    const messages = {
      approve: 'Versement lancé chez Djomy.',
      reject: 'Retrait refusé, montant recrédité.',
      sync: updated.status === 'processing' ? 'Toujours en cours chez Djomy.' : 'Statut mis à jour.',
    }
    toast.success(messages[action])
    await Promise.all([loadWithdrawals(), refreshOverview()])
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Action impossible.'))
  } finally {
    busyId.value = null
    confirmTarget.value = null
    rejectTarget.value = null
    rejectReason.value = ''
  }
}

// --- Portefeuilles et journal --------------------------------------------------

const wallets = ref<AdminWalletRead[]>([])
const walletSearch = ref('')
const walletScope = ref<'beneficiaries' | 'buyers'>('beneficiaries')
const journal = ref<LedgerTransactionRead[]>([])
const journalPage = ref(1)
const journalPages = ref(1)

async function loadWallets() {
  wallets.value = await apiFetch<AdminWalletRead[]>('/admin/finance/wallets')
}
async function loadJournal(reset = true) {
  const page = reset ? 1 : journalPage.value + 1
  const result = await apiFetch<Page<LedgerTransactionRead>>('/admin/finance/transactions', {
    query: { page, page_size: 25 },
  })
  journal.value = reset ? result.items : [...journal.value, ...result.items]
  journalPage.value = page
  journalPages.value = result.pages
}

const visibleWallets = computed(() => {
  const term = walletSearch.value.trim().toLowerCase()
  return wallets.value
    .filter((w) => (walletScope.value === 'buyers') === (w.kind === 'buyer'))
    .filter((w) => !term || w.owner_label.toLowerCase().includes(term))
    .sort((a, b) => b.balance.total - a.balance.total)
})

// --- Règles ----------------------------------------------------------------------

const settings = reactive<EarningsSettings>({
  courier_delivery_share_percent: 80,
  pickup_point_fee_per_parcel: 2000,
  earnings_hold_days: 3,
  withdrawal_fee_percent: 0,
  min_withdrawal_amount: 10000,
  buyer_wallet_enabled: false,
  wallet_topup_min: 5000,
  wallet_topup_max: 2_000_000,
  wallet_max_balance: 5_000_000,
})
const savingSettings = ref(false)

async function loadSettings() {
  Object.assign(settings, await apiFetch<EarningsSettings>('/admin/finance/settings'))
}
async function saveSettings() {
  savingSettings.value = true
  try {
    const body = Object.fromEntries(
      Object.entries(settings).map(([k, v]) => [k, typeof v === 'boolean' ? v : Number(v)]),
    )
    Object.assign(settings, await apiFetch<EarningsSettings>('/admin/finance/settings', { method: 'PUT', body }))
    toast.success('Règles enregistrées — elles s’appliquent aux prochaines livraisons et demandes de retrait.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible d’enregistrer ces règles.'))
  } finally {
    savingSettings.value = false
  }
}

async function refreshAll() {
  await Promise.all([refreshOverview(), loadWithdrawals(), loadWallets(), loadJournal()])
}

onMounted(() => Promise.all([loadWithdrawals(), loadWallets(), loadJournal(), loadSettings()]))

function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}
function shortId(id: string) {
  return `#GN-${id.slice(0, 5).toUpperCase()}`
}
</script>

<template>
  <div class="dashboard-shell finance">
    <header class="finance__head">
      <div>
        <h1 class="finance__title">Compte principal</h1>
        <p class="finance__sub">Argent encaissé via Djomy et sa répartition entre les acteurs de la plateforme.</p>
      </div>
      <v-btn variant="tonal" size="small" @click="refreshAll">
        <PhArrowsClockwise :size="15" class="mr-1" />
        Actualiser
      </v-btn>
    </header>

    <template v-if="overview">
      <!-- Trésorerie et sa composition -->
      <section class="card treasury">
        <div class="treasury__top">
          <div>
            <div class="treasury__label">Trésorerie Djomy (selon le grand livre)</div>
            <div class="treasury__amount">{{ formatGnf(overview.treasury) }}</div>
          </div>
          <span class="balanced" :class="{ 'balanced--ko': !overview.is_balanced }">
            <component :is="overview.is_balanced ? PhCheckCircle : PhWarningCircle" :size="16" weight="fill" />
            {{ overview.is_balanced ? 'Comptes équilibrés' : 'Écart détecté' }}
          </span>
        </div>

        <div v-if="positiveTotal > 0" class="stack" role="img" :aria-label="segments.map((s) => `${s.label} ${formatGnf(s.value)}`).join(', ')">
          <div
            v-for="s in segments.filter((s) => s.value > 0)"
            :key="s.key"
            class="stack__seg"
            :style="{ flexGrow: s.value, background: s.color }"
            :title="`${s.label} : ${formatGnf(s.value)}`"
          />
        </div>
        <ul class="legend">
          <li v-for="s in segments" :key="s.key">
            <span class="legend__dot" :style="{ background: s.color }" />
            <span class="legend__label">{{ s.label }}</span>
            <span class="legend__value">{{ formatGnf(s.value) }}</span>
          </li>
        </ul>
        <p class="treasury__note">
          Dû aux bénéficiaires : {{ formatGnf(overview.beneficiaries_available) }} retirable,
          {{ formatGnf(overview.beneficiaries_pending) }} encore dans le délai de sécurité.
        </p>
      </section>

      <div class="kpis">
        <div class="kpi"><div class="kpi__label">Total encaissé</div><div class="kpi__value">{{ formatGnf(overview.total_captured) }}</div></div>
        <div class="kpi">
          <div class="kpi__label">Rechargé sur NdjouriBank</div>
          <div class="kpi__value">{{ formatGnf(overview.total_topped_up) }}</div>
          <div class="kpi__sub">{{ overview.buyer_wallets_count }} acheteur(s) avec un solde</div>
        </div>
        <div class="kpi"><div class="kpi__label">Remboursé aux acheteurs</div><div class="kpi__value">{{ formatGnf(overview.total_refunded) }}</div></div>
        <div class="kpi"><div class="kpi__label">Versé aux bénéficiaires</div><div class="kpi__value">{{ formatGnf(overview.total_paid_out) }}</div></div>
        <div class="kpi kpi--accent">
          <div class="kpi__label">Retraits à valider</div>
          <div class="kpi__value">{{ overview.withdrawals_pending_count }}</div>
          <div class="kpi__sub">{{ formatGnf(overview.withdrawals_pending_amount) }}</div>
        </div>
      </div>
    </template>

    <v-tabs v-model="tab" color="primary" class="mb-4">
      <v-tab value="withdrawals">
        <PhClock :size="16" class="mr-1" /> Retraits
        <span v-if="overview?.withdrawals_pending_count" class="tab-badge">{{ overview.withdrawals_pending_count }}</span>
      </v-tab>
      <v-tab value="wallets"><PhWallet :size="16" class="mr-1" /> Portefeuilles</v-tab>
      <v-tab value="journal"><PhListChecks :size="16" class="mr-1" /> Journal</v-tab>
      <v-tab value="settings"><PhGear :size="16" class="mr-1" /> Règles</v-tab>
    </v-tabs>

    <!-- Retraits -->
    <section v-if="tab === 'withdrawals'">
      <v-btn-toggle v-model="withdrawalFilter" mandatory density="compact" divided variant="outlined" class="mb-3">
        <v-btn value="pending" size="small">À valider</v-btn>
        <v-btn value="processing" size="small">En cours</v-btn>
        <v-btn value="paid" size="small">Versés</v-btn>
        <v-btn value="all" size="small">Tous</v-btn>
      </v-btn-toggle>

      <CommonEmptyState v-if="!loadingWithdrawals && !withdrawals.length" message="Aucun retrait dans cette catégorie." />
      <div class="withdrawals">
        <div v-for="w in withdrawals" :key="w.id" class="card withdrawal">
          <div class="withdrawal__head">
            <div>
              <div class="withdrawal__owner">{{ w.owner_label }}</div>
              <div class="text-muted text-meta">{{ ACCOUNT_KIND_LABELS[w.account_kind] }} · {{ formatDateTime(w.created_at) }}</div>
            </div>
            <v-chip size="small" variant="tonal" :color="WITHDRAWAL_STATUS_META[w.status].color">
              {{ WITHDRAWAL_STATUS_META[w.status].label }}
            </v-chip>
          </div>
          <dl class="withdrawal__facts">
            <div><dt>À verser</dt><dd class="withdrawal__net">{{ formatGnf(w.net_amount) }}</dd></div>
            <div><dt>Débité du solde</dt><dd>{{ formatGnf(w.amount) }}</dd></div>
            <div><dt>Frais facturés</dt><dd>{{ formatGnf(w.fee) }} ({{ w.fee_percent }} %)</dd></div>
            <div>
              <dt>Destination</dt>
              <dd>{{ payoutProviderLabel(w.payout_provider) }} {{ w.payout_account_number }} · {{ w.payout_beneficiary_name }}</dd>
            </div>
            <div v-if="w.djomy_total_amount"><dt>Coût Djomy réel</dt><dd>{{ formatGnf(w.djomy_total_amount) }}</dd></div>
          </dl>
          <p v-if="w.admin_note" class="withdrawal__note">{{ w.admin_note }}</p>
          <div v-if="w.status === 'pending' || w.status === 'processing'" class="withdrawal__actions">
            <template v-if="w.status === 'pending'">
              <v-btn color="primary" size="small" :loading="busyId === w.id" @click="confirmTarget = w">
                Valider et verser
              </v-btn>
              <v-btn variant="text" color="error" size="small" :disabled="busyId === w.id" @click="rejectTarget = w">
                Refuser
              </v-btn>
            </template>
            <v-btn v-else variant="tonal" size="small" :loading="busyId === w.id" @click="act(w, 'sync')">
              <PhArrowsClockwise :size="14" class="mr-1" /> Vérifier chez Djomy
            </v-btn>
          </div>
        </div>
      </div>
    </section>

    <!-- Portefeuilles -->
    <section v-else-if="tab === 'wallets'">
      <div class="d-flex flex-wrap align-center ga-3 mb-3">
        <v-btn-toggle v-model="walletScope" mandatory density="compact" divided variant="outlined">
          <v-btn value="beneficiaries" size="small">Bénéficiaires</v-btn>
          <v-btn value="buyers" size="small">Acheteurs NdjouriBank</v-btn>
        </v-btn-toggle>
        <v-text-field v-model="walletSearch" placeholder="Rechercher…" density="compact" hide-details clearable style="max-width: 360px" />
      </div>
      <CommonEmptyState
        v-if="!visibleWallets.length"
        :message="walletScope === 'buyers' ? 'Aucun solde acheteur pour l\'instant.' : 'Aucun portefeuille pour l\'instant — ils apparaissent à la première livraison payée en ligne.'"
      />
      <div v-else-if="walletScope === 'buyers'" class="card table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>Acheteur</th>
              <th class="num">Solde</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="w in visibleWallets" :key="w.id">
              <td class="strong">{{ w.owner_label }}</td>
              <td class="num strong">{{ formatGnf(w.balance.total) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="card table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>Bénéficiaire</th>
              <th>Type</th>
              <th class="num">Disponible</th>
              <th class="num">En attente</th>
              <th class="num">En retrait</th>
              <th>Moyen de réception</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="w in visibleWallets" :key="w.id">
              <td class="strong">{{ w.owner_label }}</td>
              <td>{{ ACCOUNT_KIND_LABELS[w.kind] }}</td>
              <td class="num strong">{{ formatGnf(w.balance.available) }}</td>
              <td class="num">{{ formatGnf(w.balance.pending) }}</td>
              <td class="num">{{ formatGnf(w.withdrawals_in_progress) }}</td>
              <td>
                <template v-if="w.payout_provider">{{ payoutProviderLabel(w.payout_provider) }} {{ w.payout_account_number }}</template>
                <span v-else class="text-muted">Non renseigné</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Journal -->
    <section v-else-if="tab === 'journal'">
      <CommonEmptyState v-if="!journal.length" message="Aucune écriture pour l'instant." />
      <div v-for="t in journal" :key="t.id" class="card tx">
        <div class="tx__head">
          <span class="tx__kind">{{ TRANSACTION_KIND_LABELS[t.kind] }}</span>
          <span class="text-muted text-meta">{{ formatDateTime(t.created_at) }}</span>
        </div>
        <div class="tx__desc">
          {{ t.description }}
          <NuxtLink v-if="t.order_id" :to="`/admin/commandes/${t.order_id}`" class="tx__link">{{ shortId(t.order_id) }}</NuxtLink>
        </div>
        <table class="tx__lines">
          <tr v-for="(line, i) in t.lines" :key="i">
            <td>{{ line.owner_label }} <span class="text-muted">· {{ ACCOUNT_KIND_LABELS[line.account_kind] }}</span></td>
            <td class="num">{{ line.amount > 0 ? formatGnf(line.amount) : '' }}</td>
            <td class="num">{{ line.amount < 0 ? formatGnf(-line.amount) : '' }}</td>
          </tr>
        </table>
      </div>
      <p v-if="journal.length" class="text-muted text-fine mt-1">Colonnes : débit, crédit.</p>
      <v-btn v-if="journalPage < journalPages" variant="text" block @click="loadJournal(false)">Voir plus</v-btn>
    </section>

    <!-- Règles -->
    <section v-else class="card settings">
      <h2 class="settings__title">Répartition à la livraison</h2>
      <p class="text-muted text-meta mb-4">
        Pour chaque colis payé en ligne et livré : le vendeur reçoit le montant des articles moins sa commission,
        le livreur une part des frais de livraison, le point de retrait un montant fixe pris sur la part Ndjouri.
      </p>
      <div class="settings__grid">
        <v-text-field v-model="settings.courier_delivery_share_percent" label="Part livreur des frais de livraison" suffix="%" type="number" variant="outlined" />
        <v-text-field v-model="settings.pickup_point_fee_per_parcel" label="Rémunération point de retrait / colis" suffix="GNF" type="number" variant="outlined" />
        <v-text-field v-model="settings.earnings_hold_days" label="Délai avant disponibilité" suffix="jours" type="number" variant="outlined" hint="Couvre litiges et retours." persistent-hint />
      </div>
      <h2 class="settings__title mt-4">Retraits</h2>
      <div class="settings__grid">
        <v-text-field v-model="settings.withdrawal_fee_percent" label="Frais d'envoi facturés" suffix="%" type="number" step="0.1" variant="outlined" hint="À caler sur la grille Djomy — l'écart est absorbé par Ndjouri." persistent-hint />
        <v-text-field v-model="settings.min_withdrawal_amount" label="Montant minimum" suffix="GNF" type="number" variant="outlined" />
      </div>
      <h2 class="settings__title mt-4">NdjouriBank (acheteurs)</h2>
      <p class="text-muted text-meta mb-2">
        Solde rechargé via Djomy et dépensé sur Ndjouri uniquement, jamais retirable. Fermé, plus aucune recharge ni
        remboursement « au choix » sur le solde — un solde existant reste utilisable pour payer.
      </p>
      <v-switch
        v-model="settings.buyer_wallet_enabled"
        color="primary"
        inset
        hide-details
        :label="settings.buyer_wallet_enabled ? 'Ouvert aux acheteurs' : 'Fermé (en attente de validation de conformité)'"
        class="mb-2"
      />
      <div class="settings__grid">
        <v-text-field v-model="settings.wallet_topup_min" label="Recharge minimum" suffix="GNF" type="number" variant="outlined" />
        <v-text-field v-model="settings.wallet_topup_max" label="Recharge maximum" suffix="GNF" type="number" variant="outlined" />
        <v-text-field v-model="settings.wallet_max_balance" label="Plafond du solde" suffix="GNF" type="number" variant="outlined" />
      </div>
      <v-btn color="primary" class="mt-4" :loading="savingSettings" @click="saveSettings">Enregistrer les règles</v-btn>
    </section>

    <!-- Confirmation versement -->
    <v-dialog :model-value="!!confirmTarget" max-width="420" @update:model-value="(v) => { if (!v) confirmTarget = null }">
      <v-card v-if="confirmTarget" class="pa-5">
        <h2 class="dialog-title">Verser {{ formatGnf(confirmTarget.net_amount) }} ?</h2>
        <p class="text-meta mb-2">
          À <strong>{{ confirmTarget.payout_beneficiary_name }}</strong> ({{ confirmTarget.owner_label }}) sur
          {{ payoutProviderLabel(confirmTarget.payout_provider) }} {{ confirmTarget.payout_account_number }}.
        </p>
        <p class="text-muted text-fine mb-0">
          Djomy prélève le montant et ses frais sur le solde marchand, qui doit être suffisamment approvisionné.
        </p>
        <div class="d-flex justify-end ga-2 mt-4">
          <v-btn variant="text" @click="confirmTarget = null">Annuler</v-btn>
          <v-btn color="primary" :loading="busyId === confirmTarget.id" @click="act(confirmTarget, 'approve')">Verser</v-btn>
        </div>
      </v-card>
    </v-dialog>

    <!-- Refus -->
    <v-dialog :model-value="!!rejectTarget" max-width="420" @update:model-value="(v) => { if (!v) rejectTarget = null }">
      <v-card v-if="rejectTarget" class="pa-5">
        <h2 class="dialog-title">Refuser ce retrait</h2>
        <p class="text-muted text-meta">Le montant revient immédiatement sur le solde de {{ rejectTarget.owner_label }}.</p>
        <v-textarea v-model="rejectReason" label="Motif (visible par le bénéficiaire)" rows="2" variant="outlined" />
        <div class="d-flex justify-end ga-2 mt-2">
          <v-btn variant="text" @click="rejectTarget = null"><PhX :size="14" class="mr-1" />Annuler</v-btn>
          <v-btn
            color="error"
            :disabled="rejectReason.trim().length < 3"
            :loading="busyId === rejectTarget.id"
            @click="act(rejectTarget, 'reject', { reason: rejectReason.trim() })"
          >
            Refuser
          </v-btn>
        </div>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
/* Couleurs catégorielles de la composition (palette validée en clair et en sombre). */
.finance {
  --fin-1: #2a78d6;
  --fin-2: #eb6834;
  --fin-3: #1baf7a;
  --fin-4: #eda100;
  --fin-5: #e87ba4;
}

:root[data-theme='dark'] .finance {
  --fin-1: #3987e5;
  --fin-2: #d95926;
  --fin-3: #199e70;
  --fin-4: #c98500;
  --fin-5: #d55181;
}

.finance__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.finance__title {
  margin: 0;
  font-family: var(--font-heading);
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--color-neutral-200);
}

.finance__sub {
  margin: 2px 0 0;
  font-size: 13px;
  color: var(--color-neutral-400);
}

.card {
  padding: 16px;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-lg);
  background: var(--color-neutral-900);
  box-shadow: var(--shadow-sm);
}

.treasury__top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.treasury__label {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-neutral-400);
}

.treasury__amount {
  font-family: var(--font-heading);
  font-size: 30px;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--color-neutral-200);
  font-variant-numeric: tabular-nums;
}

.balanced {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 12.5px;
  font-weight: 700;
  color: var(--color-success);
  background: color-mix(in srgb, var(--color-success) 12%, transparent);
}

.balanced--ko {
  color: var(--color-error);
  background: color-mix(in srgb, var(--color-error) 12%, transparent);
}

/* Barre empilée : 2px d'espace entre segments, extrémités arrondies. */
.stack {
  display: flex;
  gap: 2px;
  height: 14px;
  margin: 16px 0 12px;
  border-radius: 4px;
  overflow: hidden;
}

.stack__seg {
  flex-basis: 0;
  min-width: 4px;
}

.legend {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 6px 20px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.legend li {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.legend__dot {
  width: 10px;
  height: 10px;
  flex: none;
  border-radius: 3px;
}

.legend__label {
  flex: 1;
  color: var(--color-neutral-300);
}

.legend__value {
  font-weight: 700;
  color: var(--color-neutral-200);
  font-variant-numeric: tabular-nums;
}

.treasury__note {
  margin: 10px 0 0;
  font-size: 12.5px;
  color: var(--color-neutral-400);
}

.kpis {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 10px;
  margin: 12px 0 18px;
}

.kpi {
  padding: 14px;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-md);
  background: var(--color-neutral-900);
}

.kpi--accent {
  border-left: 4px solid var(--color-accent);
}

.kpi__label {
  font-size: 12px;
  color: var(--color-neutral-400);
}

.kpi__value {
  font-family: var(--font-heading);
  font-size: 19px;
  font-weight: 800;
  color: var(--color-neutral-200);
  font-variant-numeric: tabular-nums;
}

.kpi__sub {
  font-size: 12px;
  color: var(--color-neutral-400);
}

.tab-badge {
  margin-left: 6px;
  padding: 0 7px;
  border-radius: 999px;
  background: var(--color-accent);
  color: #fff;
  font-size: 11.5px;
  line-height: 18px;
}

.withdrawals {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 360px), 1fr));
  gap: 12px;
}

.withdrawal__head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
}

.withdrawal__owner {
  font-family: var(--font-heading);
  font-weight: 800;
  color: var(--color-neutral-200);
}

.withdrawal__facts {
  display: grid;
  gap: 4px;
  margin: 12px 0 0;
  font-size: 13px;
}

.withdrawal__facts > div {
  display: grid;
  grid-template-columns: 130px 1fr;
  gap: 8px;
}

.withdrawal__facts dt {
  color: var(--color-neutral-400);
}

.withdrawal__facts dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.withdrawal__net {
  font-weight: 800;
  color: var(--color-neutral-200);
}

.withdrawal__note {
  margin: 8px 0 0;
  font-size: 12.5px;
  color: var(--color-error);
}

.withdrawal__actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

.table-wrap {
  padding: 0;
  overflow-x: auto;
}

.table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.table th {
  padding: 10px 12px;
  text-align: left;
  font-size: 11.5px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-neutral-400);
  border-bottom: 1px solid var(--color-divider);
  white-space: nowrap;
}

.table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--color-divider);
  color: var(--color-neutral-300);
}

.table .num,
.tx__lines .num {
  text-align: right;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.strong {
  font-weight: 700;
  color: var(--color-neutral-200) !important;
}

.tx {
  margin-bottom: 10px;
}

.tx__head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}

.tx__kind {
  font-weight: 800;
  color: var(--color-neutral-200);
}

.tx__desc {
  margin: 2px 0 8px;
  font-size: 13px;
  color: var(--color-neutral-300);
}

.tx__link {
  margin-left: 6px;
  color: var(--color-primary-300);
  font-weight: 600;
  text-decoration: none;
}

.tx__lines {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}

.tx__lines td {
  padding: 4px 0;
  border-top: 1px dashed var(--color-divider);
  color: var(--color-neutral-300);
}

.tx__lines td.num {
  width: 130px;
}

.settings {
  max-width: 760px;
}

.settings__title {
  margin: 0 0 6px;
  font-family: var(--font-heading);
  font-size: 16px;
  font-weight: 800;
  color: var(--color-neutral-200);
}

.settings__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 8px 12px;
}

.dialog-title {
  margin: 0 0 10px;
  font-family: var(--font-heading);
  font-size: 18px;
  font-weight: 800;
}
</style>
