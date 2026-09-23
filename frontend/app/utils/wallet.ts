/**
 * Libellés partagés des portefeuilles (components/wallet/WalletDashboard.vue),
 * du solde NdjouriBank acheteur (pages/ndjouribank.vue) et du compte
 * principal admin (pages/admin/finance).
 */
import type {
  LedgerAccountKind,
  LedgerTransactionKind,
  PaymentMethod,
  PayoutProvider,
  TopUpStatus,
  WithdrawalStatus,
} from '~/types/api'

export const PAYOUT_PROVIDERS: { value: PayoutProvider; title: string }[] = [
  { value: 'OM', title: 'Orange Money' },
  { value: 'MOMO', title: 'MTN Mobile Money' },
  { value: 'PAYCARD', title: 'PayCard' },
  { value: 'SOUTRA_MONEY', title: 'Soutra Money' },
  { value: 'KULU', title: 'Kulu' },
]

export function payoutProviderLabel(provider: PayoutProvider | null): string {
  return PAYOUT_PROVIDERS.find((p) => p.value === provider)?.title ?? '—'
}

export const WITHDRAWAL_STATUS_META: Record<WithdrawalStatus, { label: string; color: string }> = {
  pending: { label: 'En attente de validation', color: 'warning' },
  processing: { label: 'Versement en cours', color: 'info' },
  paid: { label: 'Versé', color: 'success' },
  rejected: { label: 'Refusé', color: 'error' },
  cancelled: { label: 'Annulé', color: 'secondary' },
  failed: { label: 'Échoué — recrédité', color: 'error' },
}

export const TRANSACTION_KIND_LABELS: Record<LedgerTransactionKind, string> = {
  payment_captured: 'Paiement reçu',
  sub_order_settled: 'Gain de livraison',
  refund_completed: 'Remboursement',
  withdrawal_requested: 'Retrait demandé',
  withdrawal_reversed: 'Retrait annulé',
  withdrawal_paid: 'Retrait versé',
  wallet_topup: 'Recharge',
  wallet_payment: 'Paiement de commande',
  refund_to_wallet: 'Remboursement',
}

export const ACCOUNT_KIND_LABELS: Record<LedgerAccountKind, string> = {
  djomy_treasury: 'Trésorerie Djomy',
  order_escrow: 'Séquestre',
  platform_revenue: 'Revenus Ndjouri',
  withdrawals_pending: 'Retraits en cours',
  vendor: 'Boutique',
  courier: 'Livreur',
  pickup_point: 'Point de retrait',
  buyer: 'NdjouriBank',
}

export const TOPUP_STATUS_META: Record<TopUpStatus, { label: string; color: string }> = {
  pending: { label: 'En attente de paiement', color: 'warning' },
  paid: { label: 'Créditée', color: 'success' },
  failed: { label: 'Échouée', color: 'error' },
  cancelled: { label: 'Annulée', color: 'secondary' },
}

// --- Moyens de paiement d'une commande ---------------------------------------------

export const PAYMENT_METHOD_LABELS: Record<PaymentMethod, { paid: string; short: string }> = {
  cash_on_delivery: { paid: 'Paiement à la livraison', short: 'À la livraison' },
  online: { paid: 'Payé en ligne', short: 'En ligne' },
  wallet: { paid: 'Payé avec NdjouriBank', short: 'NdjouriBank' },
}
