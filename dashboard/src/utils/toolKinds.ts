// One table for the built-in tools ChatUI describes in words: the reply
// summary counts them by kind, tool cards name what ran or changed, and the
// sub-agent list says what an agent is doing right now.
export type ToolKind = "code" | "command" | "edit" | "view" | "spawn" | "agent";

export const TOOL_KINDS: Record<
  string,
  // kind, verb key under toolSummary, argument shown after the verb
  { kind: ToolKind; verb: string; target: string | null }
> = {
  astrbot_execute_shell: { kind: "command", verb: "run", target: "command" },
  astrbot_shell_session: { kind: "command", verb: "run", target: "command" },
  astrbot_execute_python: { kind: "code", verb: "runPython", target: "code" },
  astrbot_execute_ipython: { kind: "code", verb: "runPython", target: "code" },
  astrbot_file_write_tool: { kind: "edit", verb: "edit", target: "path" },
  astrbot_file_edit_tool: { kind: "edit", verb: "edit", target: "path" },
  astrbot_file_read_tool: { kind: "view", verb: "read", target: "path" },
  astrbot_grep_tool: { kind: "view", verb: "search", target: "pattern" },
  spawn_agent: { kind: "spawn", verb: "spawn", target: "name" },
  // Waiting for or steering sub-agents is part of delegation.
  send_message: { kind: "agent", verb: "message", target: "agent_id" },
  wait_agent: { kind: "agent", verb: "wait", target: null },
  list_agents: { kind: "agent", verb: "list", target: null },
  get_agent_result: { kind: "agent", verb: "result", target: null },
  cancel_agent: { kind: "agent", verb: "cancel", target: null },
};
