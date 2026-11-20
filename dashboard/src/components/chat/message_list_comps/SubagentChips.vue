<template>
  <div v-if="chips.length" class="subagent-chips">
    <button
      v-for="chip in chips"
      :key="chip.id"
      type="button"
      class="subagent-chip"
      :class="`subagent-chip--${chip.tone}`"
      :title="chip.title"
      :style="{
        '--agent-light': chip.color.light,
        '--agent-dark': chip.color.dark,
      }"
      @click="openAgent(chip.id)"
    >
      <SubagentStar
        :agent-id="chip.id"
        :active="chip.tone === 'active'"
        :muted="chip.tone === 'ended'"
      />
      <span class="subagent-chip-name">{{ chip.identity }}</span>
      <span class="subagent-chip-activity">{{ chip.activity }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, nextTick } from "vue";
import SubagentStar from "@/components/chat/SubagentStar.vue";
import {
  isSubagentActive,
  subagentActivity,
  subagentColor,
  subagentIdentity,
  subagentTaskName,
  useSessionSubagents,
} from "@/composables/useSessionSubagents";
import { useModuleI18n } from "@/i18n/composables";
import { workbenchKey } from "@/utils/chatViews";

// One chip per sub-agent a reply started, from the same polled state as the
// session panel; clicking one shows that agent in the panel.
const props = defineProps<{
  agentIds: string[];
}>();

const { tm } = useModuleI18n("features/chat");
const { byId, focusAgentId } = useSessionSubagents();
// Chips open the session view of the chat workbench.
const workbench = inject(workbenchKey, undefined);

const chips = computed(() =>
  props.agentIds.flatMap((id) => {
    const agent = byId.value.get(id);
    if (!agent) return [];
    const activity = subagentActivity(agent);
    return [
      {
        id,
        identity: subagentIdentity(agent),
        activity: tm(`sessionPanel.subagents.activity.${activity}`),
        title: subagentTaskName(agent),
        color: subagentColor(id),
        tone: isSubagentActive(agent)
          ? "active"
          : activity === "done"
          ? "done"
          : "ended",
      },
    ];
  }),
);

async function openAgent(agentId: string) {
  focusAgentId.value = "";
  workbench?.openBuiltin("session");
  await nextTick();
  focusAgentId.value = agentId;
}
</script>

<style scoped>
.subagent-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 6px 0 2px;
}

.subagent-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  max-width: 100%;
  padding: 3px 10px 3px 8px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 999px;
  color: rgba(var(--v-theme-on-surface), 0.72);
  font: inherit;
  font-size: 12px;
  line-height: 1.4;
}

.subagent-chip:hover {
  background: rgba(var(--v-theme-on-surface), 0.05);
}

.subagent-chip-name {
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface));
}

.subagent-chip-activity {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.subagent-chip--active {
  border-color: rgba(var(--v-theme-primary), 0.45);
}

.subagent-chip {
  --agent-color: var(--agent-light);
}

.v-theme--dark .subagent-chip {
  --agent-color: var(--agent-dark);
}

/* Same period and phase as the star, so both breathe in the agent's color. */
.subagent-chip--active .subagent-chip-activity {
  animation: subagent-chip-breathe 2s ease-in-out infinite;
}

@keyframes subagent-chip-breathe {
  0%,
  100% {
    color: rgba(var(--v-theme-on-surface), 0.55);
  }
  50% {
    color: var(--agent-color);
  }
}

@media (prefers-reduced-motion: reduce) {
  .subagent-chip--active .subagent-chip-activity {
    animation: none;
    color: var(--agent-color);
  }
}
</style>
