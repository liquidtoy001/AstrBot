# Subagents {#agent-handsoff-and-subagent}

Subagents let the built-in AI delegate tasks to background agents with independent contexts while continuing the main conversation. No plugin installation is required.

## Enable subagents

Open **Config → AI → Capabilities → Subagents** in the target profile and enable the capability. You can use generic subagents immediately. The default concurrency limit is 3, and the default timeout is 600 seconds, including queue time.

![Subagent capability settings](images/subagent-settings-en.png)

## Configure a specialized agent

1. Click **Configure Specialized Agents**, then **Create Agent**.
2. Select the AstrBot runtime and enter a name and description. The description helps the main agent decide when to delegate.
3. Select a persona and chat model, or leave them empty to follow the main agent.
4. Save, close the dialog, and select the agent under **Specialized Agent Configurations**.

**Which model a sub-agent uses**: a specialized agent with a chat model uses that model. A specialized agent without one, and a generic sub-agent, use the model of the request that started it (for example the model chosen in ChatUI for that message), else the session default. The main agent sees each specialized agent's model and all available chat models; when the user asks for a specific model (such as "start 3 luna agents"), it uses a specialized agent on that model if there is one. Otherwise it passes the model's `provider_id` to `spawn_agent`, and AstrBot creates a specialized agent on that model with no persona (named like "gpt-6-luna worker", with a description saying it was created automatically) and selects it in the profile the conversation uses. Several spawned at once create only one; later requests for the model reuse it. Only enabled chat models can be used, an unknown ID is rejected with the list of valid ones, and no provider or credential is ever created. An existing specialized agent on that model with no persona (created by hand or automatically) is reused instead of creating another. The main agent tells the user when it created one; it also appears in ChatUI **Settings → Agent → Subagents** and in the config page's list of specialized agents, where it can be edited or deleted in **Configure Specialized Agents**. A chat model ID passed in `config_id` by mistake is treated as `provider_id`, and empty `config_id` or `provider_id` values count as not set.

![Subagent management](images/subagent-create-en.png)

![Create Agent form](images/subagent-edit-en.png)

The selected persona supplies the agent's instructions, tools, and skills, within the parent agent's authorized capabilities. Other execution settings, such as step limits and tool timeouts, follow the main agent when the session is created. Configuration changes apply to new sessions.

To edit an agent, click its card. To delete one, remove any references from profiles or other agent configurations first. Configurations for unavailable runtimes remain saved but cannot start new sessions.

## Delegate and follow up

Ask the main agent to delegate a task, for example: “Have a subagent review this report while we discuss the next steps.” The main agent uses these tools:

| Tool | Purpose |
| --- | --- |
| `spawn_agent` | Start a background task. |
| `list_agents` | Check task status. |
| `wait_agent` | Wait for results. |
| `get_agent_result` | Read a result. |
| `send_message` | Add instructions to an existing agent. |
| `cancel_agent` | Stop a task. |

The configuration dialog manages saved agents. To check or stop running tasks, ask the main agent, or in ChatUI open the workbench's **Session** view and look at the **Sub-agents** section:

- Each row shows "model · thinking level · short task", what the agent is doing (for example running code or editing files), and how long it has run. The thinking level appears only when the sub-agent's provider configuration sets one.
- A running sub-agent has a square button at the end of its row that stops it and its queued instructions. The session is kept, so the main agent can still send it new instructions.
- Expand a row for the full name, provider, persona, latest request context, tools, task, result, and total usage (input, cache hits, and output as reported by the provider; marked "some requests unreported" when a request reported nothing, in which case actual usage is higher).
- A reply that started sub-agents shows one chip per sub-agent below it (for example "haiku running code"); select a chip to find it in the **Session** view.

Subagents cannot create further subagents.

Delegated input supports text, images, and file references. Images from the original user message are not forwarded automatically. Follow-up instructions retain the subagent's history; in the built-in runtime, follow-up images and files are passed as text references.

## Restart and conversation behavior

Users in the same conversation share its subagents. Results return to the original parent conversation, even if you switch conversations. Deleted or stopped parents are not woken.

After a restart, queued and unfinished tasks are marked interrupted and are not replayed automatically. Check their status, then ask the main agent to send new instructions to continue in the same subagent conversation.

## Upgrade notes

The previous **SubAgent Orchestration / Subagent Management** sidebar entry has moved to **Config → AI → Capabilities → Subagents → Configure Specialized Agents**. The `/subagent` URL remains accessible.

Existing global settings and expert configurations migrate automatically. Existing conversations and history are preserved.

API clients should replace `/api/v1/subagents/config` and `/api/subagent/config` with `/api/v1/agent-configs` and `/api/v1/agent-configs/{config_id}`. Use `/api/v1/agent-runtimes` to list runtimes and their defaults. These endpoints require the `config` scope; see [OpenAPI scopes](../dev/openapi-scopes.md).

For plugin integration, see [running an Agent](../dev/star/guides/ai/agent.md#run-session-agent) and [runtime events](../dev/star/guides/ai/agent.md#runtime-events).
