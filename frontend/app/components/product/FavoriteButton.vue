<script setup lang="ts">
import { PhHeart } from '@phosphor-icons/vue'

/**
 * Cœur "favori" : sur la photo d'une carte produit (variant "overlay") ou
 * dans l'en-tête de la fiche. Un visiteur non connecté est envoyé vers la
 * connexion, avec retour sur la page en cours.
 */
const props = withDefaults(defineProps<{ productId: string; variant?: 'overlay' | 'plain' }>(), {
  variant: 'overlay',
})

const favorites = useFavoritesStore()
const auth = useAuthStore()
const route = useRoute()
const toast = useToastStore()

const active = computed(() => favorites.has(props.productId))
const pop = ref(false)

onMounted(() => favorites.ensureLoaded())

async function onClick(event: MouseEvent) {
  // Sur une carte, le cœur est dans le lien vers la fiche : ne pas l'ouvrir.
  event.preventDefault()
  event.stopPropagation()
  if (!auth.isAuthenticated) {
    await navigateTo({ path: '/connexion', query: { redirect: route.fullPath } })
    return
  }
  try {
    const added = await favorites.toggle(props.productId)
    if (added) {
      pop.value = true
      setTimeout(() => (pop.value = false), 400)
      toast.success('Ajouté à vos favoris.')
    }
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de modifier vos favoris.'))
  }
}
</script>

<template>
  <button
    type="button"
    class="fav"
    :class="[`fav--${variant}`, { 'fav--active': active, 'fav--pop': pop }]"
    :aria-pressed="active"
    :aria-label="active ? 'Retirer des favoris' : 'Ajouter aux favoris'"
    @click="onClick"
  >
    <PhHeart :size="variant === 'overlay' ? 17 : 21" :weight="active ? 'fill' : 'bold'" />
  </button>
</template>

<style scoped>
.fav {
  display: flex;
  align-items: center;
  justify-content: center;
  border: 0;
  padding: 0;
  cursor: pointer;
  color: var(--color-neutral-400);
  transition: color 0.15s ease, transform 0.15s ease;
}

.fav--overlay {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
  color: #6e7079;
}

.fav--plain {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: none;
  color: var(--color-neutral-300);
}

.fav--plain:hover {
  background: var(--color-neutral-800);
}

.fav--active {
  color: #e5484d !important;
}

.fav--pop {
  animation: fav-pop 0.4s ease;
}

@keyframes fav-pop {
  40% {
    transform: scale(1.3);
  }
  100% {
    transform: scale(1);
  }
}
</style>
