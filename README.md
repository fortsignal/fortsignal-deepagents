# FortSignal Deep Agents

Run **any Deep Agent with cryptographic tool‑call protection** powered by
[FortSignal](https://fortsignal.com). Every risky operation (write file, edit
file, execute, sub‑task) is intercepted and routed through FortSignal's
challenge/verify flow — only signed, cryptographically verified intents reach
your machine.

```bash
pip install fortsignal-deepagents
export FORTSIGNAL_API_KEY="fs_live_..."
fortsignal-deepagents
```

---

## Why?

Deep Agents are trusted with powerful tools — file writes, shell commands,
sub‑agent spawning. **FortSignal** adds a signing layer so every destructive
action requires a signed challenge. This prevents prompt‑injection attacks
from escalating into real damage.

---

## Setup

You need a **FortSignal API key** and either an **agent registration** or a
**user registration** on FortSignal.

### 1. Get credentials

Sign up at [fortsignal.com](https://fortsignal.com) and get your API key.

### 2. Set environment variables

```bash
export FORTSIGNAL_API_KEY="fs_live_..."
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
