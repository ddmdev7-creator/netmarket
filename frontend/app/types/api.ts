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
export type PaymentMethod = 'cash_on_delivery'
export type PaymentStatus = 'pending' | 'paid' | 'failed' | 'cancelled'
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
  vendor_shop_name: string | null
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

/** pickup_dropoff_token is the courier's own QR payload for a pickup_point sub-order (set only while status is "shipped" and delivery_type is "pickup_point") — the pickup point manager scans it to confirm drop-off. */
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
  pickup_dropoff_token: string | null
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
  items: OrderItemRead[]
  /** null for orders placed before the delivery-estimate feature existed. */
  estimated_delivery_min: string | null
  estimated_delivery_max: string | null
}

/** Buyer-facing shape, nested under OrderRead. delivery_token is the buyer's own private QR payload (set only while status is "shipped") — the vendor never receives this field, only what their camera reads off it. */
export interface SubOrderRead extends SubOrderBase {
  delivery_token: string | null
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
  payment_method: PaymentMethod
  payment_status: PaymentStatus | null
  total: number
  created_at: string
  sub_orders: SubOrderRead[]
}

/** Sub-order shape for the admin's own order detail (GET /admin/orders/{id}) — adds the vendor account (not just the frozen shop_name) and courier info. */
export interface AdminSubOrderRead extends SubOrderBase {
  courier_name: string | null
  courier_phone: string | null
  storage_location: string | null
  vendor_owner_phone: string | null
  vendor_owner_email: string | null
  vendor_owner_full_name: string | null
}

/** Full order detail for the admin — order + buyer account + per-sub-order vendor/courier info. */
export interface AdminOrderRead {
  id: string
  status: OrderStatus
  delivery_address: string
  delivery_type: DeliveryType
  delivery_zone: string | null
  delivery_instructions: string | null
  recipient_name: string | null
  recipient_phone: string | null
  pickup_point_contacts: PickupPointContactRead[]
  payment_method: PaymentMethod
  payment_status: PaymentStatus | null
  total: number
  created_at: string
  sub_orders: AdminSubOrderRead[]
  buyer_phone: string
  buyer_email: string | null
  buyer_full_name: string | null
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
