<script setup lang="ts">
import { PhMotorcycle } from '@phosphor-icons/vue'

const notifications = useNotificationStore()
const { apiFetch } = useApi()
const toast = useToastStore()
const router = useRouter()

const request = computed(() => notifications.pendingDeliveryRequest)
const responding = ref(false)

async function accept() {
  const subOrderId = request.value?.sub_order_id
  if (!subOrderId) return
  responding.value = true
  try {
    await apiFetch(`/orders/sub-orders/${subOrderId}/accept-delivery`, { method: 'POST' })
    toast.success('Livraison acceptée.')
    notifications.clearDeliveryRequest()
    await router.push('/livreur')
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'accepter cette livraison — elle a peut-être déjà été prise."))
    notifications.clearDeliveryRequest()
  } finally {
    responding.value = false
  }
}

async function decline() {
  const subOrderId = request.value?.sub_order_id
  if (!subOrderId) {
    notifications.clearDeliveryRequest()
    return
  }
  responding.value = true
  try {
    await apiFetch(`/orders/sub-orders/${subOrderId}/decline-delivery`, { method: 'POST' })
  } catch {
    // Best-effort — même si le refus explicite échoue, le minuteur côté
    // serveur avancera de toute façon à l'expiration (voir _run_dispatch).
  } finally {
    responding.value = false
    notifications.clearDeliveryRequest()
  }
}
</script>

<template>
  <v-dialog :model-value="!!request" max-width="360" persistent>
    <v-card v-if="request" class="pa-4">
      <div class="d-flex align-center ga-2 mb-3">
        <PhMotorcycle :size="24" color="var(--color-primary)" />
        <span class="text-h6 mb-0">Nouvelle demande de livraison</span>
      </div>
      <p class="mb-4" style="font-size: 13.5px">{{ request.body }}</p>
      <div class="d-flex ga-2">
        <v-btn variant="outlined" class="flex-grow-1" :disabled="responding" @click="decline">Refuser</v-btn>
        <v-btn color="primary" class="flex-grow-1" :loading="responding" @click="accept">Accepter</v-btn>
      </div>
    </v-card>
  </v-dialog>
</template>
