<template>
  <section class="so-section">
    <div class="so-row so-heading">
      <span>{{ tm("sessionPanel.subagents.title") }}</span>
      <span v-if="agents.length" class="so-muted">
        {{ agents.length }}
        <template v-if="usageSum">· {{ formatTokenCount(usageSum) }}</template>
      </span>
    </div>
    <div v-if="error" class="so-note so-error">{{ error }}</div>
    <div v-if="cancelError" class="so-note so-error" role="alert">{{ cancelError }}</div>
    <div v-else-if="!agents.length" class="so-note">
      {{
        enabled
          ? tm("sessionPanel.subagents.empty")
          : tm("sessionPanel.subagents.disabled")
      }}
    </div>
    <div
      v-for="agent in shownAgents"
      :key="agent.agent_id"
      :ref="(el) => setItemRef(agent.agent_id, el)"
      class="subagent-item"
      :class="{
        'subagent-item--open': expanded === agent.agent_id,
        'subagent-item--focus': focusAgentId === agent.agent_id,
      }"
    >
      <div class="subagent-line">
        <button
          type="button"
          class="so-row subagent-row"
          :aria-expanded="expanded === agent.agent_id"
          @click="toggle(agent.agent_id)"
        >
          <span class="so-label subagent-name">
            <SubagentStar
              :agent-id="agent.agent_id"
              :active="agent.state === 'running'"
              :muted="!isSubagentActive(agent) && agent.state !== 'completed'"
            />
            <span class="subagent-name-text" :title="agent.name">{{
              displayName(agent)
            }}</span>
          </span>
          <span
            class="subagent-summary"
            :class="{ 'subagent-summary--active': agent.state === 'running' }"
            :style="{
              '--agent-light': subagentColor(agent.agent_id).light,
              '--agent-dark': subagentColor(agent.agent_id).dark,
            }"
            >{{ summary(agent) }}</span
          >
          <span v-if="elapsed(agent) !== null" class="subagent-elapsed">{{
            formatElapsed(elapsed(agent) || 0)
          }}</span>
          <v-icon size="16" class="subagent-chevron">mdi-chevron-down</v-icon>
        </button>
        <v-btn
          v-if="isSubagentActive(agent)"
          class="subagent-stop"
          icon
          size="x-small"
          variant="text"
          color="error"
          :loading="cancelling === agent.agent_id"
          :title="tm('sessionPanel.subagents.cancel')"
          :aria-label="tm('sessionPanel.subagents.cancel')"
          @click="cancel(agent)"
        >
          <v-icon size="16">mdi-stop</v-icon>
        </v-btn>
      </div>
      <div v-if="expanded === agent.agent_id" class="subagent-detail">
        <div class="so-muted">
          {{ agent.name }} ·
          {{ tm(`sessionPanel.subagents.states.${agent.state}`) }} ·
          {{
            tm("sessionPanel.subagents.steps", { count: agent.completed_steps })
          }}
        </div>
        <div class="so-muted">
          {{
            [
              agent.provider_id && agent.model
                ? `${agent.provider_id} / ${agent.model}`
                : agent.provider_id,
              agent.persona_id
                ? tm("sessionPanel.subagents.persona", {
                    name: agent.persona_id,
                  })
                : "",
              agent.context_tokens
                ? tm("sessionPanel.subagents.context", {
                    tokens: formatTokenCount(agent.context_tokens),
                  })
                : "",
            ]
              .filter(Boolean)
              .join(" · ")
          }}
        </div>
        <div v-if="agent.total_usage" class="so-muted">
          {{ usageText(agent.total_usage) }}
        </div>
        <div v-else-if="agent.state !== 'pending'" class="so-muted">
          {{ tm("sessionPanel.subagents.usageUnknown") }}
        </div>
        <div v-if="agent.task" class="subagent-clip">
          {{ tm("sessionPanel.subagents.task") }}{{ agent.task }}
        </div>
        <div v-if="agent.error" class="subagent-clip so-error">
          {{ agent.error }}
        </div>
        <div v-else-if="agent.result" class="subagent-clip">
          {{ tm("sessionPanel.subagents.result") }}{{ agent.result }}
        </div>
        <div v-if="agent.tools?.length" class="subagent-clip">
          {{ tm("sessionPanel.subagents.tools") }}{{ agent.tools.join(", ") }}
        </div>
        <div class="so-note">{{ tm("sessionPanel.subagents.note") }}</div>
      </div>
    </div>
    <button
      v-if="agents.length > AGENT_LIMIT"
      type="button"
      class="so-more"
      @click="showAll = !showAll"
    >
      {{
        showAll
          ? tm("sessionPanel.subagents.less")
          : tm("sessionPanel.subagents.more", {
              count: agents.length - AGENT_LIMIT,
            })
      }}
    </button>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { chatApi } from "@/api/v1";
import SubagentStar from "@/components/chat/SubagentStar.vue";
import {
  formatElapsed,
  isSubagentActive,
  subagentActivity,
  subagentColor,
  subagentElapsed,
  subagentModelName,
  subagentTaskName,
  useSessionSubagents,
  type Subagent,
  type SubagentUsage,
} from "@/composables/useSessionSubagents";
import { useModuleI18n } from "@/i18n/composables";
import { askForConfirmation, useConfirmDialog } from "@/utils/confirmDialog";
import { formatTokenCount } from "@/utils/providerMetadata";

const props = defineProps<{
  sessionId?: string | null;
  running?: boolean;
}>();

const { tm } = useModuleI18n("features/chat");
const confirmDialog = useConfirmDialog();
const { agents, enabled, error, now, focusAgentId, reload } =
  useSessionSubagents();
const cancelling = ref("");
const cancelError = ref("");
watch(() => props.sessionId, () => { cancelError.value = ""; });

// One line per agent, active ones first; details open one at a time.
const AGENT_LIMIT = 4;
const expanded = ref("");
const showAll = ref(false);
const itemRefs = new Map<string, Element>();
const sortedAgents = computed(() => [
  ...agents.value.filter(isSubagentActive),
  ...agents.value.filter((agent) => !isSubagentActive(agent)),
]);
const shownAgents = computed(() =>
  showAll.value ? sortedAgents.value : sortedAgents.value.slice(0, AGENT_LIMIT),
);
const usageSum = computed(() =>
  agents.value.reduce(
    (sum, agent) =>
      sum +
      (agent.total_usage
        ? agent.total_usage.input_tokens + agent.total_usage.output_tokens
        : 0),
    0,
  ),
);

function setItemRef(agentId: string, el: unknown) {
  if (el instanceof Element) itemRefs.set(agentId, el);
  else itemRefs.delete(agentId);
}

function toggle(agentId: string) {
  expanded.value = expanded.value === agentId ? "" : agentId;
}

function elapsed(agent: Subagent) {
  return subagentElapsed(agent, now.value);
}

/** Model, thinking level and short task, e.g. "haiku-5-5 · 低 · 秋日观察". */
function displayName(agent: Subagent) {
  return [
    subagentModelName(agent),
    agent.thinking
      ? tm(`sessionPanel.subagents.thinkingLevels.${agent.thinking}`)
      : "",
    subagentTaskName(agent),
  ]
    .filter(Boolean)
    .join(" · ");
}

function summary(agent: Subagent) {
  const activity = tm(
    `sessionPanel.subagents.activity.${subagentActivity(agent)}`,
  );
  if (isSubagentActive(agent)) return activity;
  const usage = agent.total_usage
    ? agent.total_usage.input_tokens + agent.total_usage.output_tokens
    : 0;
  return usage ? `${formatTokenCount(usage)} · ${activity}` : activity;
}

function usageText(usage: SubagentUsage) {
  const text = tm("sessionPanel.subagents.usage", {
    input: formatTokenCount(usage.input_tokens),
    cached: formatTokenCount(usage.cached_input_tokens),
    output: formatTokenCount(usage.output_tokens),
  });
  return usage.complete
    ? text
    : `${text} · ${tm("sessionPanel.subagents.usagePartial")}`;
}

async function cancel(agent: Subagent) {
  const sessionId = props.sessionId;
  if (!sessionId || cancelling.value) return;
  const confirmed = await askForConfirmation(
    tm("sessionPanel.subagents.cancelConfirm", { name: displayName(agent) }),
    confirmDialog,
  );
  if (!confirmed || props.sessionId !== sessionId) return;
  cancelError.value = "";
  cancelling.value = agent.agent_id;
  try {
    const response = await chatApi.cancelSubagent(
      sessionId,
      agent.agent_id,
    );
    if (response.data.status !== "ok") {
      throw new Error(response.data.message ?? undefined);
    }
  } catch (err) {
    if (props.sessionId === sessionId) {
      cancelError.value = err instanceof Error ? err.message : String(err);
    }
  } finally {
    cancelling.value = "";
    await reload();
  }
}

// A chip under a reply asks to show its agent: expand and scroll to it.
watch(
  focusAgentId,
  async (agentId, _previous, onCleanup) => {
    if (!agentId) return;
    let active = true;
    const timeout = setTimeout(() => {
      if (focusAgentId.value === agentId) focusAgentId.value = "";
    }, 2000);
    onCleanup(() => { active = false; clearTimeout(timeout); });
    const index = sortedAgents.value.findIndex(
      (agent) => agent.agent_id === agentId,
    );
    if (index >= AGENT_LIMIT) showAll.value = true;
    expanded.value = agentId;
    await nextTick();
    if (active) itemRefs.get(agentId)?.scrollIntoView({ block: "nearest" });
  },
  { immediate: true },
);
</script>

<style scoped>
.subagent-item {
  border-radius: 6px;
}

.subagent-item--open {
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.subagent-item--focus {
  box-shadow: inset 0 0 0 1px rgba(var(--v-theme-primary), 0.6);
}

.subagent-line {
  display: flex;
  align-items: center;
  gap: 2px;
}

.subagent-row {
  flex: 1 1 auto;
  width: 100%;
  min-width: 0;
  min-height: 26px;
  padding: 2px 4px;
  border-radius: 6px;
  color: inherit;
  font: inherit;
  text-align: left;
}

.subagent-row:hover {
  background: rgba(var(--v-theme-on-surface), 0.06);
}

.subagent-summary--active {
  --agent-color: var(--agent-light);
  animation: subagent-summary-breathe 2s ease-in-out infinite;
}

.v-theme--dark .subagent-summary--active {
  --agent-color: var(--agent-dark);
}

/* Breathes with the row's star in the agent's color. */
@keyframes subagent-summary-breathe {
  0%,
  100% {
    color: rgba(var(--v-theme-on-surface), 0.6);
  }
  50% {
    color: var(--agent-color);
  }
}

@media (prefers-reduced-motion: reduce) {
  .subagent-summary.subagent-summary--active {
    animation: none;
    color: var(--agent-color);
  }
}

.subagent-summary {
  flex: 0 1 auto;
  min-width: 0;
  max-width: 45%;
  margin-left: auto;
  overflow: hidden;
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.subagent-elapsed {
  flex-shrink: 0;
  margin-left: 6px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.subagent-stop {
  flex-shrink: 0;
}

.subagent-chevron {
  margin-left: 2px;
  flex-shrink: 0;
  opacity: 0.5;
  transition: transform 0.15s;
}

.subagent-item--open .subagent-chevron {
  transform: rotate(180deg);
}

.subagent-detail {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0 8px 8px 22px;
}

.subagent-detail .so-muted {
  overflow: hidden;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.subagent-detail .subagent-clip {
  -webkit-line-clamp: 1;
}

.subagent-row .so-label.subagent-name {
  flex: 1 1 auto;
  min-width: 0;
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface));
}

.subagent-name-text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.subagent-clip {
  color: rgba(var(--v-theme-on-surface), 0.72);
  font-size: 12px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}
</style>
