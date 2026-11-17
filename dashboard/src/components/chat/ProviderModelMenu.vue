<template>
  <ProviderSelectMenu
    ref="providerSelectMenuRef"
    :model-value="selectedProviderId"
    :fallback-model="selectedModelName"
    provider-type="chat_completion"
    :variant="variant"
    :allow-empty="true"
    model-only
    preload
    @update:model-value="updateSelection"
    @select="saveSelection"
  >
    <template v-if="reasoningEffort || fastMode" #trigger-suffix>
      <span v-if="reasoningEffort" class="effort-chip">
        {{ tm(`reasoningEffort.levels.${reasoningEffort}`) }}
      </span>
      <span v-if="fastMode" class="effort-chip fast-chip">
        <v-icon size="12">mdi-lightning-bolt</v-icon>
        {{ tm("fastMode.chip") }}
      </span>
    </template>
    <!-- Per-conversation thinking level; the backend maps it per provider type. -->
    <template #top>
      <div class="effort-section">
        <div class="effort-section-head">
          <span class="effort-section-title">{{
            tm("reasoningEffort.title")
          }}</span>
          <span class="effort-section-hint">{{
            tm("reasoningEffort.hint")
          }}</span>
        </div>
        <div v-if="effortLevels.length" class="effort-options" role="group">
          <button
            v-for="option in effortLevels"
            :key="option"
            type="button"
            class="effort-option"
            :class="{ active: reasoningEffort === option }"
            :aria-pressed="reasoningEffort === option"
            @click="reasoningEffort = option"
          >
            {{ tm(`reasoningEffort.levels.${option}`) }}
          </button>
        </div>
        <div v-else class="effort-section-hint">
          {{ tm("reasoningEffort.unsupported") }}
        </div>
      </div>
      <!-- Fast mode: only where the backend says the provider offers it. -->
      <div v-if="fastSupported" class="fast-section">
        <div class="fast-section-text">
          <span class="effort-section-title">{{ tm("fastMode.title") }}</span>
          <span class="effort-section-hint">{{ tm("fastMode.hint") }}</span>
        </div>
        <v-switch
          v-model="fastMode"
          color="primary"
          density="compact"
          hide-details
          inset
        />
      </div>
      <v-divider class="effort-menu-divider" />
    </template>
  </ProviderSelectMenu>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import ProviderSelectMenu from "@/components/shared/ProviderSelectMenu.vue";
import { useProviderModelSelection } from "@/composables/useProviderModelSelection";
import { useModuleI18n } from "@/i18n/composables";

interface ProviderSelection {
  id: string;
  model?: string;
}

const props = withDefaults(
  defineProps<{
    variant?: "input" | "header";
  }>(),
  {
    variant: "input",
  },
);

const {
  selectedProviderId,
  selectedModelName,
  setSelection,
  reasoningEffort,
  fastMode,
} = useProviderModelSelection();
const { tm } = useModuleI18n("features/chat");
const providerSelectMenuRef = ref<InstanceType<
  typeof ProviderSelectMenu
> | null>(null);
const variant = props.variant;

// Levels each provider type accepts. The backend maps them to the provider's
// own parameter (OpenAI reasoning_effort / Responses reasoning.effort,
// Anthropic effort or thinking budget, Gemini thinking level or budget); xAI
// accepts only low and high. Types not listed get no per-request level and use
// their configured setting.
const COMMON_LEVELS = ["low", "medium", "high"];
const EFFORT_LEVELS_BY_TYPE: Record<string, string[]> = {
  openai_chat_completion: COMMON_LEVELS,
  openai_responses: COMMON_LEVELS,
  openrouter_chat_completion: COMMON_LEVELS,
  aihubmix_chat_completion: COMMON_LEVELS,
  mirarouter_chat_completion: COMMON_LEVELS,
  groq_chat_completion: COMMON_LEVELS,
  xai_chat_completion: ["low", "high"],
  anthropic_chat_completion: COMMON_LEVELS,
  kimi_code_chat_completion: COMMON_LEVELS,
  minimax_token_plan: COMMON_LEVELS,
  xiaomi_token_plan: COMMON_LEVELS,
  googlegenai_chat_completion: COMMON_LEVELS,
};
const selectedProvider = computed(
  () =>
    providerSelectMenuRef.value?.selectedProvider as
      | {
          id?: string;
          type?: string;
          model?: string;
          supports_fast_mode?: boolean;
        }
      | undefined,
);
// The backend judges fast mode for the entry's configured model; another
// model picked in ChatUI is not offered it rather than silently ignored.
const fastSupported = computed(() => {
  const provider = selectedProvider.value;
  return (
    provider?.supports_fast_mode === true &&
    (!selectedModelName.value || selectedModelName.value === provider.model)
  );
});
// "Default model" has no known type here; offer the common levels.
const effortLevels = computed(() => {
  const type = selectedProvider.value?.type;
  return type ? EFFORT_LEVELS_BY_TYPE[type] || [] : COMMON_LEVELS;
});
// No "default" level: supported providers always get an explicit level (low
// unless chosen), so the menu always shows the current choice. Wait until the
// provider list matches the selection, or a stale type would reset the level.
watch(
  [
    effortLevels,
    reasoningEffort,
    selectedProviderId,
    selectedProvider,
    fastSupported,
  ],
  ([levels, effort]) => {
    if (
      selectedProviderId.value &&
      selectedProvider.value?.id !== selectedProviderId.value
    ) {
      return;
    }
    if (!levels.length) {
      if (effort) reasoningEffort.value = "";
    } else if (!levels.includes(effort)) {
      reasoningEffort.value = levels.includes("low") ? "low" : levels[0];
    }
    if (!fastSupported.value && fastMode.value) fastMode.value = false;
  },
  { immediate: true },
);

function updateSelection(value: string | string[]) {
  if (typeof value === "string") setSelection(value, selectedModelName.value);
}

function saveSelection(provider: ProviderSelection | null) {
  setSelection(provider?.id || "", provider?.model || "");
}

function getCurrentSelection() {
  return (
    providerSelectMenuRef.value?.getCurrentSelection() || {
      providerId: selectedProviderId.value,
      modelName: selectedModelName.value,
    }
  );
}

defineExpose({ getCurrentSelection });
</script>

<style scoped>
/* Slot content does not get ProviderSelectMenu's scoped styles. */
.effort-chip {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 7px;
  border-radius: 999px;
  background: rgba(var(--v-theme-primary), 0.14);
  color: rgb(var(--v-theme-primary));
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}

.fast-chip {
  gap: 2px;
}

.fast-section {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 4px 2px;
}

.fast-section-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.effort-section {
  padding: 4px 4px 2px;
}

.effort-section-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}

.effort-section-title {
  font-size: 0.88rem;
  font-weight: 600;
}

.effort-section-hint {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.55);
}

.effort-options {
  display: flex;
  gap: 4px;
  padding: 3px;
  border-radius: 10px;
  background: rgba(var(--v-theme-on-surface), 0.06);
}

.effort-option {
  flex: 1;
  height: 30px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.7);
  font-size: 0.85rem;
  cursor: pointer;
}

.effort-option:hover {
  color: rgb(var(--v-theme-on-surface));
}

.effort-option.active {
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25);
}

.effort-menu-divider {
  margin: 10px 0 6px;
}
</style>
