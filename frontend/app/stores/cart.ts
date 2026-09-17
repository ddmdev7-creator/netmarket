import { defineStore } from 'pinia'
import type { CartRead } from '~/types/api'

export const useCartStore = defineStore('cart', () => {
  const cart = ref<CartRead | null>(null)
  const loading = ref(false)

  const itemCount = computed(
    () => cart.value?.vendors.reduce((sum, group) => sum + group.items.reduce((s, i) => s + i.quantity, 0), 0) ?? 0,
  )

  async function fetchCart() {
    const { apiFetch } = useApi()
    loading.value = true
    try {
      cart.value = await apiFetch<CartRead>('/cart')
    } finally {
      loading.value = false
    }
  }

  async function addItem(productId: string, quantity = 1, variantId: string | null = null) {
    const { apiFetch } = useApi()
    cart.value = await apiFetch<CartRead>('/cart/items', {
      method: 'POST',
      body: { product_id: productId, variant_id: variantId, quantity },
    })
  }

  async function updateItem(itemId: string, quantity: number) {
    const { apiFetch } = useApi()
    cart.value = await apiFetch<CartRead>(`/cart/items/${itemId}`, { method: 'PATCH', body: { quantity } })
  }

  async function removeItem(itemId: string) {
    const { apiFetch } = useApi()
    cart.value = await apiFetch<CartRead>(`/cart/items/${itemId}`, { method: 'DELETE' })
  }

  async function clearCart() {
    const { apiFetch } = useApi()
    cart.value = await apiFetch<CartRead>('/cart', { method: 'DELETE' })
  }

  function reset() {
    cart.value = null
  }

  return { cart, loading, itemCount, fetchCart, addItem, updateItem, removeItem, clearCart, reset }
})
