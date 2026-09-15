<script setup lang="ts">
import jsQR from 'jsqr'
import { PhX } from '@phosphor-icons/vue'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [boolean]; decode: [string] }>()

const videoEl = ref<HTMLVideoElement | null>(null)
const canvasEl = ref<HTMLCanvasElement | null>(null)
const error = ref('')

let stream: MediaStream | null = null
let rafId: number | null = null

function stopCamera() {
  if (rafId !== null) cancelAnimationFrame(rafId)
  rafId = null
  stream?.getTracks().forEach((track) => track.stop())
  stream = null
}

function scanFrame() {
  const video = videoEl.value
  const canvas = canvasEl.value
  if (!video || !canvas || video.readyState !== video.HAVE_ENOUGH_DATA) {
    rafId = requestAnimationFrame(scanFrame)
    return
  }

  canvas.width = video.videoWidth
  canvas.height = video.videoHeight
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
  const frame = ctx.getImageData(0, 0, canvas.width, canvas.height)
  const result = jsQR(frame.data, frame.width, frame.height, { inversionAttempts: 'dontInvert' })

  if (result?.data) {
    emit('decode', result.data)
    close()
    return
  }
  rafId = requestAnimationFrame(scanFrame)
}

async function startCamera() {
  error.value = ''
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
    if (videoEl.value) {
      videoEl.value.srcObject = stream
      await videoEl.value.play()
    }
    rafId = requestAnimationFrame(scanFrame)
  } catch {
    error.value = "Impossible d'accéder à la caméra. Vérifie que l'autorisation caméra est accordée à ce site."
  }
}

function close() {
  stopCamera()
  emit('update:modelValue', false)
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) nextTick(startCamera)
    else stopCamera()
  },
)

onBeforeUnmount(stopCamera)
</script>

<template>
  <v-dialog :model-value="modelValue" fullscreen persistent @update:model-value="close">
    <div class="scanner">
      <div class="scanner__header">
        <span>Scanner le code de livraison</span>
        <v-btn icon variant="text" color="white" @click="close">
          <PhX :size="22" />
        </v-btn>
      </div>

      <div class="scanner__viewport">
        <video ref="videoEl" muted playsinline class="scanner__video" />
        <div class="scanner__frame" />
      </div>

      <div class="scanner__footer">
        <p v-if="error" class="scanner__error">{{ error }}</p>
        <p v-else class="text-muted" style="font-size: 13px">
          Cadre le QR code affiché sur le téléphone de l'acheteur.
        </p>
      </div>

      <canvas ref="canvasEl" style="display: none" />
    </div>
  </v-dialog>
</template>

<style scoped>
.scanner {
  height: 100dvh;
  background: #000;
  display: flex;
  flex-direction: column;
}

.scanner__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: calc(12px + env(safe-area-inset-top, 0px)) 16px 12px;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
}

.scanner__viewport {
  position: relative;
  flex: 1;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.scanner__video {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.scanner__frame {
  position: absolute;
  width: 68%;
  aspect-ratio: 1;
  border: 3px solid var(--color-primary);
  border-radius: var(--radius-md);
  box-shadow: 0 0 0 999px rgba(0, 0, 0, 0.45);
}

.scanner__footer {
  padding: 16px 16px calc(20px + env(safe-area-inset-bottom, 0px));
  text-align: center;
}

.scanner__error {
  color: #f5a5a5;
  font-size: 13px;
}
</style>
