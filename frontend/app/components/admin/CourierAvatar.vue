<script setup lang="ts">
import { PhUser } from '@phosphor-icons/vue'
/**
 * Photo de visage d'un livreur, ou un avatar à ses initiales s'il n'en a pas
 * (livreur créé par un admin, antérieur à la vérification d'identité) ou si
 * elle ne se charge pas. La photo n'est pas publique : chargée en blob via
 * apiFetchBlob (voir composables/useApi.ts), puis libérée au démontage.
 */
const props = withDefaults(
  defineProps<{ courierId: string; photoKey: string | null; name: string | null; size?: number }>(),
  { size: 96 },
)

const { apiFetchBlob } = useApi()
const photoUrl = ref<string | null>(null)
const failed = ref(false)

const initials = computed(() => {
  const parts = (props.name ?? '').trim().split(/\s+/).filter(Boolean)
  return parts.slice(0, 2).map((p) => p[0]!.toUpperCase()).join('')
})

async function load() {
  if (photoUrl.value) URL.revokeObjectURL(photoUrl.value)
  photoUrl.value = null
  failed.value = false
  if (!props.photoKey) return
  try {
    const blob = await apiFetchBlob(`/couriers/${props.courierId}/documents/${props.photoKey}`)
    photoUrl.value = URL.createObjectURL(blob)
  } catch {
    failed.value = true
  }
}

onMounted(load)
watch(() => [props.courierId, props.photoKey], load)
onBeforeUnmount(() => {
  if (photoUrl.value) URL.revokeObjectURL(photoUrl.value)
})
</script>

<template>
  <div
    class="courier-avatar"
    :style="{ width: `${size}px`, height: `${size}px`, fontSize: `${Math.round(size * 0.36)}px` }"
    :title="photoKey && failed ? 'Photo indisponible' : undefined"
  >
    <img v-if="photoUrl" :src="photoUrl" :alt="`Photo de ${name ?? 'livreur'}`" />
    <span v-else-if="initials" aria-hidden="true">{{ initials }}</span>
    <PhUser v-else :size="Math.round(size * 0.5)" aria-hidden="true" />
  </div>
</template>

<style scoped>
.courier-avatar {
  flex: none;
  border-radius: 50%;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--color-primary) 18%, var(--color-neutral-800));
  color: var(--color-primary-300);
  font-family: var(--font-heading);
  font-weight: 700;
  border: 2px solid var(--color-divider-strong);
}

.courier-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
</style>
