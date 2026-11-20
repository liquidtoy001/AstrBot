<template>
  <svg
    class="subagent-star"
    :class="{ 'subagent-star--active': active, 'subagent-star--muted': muted }"
    :style="{ '--star-light': color.light, '--star-dark': color.dark }"
    viewBox="0 0 24 24"
    aria-hidden="true"
    focusable="false"
    xmlns="http://www.w3.org/2000/svg"
  >
    <path
      d="m246.3 328.1-17.8 41.2c-6.4 14.8-26.9 14.8-33.3 0l-17.8-41.2c-14.9-34.2-41.8-61.4-75.3-76.3l-48.8-21.6c-14.7-6.5-14.7-27.9 0-34.4l47.2-21c34.4-15.3 61.7-43.5 76.4-78.8l18-43.7c6.3-15.2 27.3-15.2 33.6 0l18 43.7c14.7 35.3 42 63.6 76.4 78.8l47.2 21c14.7 6.5 14.7 27.9 0 34.4l-48.8 21.6c-33.5 14.8-60.4 42.1-75.3 76.2z"
      fill="currentColor"
      transform="matrix(0.0634 0 0 0.0634 -1.42 -1.35)"
    />
  </svg>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { subagentColor } from "@/composables/useSessionSubagents";

// The large star of the AstrBot logo (static ChatUI logo shape), colored per
// sub-agent so the chip under a reply and the session panel row match.
const props = defineProps<{
  agentId: string;
  active?: boolean;
  muted?: boolean;
}>();

const color = computed(() => subagentColor(props.agentId));
</script>

<style scoped>
.subagent-star {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  color: var(--star-light);
}

.v-theme--dark .subagent-star {
  color: var(--star-dark);
}

.subagent-star--muted {
  opacity: 0.45;
}

/* Breathes in step with the activity text of a running chip or panel row. */
.subagent-star--active {
  animation: subagent-star-breathe 2s ease-in-out infinite;
}

@keyframes subagent-star-breathe {
  0%,
  100% {
    opacity: 0.4;
  }
  50% {
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .subagent-star--active {
    animation: none;
  }
}
</style>
