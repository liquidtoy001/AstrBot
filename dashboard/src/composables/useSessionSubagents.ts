import { computed, onUnmounted, ref, watch, type Ref } from "vue";
import { chatApi } from "@/api/v1";
import { TOOL_KINDS } from "@/utils/toolKinds";

export type SubagentState =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "timed_out"
  | "interrupted";

export type SubagentUsage = {
  input_tokens: number;
  output_tokens: number;
  cached_input_tokens: number;
  complete: boolean;
};

export type Subagent = {
  agent_id: string;
  name: string;
  state: SubagentState;
  task?: string;
  result?: string | null;
  error?: string | null;
  completed_steps: number;
  started_at?: number | null;
  finished_at?: number | null;
  provider_id?: string | null;
  config_name?: string | null;
  model?: string | null;
  thinking?: "low" | "medium" | "high" | null;
  persona_id?: string | null;
  tools?: string[] | null;
  context_tokens?: number;
  current_tool?: string | null;
  total_usage?: SubagentUsage | null;
};

// One store for the conversation's sub-agents, shared by the session panel
// and the chips under replies, so both show the same polled state.
const agents = ref<Subagent[]>([]);
const enabled = ref(true);
const error = ref("");
const now = ref(Date.now() / 1000);
const focusAgentId = ref("");
let loadGeneration = 0;
let currentSession: string | null = null;
let currentRunning = false;
let serverClockOffset = 0;
let pollTimer: ReturnType<typeof setTimeout> | null = null;
let clockTimer: ReturnType<typeof setInterval> | null = null;

export function isSubagentActive(agent: Subagent) {
  return agent.state === "running" || agent.state === "pending";
}

async function load(running: boolean) {
  const generation = ++loadGeneration;
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = null;
  const sessionId = currentSession;
  if (!sessionId) {
    agents.value = [];
    return;
  }
  try {
    const response = await chatApi.listSubagents(sessionId);
    if (generation !== loadGeneration || sessionId !== currentSession) return;
    if (response.data.status !== "ok") {
      throw new Error(response.data.message ?? undefined);
    }
    agents.value = response.data.data.agents || [];
    const serverTime = response.data.data.server_time;
    if (typeof serverTime === "number" && Number.isFinite(serverTime)) {
      serverClockOffset = serverTime - Date.now() / 1000;
      now.value = serverTime;
    }
    enabled.value = Boolean(response.data.data.enabled);
    error.value = "";
  } catch (err) {
    if (generation !== loadGeneration || sessionId !== currentSession) return;
    error.value = err instanceof Error ? err.message : String(err);
  }
  const active = agents.value.some(isSubagentActive);
  // Tick the elapsed timers only while something is running.
  if (active && !clockTimer) {
    clockTimer = setInterval(
      () => (now.value = Date.now() / 1000 + serverClockOffset),
      1000,
    );
  } else if (!active && clockTimer) {
    clearInterval(clockTimer);
    clockTimer = null;
  }
  if (running || active) {
    pollTimer = setTimeout(() => load(running), 2000);
  }
}

/**
 * Drive polling for the current conversation. Call once, from the chat page.
 */
export function useSessionSubagentsPolling(
  sessionId: Ref<string | null>,
  running: Ref<boolean>,
) {
  watch(
    () => [sessionId.value, running.value] as const,
    ([id, isRunning]) => {
      currentRunning = isRunning;
      if (id !== currentSession) {
        if (clockTimer) clearInterval(clockTimer);
        clockTimer = null;
        error.value = "";
        currentSession = id;
        serverClockOffset = 0;
        agents.value = [];
        focusAgentId.value = "";
      }
      void load(isRunning);
    },
    { immediate: true },
  );
  onUnmounted(() => {
    loadGeneration += 1;
    if (pollTimer) clearTimeout(pollTimer);
    if (clockTimer) clearInterval(clockTimer);
    pollTimer = null;
    clockTimer = null;
    currentSession = null;
    currentRunning = false;
  });
}

export function useSessionSubagents() {
  const byId = computed(
    () => new Map(agents.value.map((agent) => [agent.agent_id, agent])),
  );
  return {
    agents,
    byId,
    enabled,
    error,
    now,
    focusAgentId,
    reload: () => load(currentRunning),
  };
}

/** Seconds since the current input started, frozen once it finished. */
export function subagentElapsed(agent: Subagent, nowSeconds: number) {
  if (!agent.started_at) return null;
  const end = agent.finished_at || nowSeconds;
  return Math.max(0, Math.round(end - agent.started_at));
}

export function formatElapsed(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const rest = String(seconds % 60).padStart(2, "0");
  return minutes ? `${minutes}:${rest}` : `0:${rest}`;
}

/** Model id without the vendor prefix: claude-haiku-5-5 -> haiku-5-5. */
/**
 * Short model name, the same rule for every provider: drop the vendor path,
 * the family prefix and trailing version numbers, so
 * anthropic/claude-haiku-5-5 -> haiku and openai/gpt-6-luna -> luna.
 */
export function subagentModelName(agent: Subagent) {
  const full = String(agent.model || agent.provider_id || "").replace(
    /^.*\//,
    "",
  );
  return (
    full
      .replace(/^(claude|gpt-[\d.]+|gemini-[\d.]+)-/i, "")
      .replace(/(-\d+(\.\d+)?)+$/, "") || full
  );
}

/** Short identity for chips: the short model name, else the agent name. */
export function subagentIdentity(agent: Subagent) {
  return subagentModelName(agent) || agent.name;
}

/** A short task name from the display name or the task's first line. */
export function subagentTaskName(agent: Subagent) {
  // Session names often repeat the agent config or model name already shown
  // in the label ("haiku-worker 火星农场", "luna-火星农场").
  let name = agent.name || "";
  const model = subagentModelName(agent);
  for (const prefix of [
    agent.config_name,
    String(agent.model || "").replace(/^.*\//, ""),
    model,
  ]) {
    if (!prefix || !name.toLowerCase().startsWith(prefix.toLowerCase()))
      continue;
    const rest = name.slice(prefix.length);
    if (rest && !/^[\s:：·_-]/.test(rest)) continue;
    name = rest.replace(/^[\s:：·_-]+/, "");
    break;
  }
  const source =
    name && name !== "worker"
      ? name
      : String(agent.task || "")
          .split(/\r?\n/)
          .find((line) => line.trim()) || agent.name;
  const text = source.trim();
  return text.length > 16 ? `${text.slice(0, 15)}…` : text;
}

/** i18n key suffix for what a sub-agent is doing right now. */
export function subagentActivity(agent: Subagent) {
  if (agent.state === "pending") return "queued";
  if (agent.state === "completed") return "done";
  if (agent.state === "cancelled") return "stopped";
  if (agent.state !== "running") return "failed";
  const tool = String(agent.current_tool || "");
  if (!tool) return "thinking";
  const kind = TOOL_KINDS[tool]?.kind;
  if (kind && ["code", "command", "edit", "view"].includes(kind)) return kind;
  // Browser, computer-use and web search tools come from plugins and MCP.
  if (/browser|computer|screen/.test(tool)) return "computer";
  return /search/.test(tool) ? "search" : "tool";
}

// Sub-agent colors: none is the blue or gold of the reply avatar's star, and
// each has a darker shade for light themes and a lighter one for dark themes.
const SUBAGENT_COLORS = [
  { light: "#00845f", dark: "#2cc495" }, // green
  { light: "#6e56cf", dark: "#a996f2" }, // violet
  { light: "#a8558a", dark: "#e09ac6" }, // magenta
  { light: "#c8414b", dark: "#f27a82" }, // coral
];

/** Stable color of one sub-agent, the same in its chip and its panel row. */
export function subagentColor(agentId: string) {
  let hash = 0;
  for (const ch of agentId) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return SUBAGENT_COLORS[hash % SUBAGENT_COLORS.length];
}

/** Agent ids returned by spawn_agent calls in a reply's message parts. */
export function spawnedAgentIds(parts: unknown): string[] {
  if (!Array.isArray(parts)) return [];
  const ids: string[] = [];
  for (const part of parts) {
    if (part?.type !== "tool_call" || !Array.isArray(part.tool_calls)) continue;
    for (const call of part.tool_calls) {
      if (call?.name !== "spawn_agent" || !call.result) continue;
      try {
        const result =
          typeof call.result === "string"
            ? JSON.parse(call.result)
            : call.result;
        if (result?.agent_id) ids.push(String(result.agent_id));
      } catch {
        // Unfinished or non-JSON result: no agent yet.
      }
    }
  }
  return ids;
}

/**
 * Map each reply to delivered sub-agent results to the reply that started
 * those sub-agents, so ChatUI shows both in one bubble. A user message or any
 * other reply in between ends the group.
 */
export function subagentFollowUpRoots(
  records: Array<{
    content?: { type?: string; message?: unknown; subagentResults?: string[] };
  }>,
): Map<number, number> {
  const roots = new Map<number, number>();
  let root = -1;
  let spawned = new Set<string>();
  records.forEach((record, index) => {
    if (record.content?.type !== "bot") {
      root = -1;
      return;
    }
    const results = record.content.subagentResults;
    if (root >= 0 && results?.some((id) => spawned.has(id))) {
      roots.set(index, root);
    } else {
      root = index;
      spawned = new Set();
    }
    for (const id of spawnedAgentIds(record.content.message)) spawned.add(id);
  });
  return roots;
}
