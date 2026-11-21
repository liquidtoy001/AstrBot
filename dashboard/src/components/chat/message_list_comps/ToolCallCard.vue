<template>
  <div class="tool-call-card" :class="{ expanded: isExpanded }">
    <button class="tool-call-header" type="button" @click="toggleExpanded">
      <component
        :is="toolCallIcon"
        :size="16"
        class="tool-call-icon"
        aria-hidden="true"
      />
      <span class="tool-call-title">
        <template v-if="toolSummary">
          {{ toolSummary.verb }}
          <code v-if="toolSummary.target" class="tool-call-target">{{
            toolSummary.target
          }}</code>
        </template>
        <template v-else>
          {{ tm("actions.toolCallUsed", { name: displayToolName }) }}
        </template>
        <span v-if="fileChange" class="file-change-stat">
          <span class="stat-added">+{{ fileChange.added_count ?? 0 }}</span>
          <span class="stat-removed">-{{ fileChange.removed_count ?? 0 }}</span>
        </span>
      </span>
      <span class="tool-call-duration">{{ toolCallDuration }}</span>
      <!-- An interrupted call has no duration; it shows this instead. -->
      <span v-if="interrupted" class="tool-call-interrupted">
        <TriangleAlert :size="14" aria-hidden="true" />
        {{ tm("toolStatus.interrupted") }}
      </span>
      <span v-else-if="awaitingApproval" class="tool-call-interrupted awaiting">
        <v-icon size="14">mdi-hand-back-right-outline</v-icon>
        {{ tm("toolStatus.awaitingApproval") }}
      </span>
      <ChevronRight
        :size="22"
        class="tool-call-expand-icon"
        :class="{ expanded: isExpanded }"
        aria-hidden="true"
      />
    </button>

    <div v-if="isExpanded" class="tool-call-details">
      <div v-if="toolCall.id" class="tool-call-detail-row">
        <span class="detail-label">ID:</span>
        <code class="detail-value">
          {{ toolCall.id }}
        </code>
      </div>

      <div v-if="fileChange" class="tool-call-detail-row">
        <span class="detail-label">{{ tm("fileChange.changes") }}</span>
        <code class="detail-value">{{ fileChange.path }}</code>
        <pre
          v-if="fileChange.removed || fileChange.added"
          class="detail-value detail-json file-change-diff"
        ><span class="diff-meta">@@ {{ tm("fileChange.line", { line: fileChange.start_line }) }}</span>
<span
  v-for="(line, i) in fileChange.removed"
  :key="'r' + i"
  class="diff-removed"
>- {{ line }}
</span><span
  v-for="(line, i) in fileChange.added"
  :key="'a' + i"
  class="diff-added"
>+ {{ line }}
</span><span v-if="fileChange.truncated" class="diff-meta">{{ tm("fileChange.truncated") }}</span></pre>
        <span v-else class="file-change-note">{{
          tm(`fileChange.reasons.${fileChange.reason || "none"}`)
        }}</span>
        <div v-if="fileChange.undoable" class="file-change-actions">
          <v-btn
            v-if="!undoState.done"
            size="small"
            variant="tonal"
            :loading="undoState.busy"
            @click="undoFileChange"
          >
            {{
              fileChange.created
                ? tm("fileChange.undoCreate")
                : tm("fileChange.undo")
            }}
          </v-btn>
          <span v-if="undoState.message" class="file-change-note">{{
            undoState.message
          }}</span>
        </div>
      </div>

      <div class="tool-call-detail-row">
        <span class="detail-label">Args:</span>
        <pre class="detail-value detail-json">{{
          JSON.stringify(toolCall.args, null, 2)
        }}</pre>
      </div>

      <div v-if="toolCall.result" class="tool-call-detail-row">
        <span class="detail-label">Result:</span>
        <pre class="detail-value detail-json detail-result">{{
          formattedResult
        }}</pre>
      </div>
      <div v-if="interrupted" class="tool-call-interrupted-detail">
        {{ tm("toolStatus.interruptedDetail") }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onUnmounted, ref, watch } from "vue";
import {
  ChevronRight,
  CodeXml,
  Globe,
  Terminal,
  TriangleAlert,
  Wrench,
} from "@lucide/vue";
import { useModuleI18n } from "@/i18n/composables";
import { chatApi } from "@/api/v1";
import { askForConfirmation, useConfirmDialog } from "@/utils/confirmDialog";
import { TOOL_KINDS } from "@/utils/toolKinds";

const props = defineProps({
  toolCall: {
    type: Object,
    required: true,
  },
  isDark: {
    type: Boolean,
    default: false,
  },
  initialExpanded: {
    type: Boolean,
    default: false,
  },
});

const { tm } = useModuleI18n("features/chat");
const confirmDialog = useConfirmDialog();

// File write/edit preview and single-file undo (see backend file_undo.py).
const UNDONE_STORAGE_KEY = "chat.undoneFileChanges";
const fileChange = computed(() => props.toolCall.file_change || null);

function readUndoneIds() {
  try {
    const ids = JSON.parse(localStorage.getItem(UNDONE_STORAGE_KEY) || "[]");
    return Array.isArray(ids) ? ids : [];
  } catch {
    return [];
  }
}

// Undo state per change, so a card reused for another change starts fresh
// and a pending confirmation or request never updates the wrong change.
const undoStates = ref({});
const confirmingIds = new Set();
function undoStateOf(id) {
  return (
    undoStates.value[id] || {
      busy: false,
      done: readUndoneIds().includes(id),
      message: "",
    }
  );
}
function setUndoState(id, patch) {
  undoStates.value = {
    ...undoStates.value,
    [id]: { ...undoStateOf(id), ...patch },
  };
}
const undoState = computed(() => undoStateOf(fileChange.value?.change_id));

async function undoFileChange() {
  const change = fileChange.value;
  const id = change?.change_id;
  if (!id || undoStateOf(id).busy || confirmingIds.has(id)) return;
  const question = change.created
    ? tm("fileChange.confirmCreate")
    : tm("fileChange.confirm");
  confirmingIds.add(id);
  try {
    if (!(await askForConfirmation(question, confirmDialog))) return;
    // The card may show another change by now: never undo the old one.
    if (fileChange.value?.change_id !== id) return;
    setUndoState(id, { busy: true });
    await chatApi.undoFileChange(id);
    change.undone = true;
    setUndoState(id, { done: true, message: tm("fileChange.done") });
    try {
      const ids = [...readUndoneIds(), id].slice(-300);
      localStorage.setItem(UNDONE_STORAGE_KEY, JSON.stringify(ids));
    } catch {
      // Persistence is only a display hint; the backend refuses repeats.
    }
  } catch (error) {
    // The backend answers 409 with the reason when it refuses the undo.
    setUndoState(id, {
      message: error?.response?.data?.message || error?.message || String(error),
    });
  } finally {
    confirmingIds.delete(id);
    if (undoStateOf(id).busy) setUndoState(id, { busy: false });
  }
}
const isExpanded = ref(props.initialExpanded);
const currentTime = ref(Date.now() / 1000);
let timer = null;

// The turn ended before this call returned (see useMessages / chat_service).
const interrupted = computed(
  () => !props.toolCall.finished_ts && props.toolCall.phase === "unknown",
);
// An approval card for this call is open (see useMessages).
const awaitingApproval = computed(
  () =>
    !props.toolCall.finished_ts && props.toolCall.phase === "awaiting_approval",
);

const elapsedTime = computed(() => {
  if (props.toolCall.finished_ts || interrupted.value || awaitingApproval.value)
    return "";
  const startTime = Number(props.toolCall.ts);
  if (!Number.isFinite(startTime) || startTime <= 0) return "";
  return formatDuration(currentTime.value - startTime);
});

const displayToolName = computed(() => props.toolCall.name || "tool");

// Command-style title for well-known tools: what ran or which file changed.
const toolSummary = computed(() => {
  const entry = TOOL_KINDS[String(props.toolCall.name || "")];
  if (!entry) return null;
  const verb = tm(`toolSummary.${entry.verb}`);
  if (!entry.target) return { verb, target: "" };
  let args = props.toolCall.args ?? props.toolCall.arguments ?? {};
  if (typeof args === "string") {
    try {
      args = JSON.parse(args);
    } catch {
      args = {};
    }
  }
  const value = args?.[entry.target];
  const target = String(value || "")
    .split(/\r?\n/)
    .find((line) => line.trim())
    ?.trim();
  if (!target) return null;
  return {
    verb,
    target: target.length > 80 ? `${target.slice(0, 77)}…` : target,
  };
});

const toolCallIcon = computed(() => {
  const name = String(props.toolCall.name || "");
  if (name === "astrbot_execute_ipython" || name === "astrbot_execute_python") {
    return CodeXml;
  }
  if (name.includes("web_search") || name.includes("tavily")) {
    return Globe;
  }
  if (name === "astrbot_execute_shell") {
    return Terminal;
  }
  return Wrench;
});

const toolCallDuration = computed(() => {
  const startTime = Number(props.toolCall.ts);
  if (!Number.isFinite(startTime) || startTime <= 0) return "";
  if (props.toolCall.finished_ts) {
    return formatDuration(Number(props.toolCall.finished_ts) - startTime);
  }
  return elapsedTime.value;
});

const formattedResult = computed(() => {
  if (!props.toolCall.result) return "";
  try {
    const parsed = JSON.parse(props.toolCall.result);
    return JSON.stringify(parsed, null, 2);
  } catch {
    return props.toolCall.result;
  }
});

const formatDuration = (seconds) => {
  if (!Number.isFinite(seconds) || seconds < 0) return "";
  if (seconds < 1) {
    return `${Math.round(seconds * 1000)}ms`;
  } else if (seconds < 60) {
    return `${seconds.toFixed(1)}s`;
  } else {
    const minutes = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return `${minutes}m ${secs}s`;
  }
};

const toggleExpanded = () => {
  isExpanded.value = !isExpanded.value;
};

const updateTime = () => {
  currentTime.value = Date.now() / 1000;
};

// Tick only while the call runs; it can wait for approval, finish or be
// interrupted after mount.
watch(
  () =>
    !props.toolCall.finished_ts &&
    !interrupted.value &&
    !awaitingApproval.value,
  (running) => {
    if (timer !== null) clearInterval(timer);
    timer = null;
    if (running) {
      updateTime();
      timer = setInterval(updateTime, 100);
    }
  },
  { immediate: true },
);

onUnmounted(() => {
  if (timer) {
    clearInterval(timer);
  }
});
</script>

<style scoped>
.tool-call-card {
  margin: 6px 0;
  max-width: 100%;
  color: rgba(var(--v-theme-on-surface), 0.7);
  font-size: inherit;
  line-height: inherit;
}

.tool-call-card.expanded {
  width: 100%;
}

.tool-call-header {
  max-width: 100%;
  border: 0;
  padding: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  user-select: none;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font: inherit;
  text-align: left;
}

.tool-call-header:hover {
  color: rgba(var(--v-theme-on-surface), 0.88);
}

.tool-call-expand-icon {
  color: inherit;
  opacity: 1;
  transition: transform 0.2s ease;
  flex-shrink: 0;
}

.tool-call-expand-icon.expanded {
  transform: rotate(90deg);
}

.tool-call-icon {
  color: currentcolor;
  flex-shrink: 0;
}

.tool-call-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-call-interrupted {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  flex-shrink: 0;
  font-size: 12px;
  color: rgb(var(--v-theme-warning));
}

.tool-call-interrupted.awaiting {
  color: rgb(var(--v-theme-info));
}

.tool-call-interrupted-detail {
  margin-bottom: 8px;
  font-size: 12px;
  color: rgb(var(--v-theme-warning));
}

.tool-call-target {
  padding: 0 4px;
  border-radius: 4px;
  background: rgba(var(--v-theme-on-surface), 0.06);
  font-family: var(--chat-code-font, ui-monospace, SFMono-Regular, Menlo, monospace);
  font-size: 0.92em;
}

.tool-call-duration {
  flex-shrink: 0;
  color: rgba(var(--v-theme-on-surface), 0.48);
}

.tool-call-details {
  margin-top: 8px;
  padding-left: 26px;
  animation: fadeIn 0.2s ease-in-out;
}

.tool-call-detail-row {
  display: flex;
  flex-direction: column;
  margin-bottom: 8px;
}

.tool-call-detail-row:last-child {
  margin-bottom: 0;
}

.detail-label {
  font-size: 11px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.55);
  text-transform: uppercase;
  margin-bottom: 4px;
}

.detail-value {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.8);
  background-color: transparent;
  padding: 0;
  border-radius: 4px;
  word-break: break-all;
}

.detail-json {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  white-space: pre-wrap;
  max-height: 200px;
  overflow-y: auto;
  margin: 0;
}

.detail-result {
  max-height: 300px;
  background-color: transparent;
}

.file-change-stat {
  flex-shrink: 0;
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.stat-added,
.diff-added {
  color: rgb(var(--v-theme-success));
}

.stat-removed,
.diff-removed {
  color: rgb(var(--v-theme-error));
}

.stat-removed {
  margin-left: 4px;
}

.file-change-diff {
  margin-top: 4px;
  max-height: 320px;
}

.diff-meta,
.file-change-note {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.55);
}

.file-change-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}

.animate-fade-in {
  animation: fadeIn 0.2s ease-in-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }

  to {
    opacity: 1;
  }
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}
</style>
