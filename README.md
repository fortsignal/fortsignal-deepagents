# FortSignal Deep Agents

Run **any Deep Agent with cryptographic tool‑call protection** powered by
[FortSignal](https://fortsignal.com). Every risky operation (write file, edit
file, execute, sub‑task) is intercepted and routed through FortSignal's
challenge/verify flow — only signed, cryptographically verified intents reach
your machine.

```bash
pip install fortsignal-deepagents
```

## Quick Start

**1. Get credentials** — sign up at [dashboard.fortsignal.com](https://dashboard.fortsignal.com)
   - Go to **Settings → API Keys**, create a key → `FORTSIGNAL_API_KEY`
   - Go to **Agents → Register Agent**, download the key file → `FORTSIGNAL_AGENT_KEY`
   - Note the agent ID → `FORTSIGNAL_AGENT_ID`
   - Go to **Policies**, create one with `allowedActions: ["write_file", "edit_file"]`

**2. Run**

```bash
export FORTSIGNAL_API_KEY="fs_live_..."
export FORTSIGNAL_AGENT_ID="my-agent"
export FORTSIGNAL_AGENT_KEY="/path/to/agent-key.json"
export DEEPSEEK_API_KEY="sk-..."  # or OPENAI_API_KEY, etc.
fortsignal-deepagents --model "deepseek:deepseek-chat"
```

Every tool call is now cryptographically verified by FortSignal.

---

## Why?

Deep Agents are trusted with powerful tools — file writes, shell commands,
sub‑agent spawning. **FortSignal** adds a signing layer so every destructive
action requires a signed challenge. This prevents prompt‑injection attacks
from escalating into real damage.

---

## Setup

You need three things from the **FortSignal dashboard** (https://dashboard.fortsignal.com):

1. **API Key** — Authenticates requests to FortSignal's API
2. **User Registration** — Required for passkey (human-in-the-loop) mode
3. **Agent Registration** — Required for autonomous (agent) mode

### 1. Get your API key

1. Go to [dashboard.fortsignal.com](https://dashboard.fortsignal.com) → **Settings → API Keys**
2. Create a new key and copy it — this is your `FORTSIGNAL_API_KEY`

### 2. Get your User ID (for passkey mode)

1. In the dashboard → **Users → Add User**
2. Give it a name and ID (e.g. `"alice"`)
3. **Register a passkey** — the dashboard will prompt you to use Face ID, Touch ID, Windows Hello, or a hardware security key
4. The user's ID (e.g. `"user_alice"`) is your `FORTSIGNAL_USER_ID`

### 3. Register an agent (for autonomous mode)

1. In the dashboard → **Agents → Register Agent**
2. Give it an ID (e.g. `"my-deep-agent"`)
3. Download the generated **Ed25519 agent key file** (JSON) — this is your `FORTSIGNAL_AGENT_KEY`
4. The agent's ID (e.g. `"agent_abc123"`) is your `FORTSIGNAL_AGENT_ID`
5. **Create a policy** for this agent — define which actions (`write_file`, `execute`, etc.) and which recipients (paths, commands) it's allowed to sign
6. Optionally set up **delegation approvals** if your policy requires human delegation for certain actions

### 4. Set environment variables

```bash
# Always required:
export FORTSIGNAL_API_KEY="fs_live_..."

# For agent mode (autonomous signing):
export FORTSIGNAL_AGENT_ID="agent_abc123"
export FORTSIGNAL_AGENT_KEY="/path/to/agent-key.json"

# OR for passkey mode (human-in-the-loop):
export FORTSIGNAL_USER_ID="user_alice"

# Your LLM provider key (e.g. OpenAI) is separate:
export OPENAI_API_KEY="sk-..."
```

---

## Usage

Two modes depending on your workflow.

### Agent mode (autonomous)

For automated agents that sign challenges with an Ed25519 key.

1. Register your agent on the FortSignal dashboard and download its key file
2. Run:

```bash
export FORTSIGNAL_AGENT_ID="my-agent-id"
export FORTSIGNAL_AGENT_KEY="/path/to/agent-key.json"
fortsignal-deepagents --model "openai:gpt-4o"
```

Risky tool calls are automatically signed — no user interruption.

### Passkey mode (human-in-the-loop)

For interactive use where a human signs each challenge with WebAuthn.

```bash
export FORTSIGNAL_USER_ID="my-user-id"
fortsignal-deepagents --model "openai:gpt-4o"
```

When the agent calls a risky tool, the CLI returns WebAuthn options. Sign
in your browser, paste the assertion back, and the tool executes if verified.

### One-shot prompt

```bash
fortsignal-deepagents --model "openai:gpt-4o" --message "write hello.py"
```

---

## Python API

```python
import os
from deepagents import create_deep_agent
from fortsignal_deepagents import FortSignalMiddleware

os.environ["FORTSIGNAL_API_KEY"] = "fs_live_..."

agent = create_deep_agent(
    model="openai:gpt-4o",
    middleware=[FortSignalMiddleware(
        agent_id="my-agent-id",
        agent_key_path="/path/to/agent-key.json",
    )],
)
```

Or use the convenience helper:

```python
from fortsignal_deepagents import create_fortsignal_deep_agent

agent = create_fortsignal_deep_agent(
    model="openai:gpt-4o",
    agent_id="my-agent-id",
    agent_key_path="/path/to/agent-key.json",
)
```

---

## How it works

```
Agent calls "write_file" → FortSignalMiddleware catches it
                         → POST /challenge/start to FortSignal API
                         → Ed25519 signs challenge (agent mode)
                           or returns WebAuthn options (passkey mode)
                         → POST /challenge/verify
                         → Allow → tool executes
                         → Deny  → tool blocked with error
```

**Safe (read-only) tools** (`ls`, `read_file`, `glob`, `grep`, `fetch_url`)
pass through without any FortSignal check.

---

## Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `FORTSIGNAL_API_KEY` | — | **Required.** Your FortSignal API key |
| `FORTSIGNAL_AGENT_ID` | — | Agent ID for autonomous signing mode |
| `FORTSIGNAL_AGENT_KEY` | — | Path to Ed25519 agent key JSON file |
| `FORTSIGNAL_USER_ID` | — | User ID for passkey (WebAuthn) mode |
| `FORTSIGNAL_BASE_URL` | `https://api.fortsignal.com` | FortSignal API base URL |
| `FORTSIGNAL_MODEL` | — | Default model for `--model` |

---

## Development

```bash
git clone https://github.com/fortsignal/fortsignal-deepagents
cd fortsignal-deepagents
uv sync
uv run pytest tests/
```

---

## Tests

63 tests covering configuration, safe-tool passthrough, risky-tool interception,
challenge/verify flow (agent + passkey modes), retry logic, API error handling,
and middleware injection.

```bash
uv run pytest tests/ -v
```
