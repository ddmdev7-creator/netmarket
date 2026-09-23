/**
 * TypeScript mirror of the backend Pydantic schemas (see D:\netmarket\backend\app\**\schemas.py).
 * Keep in sync manually — there is no shared codegen between the two yet.
 */

export type UserRole = 'buyer' | 'vendor' | 'courier' | 'pickup_point_manager' | 'admin'
export type CourierStatus = 'pending' | 'approved' | 'rejected' | 'suspended'
export type VehicleType = 'moto' | 'taxi' | 'voiture'
export type IdDocumentType = 'cni_biometrique' | 'passeport'
export type CourierDocumentSlot = 'id_front' | 'id_back' | 'face' | 'vehicle'
export type VendorStatus = 'pending' | 'approved' | 'rejected' | 'suspended'
export type ProductStatus = 'active' | 'inactive'
export type OrderStatus =
  | 'pending'
  | 'confirmed'
  | 'preparing'
  | 'shipped'
  | 'arrived_at_pickup_point'
  | 'delivered'
  | 'cancelled'
export type PaymentMethod = 'cash_on_delivery' | 'online' | 'wallet'
export type PaymentStatus = 'pending' | 'paid' | 'failed' | 'cancelled' | 'refund_pending' | 'refunded' | 'refund_failed'
export type DeliveryType = 'home_delivery' | 'pickup_point'
export type SubscriptionStatus = 'pending' | 'active' | 'expired' | 'cancelled'

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface UserRead {
  id: string
  phone: string
  first_name: string | null
  last_name: string | null
  email: string | null
  email_verified: boolean
  role: UserRole
  is_active: boolean
  /** Vrai si ce compte gère aussi un point de retrait (boutique liée), sans que son rôle principal change. */
  is_pickup_point_manager: boolean
}

export interface UserUpdate {
  first_name?: string | null
  last_name?: string | null
  email?: string | null
}

export interface VendorRead {
  id: string
  user_id: string
  shop_name: string
  status: VendorStatus
  zone: string | null
  latitude: number | null
  longitude: number | null
  owner_phone: string | null
  owner_email: string | null
  owner_full_name: string | null
  commission_rate: number
  preparation_days: number
}

/** Vue publique (/vendors) — sans compte propriétaire ni commission, voir VendorRead. */
export interface VendorPublicRead {
  id: string
  shop_name: string
  zone: string | null
  latitude: number | null
  longitude: number | null
  preparation_days: number
}

export interface SubscriptionPlanRead {
  id: string
  name: string
  price_gnf: number
  duration_days: number
}

export interface VendorSubscriptionRead {
  id: string
  vendor_id: string
  status: SubscriptionStatus
  started_at: string | null
  expires_at: string | null
  plan: SubscriptionPlanRead
}

export interface AddressRead {
  id: string
  label: string
  delivery_type: DeliveryType
  zone: string
  pickup_point_id: string | null
  recipient_name: string | null
  recipient_phone: string | null
  instructions: string | null
  latitude: number | null
  longitude: number | null
  is_default: boolean
}

export interface AddressCreate {
  label: string
  delivery_type: DeliveryType
  zone: string
  pickup_point_id?: string | null
  recipient_name?: string | null
  recipient_phone?: string | null
  instructions?: string | null
  latitude?: number | null
  longitude?: number | null
  is_default?: boolean
}

export type AddressUpdate = Partial<AddressCreate>

export interface PickupPointRead {
  id: string
  name: string
  zone: string
  latitude: number | null
  longitude: number | null
  is_active: boolean
  /** Renseigné quand ce point est la boutique d'un vendeur plutôt qu'un local dédié. */
  vendor_id: string | null
  opening_hours: string | null
  vendor_shop_name: string | null
  /** Transitoires — voir ReviewRead/average_rating sur les produits. */
  average_rating: number | null
  review_count: number
}

export interface PickupPointReviewCreate {
  rating: number
  comment?: string | null
}

export interface PickupPointReviewRead {
  id: string
  pickup_point_id: string
  user_id: string
  rating: number
  comment: string | null
  created_at: string
}

export interface PickupPointCreate {
  name: string
  zone: string
  latitude?: number | null
  longitude?: number | null
  is_active?: boolean
  vendor_id?: string | null
}

export type PickupPointUpdate = Partial<PickupPointCreate>

export interface VendorAdminUpdate {
  status?: VendorStatus
  commission_rate?: number
}

export interface CourierRead {
  id: string
  user_id: string
  vehicle_type: VehicleType
  zone: string | null
  status: CourierStatus
  is_online: boolean
  phone: string
  full_name: string | null
  /** Transitoires — voir ReviewRead/average_rating sur les produits. */
  average_rating: number | null
  review_count: number
}

export interface CourierReviewCreate {
  rating: number
  comment?: string | null
}

export interface CourierReviewRead {
  id: string
  courier_id: string
  user_id: string
  rating: number
  comment: string | null
  created_at: string
}

/** Vue complète (/couriers/me, /admin/couriers) — jamais l'annuaire public, voir CourierRead. */
export interface CourierDetailRead extends CourierRead {
  id_document_type: IdDocumentType | null
  id_document_front_key: string | null
  id_document_back_key: string | null
  face_photo_key: string | null
  vehicle_name: string | null
  vehicle_plate_number: string | null
  vehicle_photo_keys: string[]
  admin_note: string | null
  latitude: number | null
  longitude: number | null
}

/** GET /admin/deliveries/active — colis confirmés, en préparation ou en route. */
export interface ActiveDeliveryRead {
  sub_order_id: string
  order_id: string
  status: OrderStatus
  vendor_id: string
  shop_name: string
  created_at: string
  /** Position actuelle de la boutique (lue en direct). */
  origin_latitude: number | null
  origin_longitude: number | null
  delivery_type: DeliveryType
  delivery_zone: string | null
  delivery_address: string
  pickup_point_name: string | null
  /** Figée au checkout ; absente pour un domicile sans GPS ou une commande antérieure. */
  destination_latitude: number | null
  destination_longitude: number | null
  courier_id: string | null
  dispatch_offered_courier_id: string | null
}

export interface CourierAvailabilityUpdate {
  is_online: boolean
  latitude?: number | null
  longitude?: number | null
}

export interface CourierRegister {
  vehicle_type: VehicleType
  zone?: string | null
  id_document_type: IdDocumentType
  id_document_front_key: string
  id_document_back_key?: string | null
  face_photo_key: string
  vehicle_name: string
  vehicle_plate_number: string
  vehicle_photo_keys: string[]
}

export interface CourierAdminCreate {
  phone: string
  email: string
  first_name?: string | null
  last_name?: string | null
}

export interface CourierInvitationRead {
  user_id: string
  phone: string
  email: string
}

export interface CourierAdminUpdate {
  status?: CourierStatus
  admin_note?: string | null
}

export interface CourierAssignRequest {
  courier_id: string | null
}

export interface DispatchRequest {
  vehicle_type?: VehicleType | null
}

/** One staff member of a pickup point, looked up live at read time (never frozen on the order — see backend PickupPointContactRead docstring). */
export interface PickupPointContactRead {
  name: string | null
  phone: string
}

/** dropoff_handoff_ready: the courier has a drop-off QR to show at the pickup point (code fetched from GET /orders/sub-orders/{id}/handoff-code). */
export interface CourierSubOrderRead {
  id: string
  order_id: string
  shop_name: string
  status: OrderStatus
  items: OrderItemRead[]
  created_at: string
  delivery_address: string
  delivery_type: DeliveryType
  delivery_zone: string | null
  delivery_instructions: string | null
  recipient_name: string | null
  recipient_phone: string | null
  pickup_point_contacts: PickupPointContactRead[]
  dropoff_handoff_ready: boolean
}

export interface PickupPointManagerRead {
  id: string
  user_id: string
  pickup_point_id: string
  phone: string
  full_name: string | null
}

export interface PickupPointManagerAdminCreate {
  phone: string
  password: string
  first_name?: string | null
  last_name?: string | null
  pickup_point_id: string
}

export interface PickupPointManagerAdminUpdate {
  pickup_point_id?: string | null
}

/** Sub-order shape for the pickup point manager's own dashboard — mirrors CourierSubOrderRead, plus who's dropping it off. */
export interface PickupPointManagerSubOrderRead {
  id: string
  order_id: string
  shop_name: string
  status: OrderStatus
  items: OrderItemRead[]
  created_at: string
  delivery_address: string
  delivery_type: DeliveryType
  delivery_zone: string | null
  delivery_instructions: string | null
  courier_name: string | null
  courier_phone: string | null
  storage_location: string | null
  customer_name: string | null
  customer_phone: string | null
  /** Dernier changement de statut (arrivée au point pour un colis en stock). */
  updated_at: string
}

export interface LowStockProduct {
  id: string
  name: string
  stock: number
}

export interface DailyOrderCount {
  day: string
  order_count: number
}

export interface VendorDashboard {
  total_orders: number
  active_orders: number
  delivered_orders: number
  cancelled_orders: number
  revenue_delivered: number
  commission_due: number
  net_revenue: number
  active_product_count: number
  low_stock_products: LowStockProduct[]
  out_of_stock_products: LowStockProduct[]
}

export interface CategoryRead {
  id: string
  name: string
  parent_id: string | null
}

export interface CategoryCreate {
  name: string
  parent_id?: string | null
}

/** PATCH /categories/{id} — parent_id null moves the category back to the root; omit a key to leave it unchanged. */
export interface CategoryUpdate {
  name?: string
  parent_id?: string | null
}

export interface ProductVariantAttributeRead {
  name: string
  value: string
}

export interface ProductVariantRead {
  id: string
  product_id: string
  sku: string | null
  /** Absolute override — null means "same price as the product". */
  price: number | null
  stock: number
  /** Absolute override — null means "same photos as the product". */
  images: string[] | null
  attributes: ProductVariantAttributeRead[]
}

export interface ProductVariantAttributeCreate {
  name: string
  value: string
}

export interface ProductVariantCreate {
  sku?: string | null
  price?: number | null
  stock?: number
  images?: string[] | null
  attributes: ProductVariantAttributeCreate[]
}

export interface ProductVariantUpdate {
  sku?: string | null
  price?: number | null
  stock?: number
  images?: string[] | null
  /** Provided = wholesale replace of the attribute set. */
  attributes?: ProductVariantAttributeCreate[] | null
}

export interface ProductRead {
  id: string
  vendor_id: string
  vendor_shop_name: string
  category_id: string
  name: string
  description: string | null
  price: number
  stock: number
  images: string[]
  status: ProductStatus
  average_rating: number | null
  review_count: number
  /** Generic estimate — buyer's zone unknown on the catalog. See app/catalog/service.py::_attach_delivery_estimate. */
  estimated_delivery_min: string | null
  estimated_delivery_max: string | null
  /** Empty when the product has no variants (stock/price stay at the product level). */
  variants: ProductVariantRead[]
}

export interface ReviewRead {
  id: string
  product_id: string
  user_id: string
  rating: number
  comment: string | null
  created_at: string
  updated_at: string
  /** Prénom + initiale (« Mamadou D. »), null si le compte n'a pas de prénom. */
  author_name: string | null
}

/** GET /reviews/mine — un produit reçu par l'acheteur, avec son avis s'il en a laissé un. */
export interface ReviewableProductRead {
  product_id: string
  product_name: string
  product_image: string | null
  order_id: string
  delivered_at: string
  review: ReviewRead | null
}

export interface ReviewCreate {
  rating: number
  comment?: string | null
}

export type ReportType = 'product' | 'review'
export type ReportStatus = 'pending' | 'dismissed' | 'actioned'

export interface ReportCreate {
  reason: string
}

export interface ReportAdminUpdate {
  status: ReportStatus
  admin_note?: string | null
}

/** product_name/review_comment/review_rating are denormalized context attached at read time (never frozen) so the admin queue doesn't need to cross-reference /products or /reviews separately. */
export interface ReportRead {
  id: string
  reporter_id: string
  report_type: ReportType
  product_id: string | null
  review_id: string | null
  reason: string
  status: ReportStatus
  admin_note: string | null
  created_at: string
  product_name: string | null
  review_comment: string | null
  review_rating: number | null
}

export type ProductSort = 'recent' | 'price_asc' | 'price_desc'

export interface ProductFilters {
  category_id?: string
  min_price?: number
  max_price?: number
  in_stock?: boolean
  q?: string
  sort?: ProductSort
  page?: number
  page_size?: number
}

export type StockLevel = 'out' | 'low'

export interface MyProductFilters {
  category_id?: string
  status?: ProductStatus
  stock_level?: StockLevel
  sort?: ProductSort
  page?: number
  page_size?: number
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface CartItemRead {
  id: string
  product_id: string
  variant_id: string | null
  /** e.g. "Couleur : Rouge, Taille : M" — read live from the variant, never frozen (the cart always reflects the current catalog). */
  variant_label: string | null
  product_name: string
  product_image: string | null
  unit_price: number
  quantity: number
  subtotal: number
}

export interface VendorCartGroup {
  vendor_id: string
  shop_name: string
  items: CartItemRead[]
  subtotal: number
  /** Generic estimate — buyer's delivery address unknown at the cart stage. See app/cart/service.py::get_cart. */
  estimated_delivery_min: string | null
  estimated_delivery_max: string | null
}

export interface CartRead {
  vendors: VendorCartGroup[]
  total: number
}

export interface OrderItemRead {
  id: string
  product_id: string
  /** Frozen at checkout — stays correct even if the variant is edited/deleted afterward. */
  variant_id: string | null
  variant_label: string | null
  product_name: string
  /** Looked up live from the product/variant (like CartItemRead) — null if deleted since. */
  product_image: string | null
  quantity: number
  unit_price: number
}

interface SubOrderBase {
  id: string
  vendor_id: string
  shop_name: string
  status: OrderStatus
  amount: number
  commission: number
  /** Frozen at checkout (distance grid); not included in amount/commission. 0 for orders placed before delivery fees existed. */
  delivery_fee: number
  items: OrderItemRead[]
  /** null for orders placed before the delivery-estimate feature existed. */
  estimated_delivery_min: string | null
  estimated_delivery_max: string | null
}

/** Buyer-facing shape, nested under OrderRead. handoff_ready: it's the buyer's turn to show their handoff QR (code fetched separately, rotates every 60 s). */
export interface SubOrderRead extends SubOrderBase {
  handoff_ready: boolean
  /** courier_id is a real column; the rest is looked up live (see backend service). No courier_phone here — unlike the vendor, a buyer has no need to call their courier directly. */
  courier_id: string | null
  courier_name: string | null
  courier_status: CourierStatus | null
  courier_average_rating: number | null
  courier_review_count: number
}

/** Sub-order shape returned by the vendor-facing endpoints (GET/PATCH /orders/sub-orders/...) — adds the order-level fields a vendor needs to fulfill the order. */
export interface VendorSubOrderRead extends SubOrderBase {
  order_id: string
  created_at: string
  delivery_address: string
  delivery_type: DeliveryType
  delivery_zone: string | null
  delivery_instructions: string | null
  recipient_name: string | null
  recipient_phone: string | null
  pickup_point_contacts: PickupPointContactRead[]
  courier_id: string | null
  courier_name: string | null
  courier_phone: string | null
  dispatch_offered_courier_id: string | null
  dispatch_offered_courier_name: string | null
}

/** POST /orders/delivery-quote — same computation as checkout, per vendor parcel. */
export interface DeliveryQuoteRead {
  vendors: {
    vendor_id: string
    shop_name: string
    delivery_fee: number
    estimated_delivery_min: string
    estimated_delivery_max: string
  }[]
  items_total: number
  delivery_total: number
  total: number
}

/** One row of the admin distance grid; max_km null = "au-delà" catch-all (also the fallback when a position is missing). */
export interface DeliveryFeeTierRead {
  id: string
  max_km: number | null
  fee: number
  /** Free-text zone description for the admin; informational only. */
  label: string | null
  /** Extra transit days for this tier, on top of the vendor's own preparation time. */
  transit_days: number
}

export interface DeliveryFeeTierCreate {
  max_km: number | null
  fee: number
  label: string | null
  transit_days: number
}

export type DeliveryFeeTierUpdate = Partial<DeliveryFeeTierCreate>

/** GET/PATCH /admin/payment-settings — informational delay shown to the buyer after a refund is initiated (see PaymentStatus 'refund_pending'). */
export interface PaymentSettingsRead {
  refund_delay_hours: number
}

export interface PaymentSettingsUpdate {
  refund_delay_hours: number
}

export interface OrderRead {
  id: string
  status: OrderStatus
  delivery_address: string
  delivery_type: DeliveryType
  delivery_zone: string | null
  delivery_instructions: string | null
  recipient_name: string | null
  recipient_phone: string | null
  pickup_point_contacts: PickupPointContactRead[]
  /** pickup_point_id is a real column; the rest is looked up live (see backend service). */
  pickup_point_id: string | null
  pickup_point_name: string | null
  pickup_point_average_rating: number | null
  pickup_point_review_count: number
  payment_method: PaymentMethod
  payment_status: PaymentStatus | null
  /** Only set right after POST /orders/checkout for an online payment — redirect the buyer here immediately. */
  payment_redirect_url: string | null
  /** Only set while payment_status === 'refund_pending' — admin-configured estimate. */
  refund_delay_hours: number | null
  /** Déjà remboursé sur le solde NdjouriBank (commande ou sous-commandes annulées). */
  wallet_refunded_amount: number
  total: number
  created_at: string
  sub_orders: SubOrderRead[]
}

/** La boutique d'une sous-commande telle qu'elle est aujourd'hui + le compte de son propriétaire. */
export interface AdminVendorInfo {
  id: string
  shop_name: string
  status: VendorStatus
  zone: string | null
  latitude: number | null
  longitude: number | null
  commission_rate: number
  preparation_days: number
  created_at: string
  owner_full_name: string | null
  owner_phone: string | null
  owner_email: string | null
}

/** Livreur d'une sous-commande. face_photo_key se charge via GET /couriers/{id}/documents/{key} (pas public). */
export interface AdminCourierInfo {
  id: string
  full_name: string | null
  phone: string
  status: CourierStatus
  vehicle_type: VehicleType
  vehicle_name: string | null
  vehicle_plate_number: string | null
  zone: string | null
  is_online: boolean
  face_photo_key: string | null
  average_rating: number | null
  review_count: number
}

export interface AdminBuyerInfo {
  id: string
  full_name: string | null
  phone: string
  email: string | null
  email_verified: boolean
  is_active: boolean
  created_at: string
  order_count: number
}

export interface AdminPickupPointInfo {
  id: string
  name: string
  zone: string
  latitude: number | null
  longitude: number | null
  is_active: boolean
  vendor_shop_name: string | null
  average_rating: number | null
  review_count: number
}

/** Sub-order shape for the admin's own order detail (GET /admin/orders/{id}). */
export interface AdminSubOrderRead extends SubOrderBase {
  created_at: string
  updated_at: string
  storage_location: string | null
  vendor: AdminVendorInfo | null
  courier: AdminCourierInfo | null
  dispatch_offered_courier_name: string | null
}

/** Full order detail for the admin — order + buyer account + pickup point + per-sub-order vendor/courier. */
export interface AdminOrderRead {
  id: string
  status: OrderStatus
  delivery_address: string
  delivery_type: DeliveryType
  delivery_zone: string | null
  delivery_instructions: string | null
  delivery_latitude: number | null
  delivery_longitude: number | null
  recipient_name: string | null
  recipient_phone: string | null
  pickup_point_contacts: PickupPointContactRead[]
  payment_method: PaymentMethod
  payment_status: PaymentStatus | null
  total: number
  created_at: string
  sub_orders: AdminSubOrderRead[]
  buyer: AdminBuyerInfo | null
  pickup_point: AdminPickupPointInfo | null
}

/** GET /admin/deliveries/monitor — une ligne de l'écran de suivi des livraisons. */
export interface DeliveryMonitorEntry {
  sub_order_id: string
  order_id: string
  status: OrderStatus
  created_at: string
  /** Dernier changement (statut/livreur) de la sous-commande. */
  updated_at: string
  estimated_delivery_min: string | null
  estimated_delivery_max: string | null
  amount: number
  delivery_fee: number
  payment_method: PaymentMethod
  vendor_id: string
  shop_name: string
  vendor_zone: string | null
  delivery_type: DeliveryType
  delivery_zone: string | null
  delivery_address: string
  pickup_point_name: string | null
  storage_location: string | null
  buyer_name: string | null
  buyer_phone: string | null
  courier_id: string | null
  courier_name: string | null
  courier_phone: string | null
  courier_is_online: boolean | null
  dispatch_offered_courier_id: string | null
  dispatch_offered_courier_name: string | null
}

export interface DeliveryMonitorRead {
  generated_at: string
  /** Début de journée pris pour « livrées aujourd'hui ». */
  since: string
  entries: DeliveryMonitorEntry[]
}

export interface AdminTopProduct {
  product_id: string
  product_name: string
  quantity_sold: number
}

export interface AdminTopVendor {
  vendor_id: string
  shop_name: string
  revenue: number
}

export interface AdminStats {
  total_vendors: number
  pending_vendors: number
  approved_vendors: number
  total_products: number
  total_orders: number
  orders_by_status: Record<OrderStatus, number>
  total_sales: number
  total_commission: number
  top_products: AdminTopProduct[]
  top_vendors: AdminTopVendor[]
  /** 30 derniers jours, jours sans activité inclus (à zéro). */
  daily_activity: AdminDailyActivity[]
  orders_by_payment_method: Record<PaymentMethod, number>
  users_by_role: Record<UserRole, number>
}

export interface AdminDailyActivity {
  date: string
  orders: number
  /** Montant des commandes passées ce jour-là, hors annulées. */
  order_amount: number
  signups: number
}

export interface ApiError {
  detail: string
  errors?: unknown[]
}

export type NotificationType =
  | 'order_received'
  | 'order_status_changed'
  | 'courier_verification_approved'
  | 'courier_verification_rejected'
  | 'delivery_request'
  | 'delivery_request_accepted'
  | 'delivery_no_courier_found'

export interface NotificationRead {
  id: string
  type: NotificationType
  title: string
  body: string
  order_id: string | null
  sub_order_id: string | null
  read_at: string | null
  created_at: string
}

export interface NotificationList {
  items: NotificationRead[]
  unread_count: number
}

// --- Portefeuilles et compte principal (backend app/wallets) ---------------------

export type WalletKind = 'vendor' | 'courier' | 'pickup_point'
export type LedgerAccountKind =
  | WalletKind
  | 'buyer'
  | 'djomy_treasury'
  | 'order_escrow'
  | 'platform_revenue'
  | 'withdrawals_pending'
export type PayoutProvider = 'OM' | 'MOMO' | 'PAYCARD' | 'SOUTRA_MONEY' | 'KULU'
export type LedgerTransactionKind =
  | 'payment_captured'
  | 'sub_order_settled'
  | 'refund_completed'
  | 'withdrawal_requested'
  | 'withdrawal_reversed'
  | 'withdrawal_paid'
  | 'wallet_topup'
  | 'wallet_payment'
  | 'refund_to_wallet'
export type WithdrawalStatus = 'pending' | 'processing' | 'paid' | 'rejected' | 'cancelled' | 'failed'

export interface WalletBalance {
  /** Retirable maintenant. */
  available: number
  /** Gains dont le délai de sécurité n'est pas écoulé. */
  pending: number
  total: number
}

/** GET /wallets/mine — un portefeuille par rôle rémunéré de l'utilisateur. */
export interface WalletRead {
  id: string
  kind: WalletKind
  owner_id: string | null
  owner_label: string
  balance: WalletBalance
  /** Réservé par des retraits demandés ou en cours de versement (déjà déduit du solde). */
  withdrawals_in_progress: number
  payout_provider: PayoutProvider | null
  payout_account_number: string | null
  payout_beneficiary_name: string | null
  min_withdrawal_amount: number
  withdrawal_fee_percent: number
  earnings_hold_days: number
}

export interface WalletEntryRead {
  id: string
  created_at: string
  kind: LedgerTransactionKind
  description: string
  /** > 0 argent reçu, < 0 argent sorti (du point de vue du titulaire). */
  amount: number
  available_at: string
  is_pending: boolean
  order_id: string | null
  sub_order_id: string | null
  withdrawal_id: string | null
}

export interface PayoutMethodUpdate {
  payout_provider: PayoutProvider
  payout_account_number: string
  payout_beneficiary_name: string
}

export interface WithdrawalRead {
  id: string
  account_id: string
  status: WithdrawalStatus
  /** Débité du portefeuille = fee + net_amount. */
  amount: number
  fee: number
  net_amount: number
  fee_percent: number
  payout_provider: PayoutProvider
  payout_account_number: string
  payout_beneficiary_name: string
  admin_note: string | null
  created_at: string
  processed_at: string | null
}

export interface AdminWithdrawalRead extends WithdrawalRead {
  account_kind: LedgerAccountKind
  owner_label: string
  djomy_payout_id: string | null
  djomy_total_amount: number | null
}

/** GET /admin/finance/overview — le compte principal. */
export interface AdminFinanceOverview {
  treasury: number
  escrow: number
  beneficiaries_available: number
  beneficiaries_pending: number
  beneficiaries_total: number
  withdrawals_reserved: number
  platform_revenue: number
  /** Soldes NdjouriBank des acheteurs (non retirables). */
  buyer_wallets_total: number
  buyer_wallets_count: number
  is_balanced: boolean
  total_captured: number
  total_topped_up: number
  total_refunded: number
  total_paid_out: number
  withdrawals_pending_count: number
  withdrawals_pending_amount: number
  withdrawals_processing_count: number
  withdrawals_processing_amount: number
}

export interface AdminWalletRead {
  id: string
  kind: WalletKind | 'buyer'
  owner_id: string | null
  owner_label: string
  balance: WalletBalance
  withdrawals_in_progress: number
  payout_provider: PayoutProvider | null
  payout_account_number: string | null
}

export interface LedgerTransactionRead {
  id: string
  created_at: string
  kind: LedgerTransactionKind
  description: string
  order_id: string | null
  sub_order_id: string | null
  withdrawal_id: string | null
  /** Montants bruts : > 0 débit, < 0 crédit. */
  lines: { account_kind: LedgerAccountKind; owner_label: string; amount: number }[]
}

export interface EarningsSettings {
  courier_delivery_share_percent: number
  pickup_point_fee_per_parcel: number
  earnings_hold_days: number
  withdrawal_fee_percent: number
  min_withdrawal_amount: number
  buyer_wallet_enabled: boolean
  wallet_topup_min: number
  wallet_topup_max: number
  wallet_max_balance: number
}

// --- NdjouriBank (solde acheteur, backend app/wallets/buyer_service.py) ----------

export type TopUpStatus = 'pending' | 'paid' | 'failed' | 'cancelled'

/** GET /ndjouribank */
export interface BuyerWalletRead {
  /** Recharges ouvertes (réglage admin) — un solde existant reste toujours utilisable. */
  enabled: boolean
  balance: number
  topup_min: number
  topup_max: number
  max_balance: number
}

export interface TopUpRead {
  id: string
  amount: number
  status: TopUpStatus
  payer_phone: string
  created_at: string
  confirmed_at: string | null
}

/** POST /ndjouribank/topups */
export interface TopUpStarted {
  topup: TopUpRead
  redirect_url: string
}

// --- Remise des colis (QR opaques, backend app/orders/handoff.py) -----------------

/** GET /orders/sub-orders/{id}/handoff-code — `code` est tout le contenu du QR. */
export interface HandoffCodeRead {
  code: string
  expires_in: number
  window_seconds: number
}

/** GET /orders/sub-orders/{id}/delivery-offer — jamais le prix des articles. */
export interface DeliveryOfferRead {
  sub_order_id: string
  shop_name: string
  shop_zone: string | null
  distance_to_shop_km: number | null
  delivery_distance_km: number | null
  courier_earning: number
  item_count: number
  delivery_type: DeliveryType
  destination_zone: string
  delivery_instructions: string | null
  recipient_name: string | null
  pickup_point_name: string | null
  pickup_point_zone: string | null
  pickup_point_contacts: PickupPointContactRead[]
  expires_in_seconds: number
}

// --- Candidatures gestionnaire de point de retrait (backend app/pickup_point_applications) ---

export type PickupApplicationStatus = 'draft' | 'submitted' | 'changes_requested' | 'approved' | 'rejected'
export type PickupApplicationSlot = 'id_front' | 'id_back' | 'portrait' | 'premises'

export interface PickupApplicationDraft {
  first_name: string | null
  last_name: string | null
  birth_date: string | null
  residence_address: string | null
  id_document_type: IdDocumentType | null
  id_document_number: string | null
  id_document_front_key: string | null
  id_document_back_key: string | null
  portrait_photo_key: string | null
  point_name: string | null
  point_address: string | null
  point_landmark: string | null
  latitude: number | null
  longitude: number | null
  opening_hours: string | null
  storage_capacity: number | null
  premises_photo_keys: string[]
}

export interface PickupApplicationRead extends PickupApplicationDraft {
  id: string
  user_id: string
  status: PickupApplicationStatus
  origin: 'self' | 'invited'
  invited_at: string | null
  submitted_at: string | null
  submission_count: number
  admin_note: string | null
  admin_suggestion: string | null
  reviewed_at: string | null
  pickup_point_id: string | null
  /** Invitation à gérer un point existant : dossier réduit à l'identité. */
  target_pickup_point_id: string | null
  target_pickup_point_name: string | null
  created_at: string
  updated_at: string
}

/** GET /pickup-point-applications/me */
export interface MyPickupApplicationState {
  application: PickupApplicationRead | null
  can_apply: boolean
  blocked_reason: string | null
  min_premises_photos: number
  max_premises_photos: number
  portrait_min_width: number
  portrait_min_height: number
}

export interface AdminPickupApplicationRead extends PickupApplicationRead {
  applicant_phone: string
  applicant_email: string | null
}
