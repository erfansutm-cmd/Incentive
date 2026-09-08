<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({
  titleId: { type: String, required: true },
  busy: { type: Boolean, default: false },
})
const emit = defineEmits(['close'])
const dialog = ref(null)

function close() {
  if (!props.busy) emit('close')
}

function onBackdrop(event) {
  if (event.target !== dialog.value) return
  const rect = dialog.value.getBoundingClientRect()
  if (event.clientX < rect.left || event.clientX > rect.right ||
      event.clientY < rect.top || event.clientY > rect.bottom) close()
}

// Native dialogs trap focus, support Escape and restore focus on close.
onMounted(() => dialog.value.showModal())
onBeforeUnmount(() => dialog.value?.close())
</script>

<template>
  <dialog
    ref="dialog"
    class="modal"
    :aria-labelledby="titleId"
    :aria-busy="busy"
    @cancel.prevent="close"
    @click="onBackdrop"
  >
    <slot />
  </dialog>
</template>

<style scoped>
dialog.modal {
  border: none;
  margin: auto;
  width: calc(100% - 2rem);
  max-width: 520px;
  color: var(--text);
}
dialog::backdrop {
  background: rgba(30, 42, 36, 0.4);
}
</style>
