<template>
  <div class="session-panel">
        <section class="so-section">
          <div class="so-heading">{{ tm("sessionPanel.session.title") }}</div>
          <div class="so-row">
            <span class="so-label">{{ tm("sessionPanel.session.model") }}</span>
            <span class="so-value">{{ model || "-" }}</span>
          </div>
          <div v-if="!sessionId" class="so-note">
            {{ tm("sessionPanel.session.newChat") }}
          </div>
        </section>

        <section class="so-section">
          <div class="so-heading">
            {{ tm("sessionPanel.context.title") }}
            <v-icon
              size="14"
              class="so-info"
              :title="
                used
                  ? tm('sessionPanel.context.note')
                  : tm('sessionPanel.context.noData')
              "
              >mdi-information-outline</v-icon
            >
          </div>
          <div class="so-row so-total">
            <span :class="{ 'so-error': nearCompaction }">
              {{
                limit
                  ? tm("sessionPanel.context.used", { percent: percent(used) })
                  : tm("sessionPanel.context.usedNoLimit")
              }}
            </span>
            <span class="so-muted">
              {{ used.toLocaleString() }} /
              {{ limit ? limit.toLocaleString() : "?" }}
            </span>
          </div>
          <div class="so-bar">
            <span
              v-for="row in rows.filter((row) => row.key !== 'free')"
              :key="row.key"
              :style="{ width: share(row.tokens), background: row.color }"
            />
            <i
              v-if="limit"
              class="so-threshold"
              :style="{ left: share(triggerTokens) }"
              :title="tm('sessionPanel.context.threshold')"
            />
          </div>
          <div class="so-row">
            <span class="so-label">{{
              tm("sessionPanel.context.threshold")
            }}</span>
            <StyledMenu v-if="sessionId && limit" location="bottom end">
              <template #activator="{ props: menuProps }">
                <button
                  type="button"
                  class="so-value so-trigger"
                  v-bind="menuProps"
                >
                  <span class="so-trigger-text">{{
                    thresholdTitle(threshold)
                  }}</span>
                  <v-icon size="14">mdi-chevron-down</v-icon>
                </button>
              </template>
              <v-list-item
                v-for="option in thresholdOptions"
                :key="option.value"
                class="styled-menu-item"
                :active="option.value === threshold"
                :disabled="option.immediate"
                @click="setThreshold(option.value)"
              >
                <v-list-item-title>
                  {{ thresholdTitle(option.value) }}
                  <span v-if="option.immediate" class="so-muted">
                    {{ tm("sessionPanel.context.immediate") }}
                  </span>
                </v-list-item-title>
              </v-list-item>
            </StyledMenu>
            <span v-else class="so-value">{{ thresholdTitle(threshold) }}</span>
          </div>
          <div class="so-legend">
            <div
              v-for="row in rows"
              :key="row.key"
              class="so-legend-item"
              :title="`${row.label}: ${row.tokens.toLocaleString()} (${percent(
                row.tokens,
              )})`"
            >
              <i class="so-dot" :style="{ background: row.color }" />
              <span class="so-legend-label">{{ row.label }}</span>
              <span class="so-legend-value">
                {{ formatTokenCount(row.tokens) }}
                <span class="so-muted">{{ percent(row.tokens) }}</span>
              </span>
            </div>
          </div>
          <div v-if="sessionId" class="so-row so-compact">
            <span class="so-muted">
              {{
                triggerTokens > used
                  ? tm("sessionPanel.context.untilCompact", {
                      tokens: formatTokenCount(triggerTokens - used),
                    })
                  : ""
              }}
            </span>
            <v-btn
              size="small"
              variant="tonal"
              :loading="compacting"
              :disabled="running"
              @click="compactNow"
            >
              {{ tm("sessionPanel.context.compactNow") }}
            </v-btn>
          </div>
          <div
            v-if="compactMessage"
            class="so-note"
            :class="{ 'so-error': compactFailed }"
          >
            {{ compactMessage }}
          </div>
          <div v-if="nearCompaction" class="so-note so-error">
            {{ tm("sessionPanel.context.nearCompaction") }}
          </div>
          <div v-if="stats.usage.input" class="so-note">
            {{
              tm("sessionPanel.context.totalUsage", {
                input: formatTokenCount(stats.usage.input),
                hit: Math.round((stats.usage.cached / stats.usage.input) * 100),
                output: formatTokenCount(stats.usage.output),
              })
            }}
          </div>
          <div v-if="stats.compactions" class="so-note">
            {{
              tm("sessionPanel.context.compactions", {
                count: stats.compactions,
              })
            }}
          </div>
          <div v-if="!used" class="so-note">
            {{ tm("sessionPanel.context.noData") }}
          </div>
        </section>

        <section v-if="fileChanges.length" class="so-section">
          <button
            type="button"
            class="so-row so-heading so-toggle"
            :aria-expanded="showFiles"
            @click="showFiles = !showFiles"
          >
            <span>
              {{ tm("sessionPanel.changes.title") }}
              <span class="so-muted">{{ fileChanges.length }}</span>
            </span>
            <span class="so-numbers">
              <span class="so-added">+{{ changeTotals.added }}</span>
              <span class="so-removed">-{{ changeTotals.removed }}</span>
            </span>
            <v-icon
              size="16"
              class="so-chevron"
              :class="{ 'so-chevron--open': showFiles }"
              >mdi-chevron-down</v-icon
            >
          </button>
          <template v-if="showFiles">
            <div v-for="change in fileChanges" :key="change.path" class="so-row">
              <span class="so-label so-path" :title="change.path">
                {{ change.path }}
              </span>
              <span class="so-numbers">
                <span class="so-added">+{{ change.added }}</span>
                <span class="so-removed">-{{ change.removed }}</span>
              </span>
            </div>
          </template>
        </section>

  </div>
</template>

<script setup lang="ts">
// The workbench's session view: this conversation's model, context and
// changed files.
import { computed, ref, watch } from "vue";
import { chatApi } from "@/api/v1";
import StyledMenu from "@/components/shared/StyledMenu.vue";
import type { ChatRecord } from "@/composables/useMessages";
import { useModuleI18n } from "@/i18n/composables";
import { formatTokenCount } from "@/utils/providerMetadata";
import {
  readChatSessionPrefs,
  writeChatSessionPref,
} from "@/utils/chatSessionPrefs.mjs";

const props = defineProps<{
  messages: ChatRecord[];
  // Provider-reported context of the latest request, and the model window.
  used: number;
  limit: number;
  model?: string;
  sessionId?: string | null;
  running?: boolean;
}>();

const { tm } = useModuleI18n("features/chat");

// Summed provider usage and compactions of every reply, and the latest
// context breakdown (each reply's agent stats carry them).
const stats = computed(() => {
  const count = (value: unknown) => Math.max(0, Number(value) || 0);
  const usage = { input: 0, cached: 0, output: 0 };
  let compactions = 0;
  let breakdown: Record<string, number> | null = null;
  for (let index = props.messages.length - 1; index >= 0; index -= 1) {
    const agentStats = props.messages[index].content?.agentStats;
    const tokens = agentStats?.token_usage;
    if (tokens) {
      usage.input += count(tokens.input_other) + count(tokens.input_cached);
      usage.cached += count(tokens.input_cached);
      usage.output += count(tokens.output);
    }
    compactions += count(agentStats?.compactions);
    breakdown ||= agentStats?.context_breakdown || null;
  }
  return { usage, compactions, breakdown };
});

// Files the agent changed in this conversation, per path: the file tools'
// change previews (`file_change`), minus undone ones (undo marks the call
// or records its ID in the browser). Hidden when no call carries a preview.
const showFiles = ref(false);
const fileChanges = computed(() => {
  let undone: unknown[] = [];
  try {
    const stored = JSON.parse(localStorage.getItem("chat.undoneFileChanges") || "[]");
    if (Array.isArray(stored)) undone = stored;
  } catch {
    // The undo record is only a display hint.
  }
  const byPath = new Map<string, { path: string; added: number; removed: number }>();
  for (const message of props.messages) {
    for (const part of message.content?.message || []) {
      for (const call of part.type === "tool_call" ? part.tool_calls || [] : []) {
        const change = call.file_change as
          | { path?: string; change_id?: string; undone?: boolean; added_count?: number; removed_count?: number }
          | undefined;
        const path = change?.path;
        if (!path || change.undone || undone.includes(change.change_id)) continue;
        const row = byPath.get(path) || { path, added: 0, removed: 0 };
        row.added += Number(change.added_count) || 0;
        row.removed += Number(change.removed_count) || 0;
        byPath.set(path, row);
      }
    }
  }
  return [...byPath.values()];
});
const changeTotals = computed(() =>
  fileChanges.value.reduce(
    (sum, change) => ({
      added: sum.added + change.added,
      removed: sum.removed + change.removed,
    }),
    { added: 0, removed: 0 },
  ),
);

const PARTS = ["system", "tools", "messages", "tool_results", "reasoning"];
const COLORS: Record<string, string> = {
  system: "rgb(var(--v-theme-warning))",
  tools: "rgb(var(--v-theme-success))",
  messages: "rgb(var(--v-theme-primary))",
  tool_results: "rgb(var(--v-theme-info))",
  // A fixed violet: the theme secondary is too close to primary to tell apart.
  reasoning: "#9c6ade",
  free: "rgba(var(--v-theme-on-surface), 0.14)",
};

// The breakdown is a character-based estimate; scale it to the reported
// usage, handing rounding remainders to the largest fractions so the rows
// add up to exactly what was used.
const rows = computed(() => {
  const breakdown = stats.value.breakdown;
  const total = PARTS.reduce((sum, key) => sum + (breakdown?.[key] || 0), 0);
  const exact =
    breakdown && props.used && total > 0
      ? PARTS.filter((key) => breakdown[key] > 0).map((key) => ({
          key,
          value: (props.used * breakdown[key]) / total,
        }))
      : [];
  const result = exact.map(({ key, value }) => ({ key, tokens: Math.floor(value) }));
  let remaining = props.used - result.reduce((sum, row) => sum + row.tokens, 0);
  for (const { key } of [...exact].sort((a, b) => (b.value % 1) - (a.value % 1))) {
    if (remaining-- <= 0) break;
    result.find((row) => row.key === key)!.tokens += 1;
  }
  if (props.limit) {
    result.push({ key: "free", tokens: Math.max(0, props.limit - props.used) });
  }
  return result.map((row) => ({
    ...row,
    color: COLORS[row.key],
    label:
      row.key === "free"
        ? tm("sessionPanel.context.free")
        : row.key === "tools" && breakdown?.tool_count
          ? tm("sessionPanel.context.toolsCount", { count: breakdown.tool_count })
          : tm(`sessionPanel.context.parts.${row.key}`),
  }));
});

function percent(value: number) {
  if (!props.limit) return "-";
  const pct = (value / props.limit) * 100;
  return `${pct > 0 && pct < 0.1 ? "<0.1" : pct.toFixed(1)}%`;
}

function share(value: number) {
  return `${Math.min(100, (value / (props.limit || props.used || 1)) * 100)}%`;
}

// Per-conversation auto-compact threshold in tokens, sent with every request
// as `compact_threshold`; 0 is automatic, which compresses at 82% of the
// window (LLMSummaryCompressor's default ratio).
const AUTO_RATIO = 0.82;
const threshold = ref(0);
const triggerTokens = computed(() =>
  threshold.value > 0
    ? Math.min(threshold.value, props.limit || threshold.value)
    : Math.round(props.limit * AUTO_RATIO),
);
const nearCompaction = computed(
  () => triggerTokens.value > 0 && props.used > triggerTokens.value,
);
// Auto, then 50%, 40% and 30% of the window rounded to 1000 tokens; a level
// at or below the current usage would compact at once and is disabled.
const thresholdOptions = computed(() =>
  [0, 0.5, 0.4, 0.3]
    .map((ratio) => (ratio ? Math.round((props.limit * ratio) / 1000) * 1000 : 0))
    .filter((value, index, values) => values.indexOf(value) === index && value <= props.limit)
    .map((value) => ({ value, immediate: value > 0 && value <= props.used })),
);

function thresholdTitle(value: number) {
  return value > 0
    ? formatTokenCount(value)
    : tm("sessionPanel.context.auto", {
        tokens: formatTokenCount(Math.round(props.limit * AUTO_RATIO)),
      });
}

function setThreshold(value: number) {
  threshold.value = value;
  writeChatSessionPref(props.sessionId || "", "compact_threshold", value || null);
}

const compacting = ref(false);
const compactMessage = ref("");
const compactFailed = ref(false);

// Requests of a previous conversation must not update this one.
let sessionGeneration = 0;

async function request<T>(
  call: () => Promise<{ data: { status: string; message?: string | null; data: T } }>,
): Promise<T | undefined> {
  const generation = sessionGeneration;
  const response = await call();
  if (generation !== sessionGeneration) return undefined;
  if (response.data.status !== "ok") {
    throw new Error(response.data.message ?? undefined);
  }
  return response.data.data;
}

async function compactNow() {
  if (!props.sessionId || compacting.value) return;
  const generation = sessionGeneration;
  compacting.value = true;
  compactMessage.value = "";
  compactFailed.value = false;
  try {
    const result = await request<{ before: number; after: number }>(() =>
      chatApi.compactSession(props.sessionId as string),
    );
    if (result) {
      compactMessage.value = tm("sessionPanel.context.compacted", {
        before: formatTokenCount(result.before),
        after: formatTokenCount(result.after),
      });
    }
  } catch (error) {
    if (generation !== sessionGeneration) return;
    compactFailed.value = true;
    compactMessage.value = tm("sessionPanel.context.compactFailed", {
      error: error instanceof Error ? error.message : String(error),
    });
  } finally {
    if (generation === sessionGeneration) compacting.value = false;
  }
}

watch(
  () => props.sessionId,
  async (sessionId) => {
    sessionGeneration += 1;
    compacting.value = false;
    compactFailed.value = false;
    compactMessage.value = "";
    threshold.value =
      Number(readChatSessionPrefs(sessionId || "").compact_threshold) || 0;
  },
  { immediate: true },
);
</script>

<style>
/* Shared by the panel's sections. */
.session-panel .so-section {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 9px 0;
  border-bottom: 1px solid
    var(--chat-border, rgba(var(--v-theme-on-surface), 0.1));
}

.session-panel .so-section:first-child {
  padding-top: 4px;
}

.session-panel .so-section:last-child {
  border-bottom: 0;
}

.session-panel .so-heading {
  font-size: 13px;
  font-weight: 600;
}

.session-panel .so-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
}

.session-panel .so-label {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
  color: rgba(var(--v-theme-on-surface), 0.78);
}

.session-panel .so-value {
  min-width: 0;
  overflow: hidden;
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-panel .so-muted,
.session-panel .so-note {
  color: rgba(var(--v-theme-on-surface), 0.58);
  font-weight: 400;
}

.session-panel .so-note {
  font-size: 12px;
  line-height: 1.5;
}

.session-panel .so-error {
  color: rgb(var(--v-theme-error));
}

.session-panel .so-more {
  align-self: flex-start;
  color: rgb(var(--v-theme-primary));
  font: inherit;
  font-size: 12px;
}
</style>

<style scoped>
.session-panel {
  height: 100%;
  color: rgb(var(--v-theme-on-surface));
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow-y: auto;
  padding: 2px 16px 12px;
  font-size: 13px;
  line-height: 1.62;
}

.so-trigger {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  max-width: 70%;
  min-width: 0;
  padding: 1px 4px;
  border-radius: 6px;
  color: inherit;
  font: inherit;
}

.so-trigger:hover {
  background: rgba(var(--v-theme-on-surface), 0.06);
}

.so-trigger-text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.so-info {
  margin-left: 2px;
  opacity: 0.5;
  cursor: help;
}

.so-total {
  font-size: 14px;
  font-weight: 600;
}

.so-bar {
  position: relative;
  display: flex;
  height: 6px;
  overflow: hidden;
  border-radius: 3px;
  background: rgba(var(--v-theme-on-surface), 0.1);
}

.so-bar span {
  height: 100%;
}

.so-threshold {
  position: absolute;
  top: -2px;
  bottom: -2px;
  width: 2px;
  margin-left: -1px;
  border-radius: 1px;
  background: rgb(var(--v-theme-on-surface));
  opacity: 0.55;
}

.so-legend {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px 16px;
}

.so-legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  font-size: 12px;
}

.so-legend-label {
  min-width: 0;
  overflow: hidden;
  color: rgba(var(--v-theme-on-surface), 0.78);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.so-legend-value {
  margin-left: auto;
  font-variant-numeric: tabular-nums;
}

.so-dot {
  width: 10px;
  height: 10px;
  flex-shrink: 0;
  border-radius: 2px;
}

.so-toggle {
  width: 100%;
  color: inherit;
  font: inherit;
  text-align: left;
}

.so-chevron {
  flex-shrink: 0;
  opacity: 0.5;
  transition: transform 0.15s;
}

.so-chevron--open {
  transform: rotate(180deg);
}

.so-numbers {
  display: grid;
  grid-template-columns: minmax(48px, auto) minmax(48px, auto);
  column-gap: 8px;
  flex-shrink: 0;
  text-align: right;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.so-path {
  display: block;
  flex-shrink: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  direction: rtl;
  text-align: left;
}

.so-added {
  color: rgb(var(--v-theme-success));
}

.so-removed {
  color: rgb(var(--v-theme-error));
}

.so-compact {
  min-height: 30px;
}

</style>
