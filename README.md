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

**1. Get credentials** — sign up at [fortsignal.com/signup](https://fortsignal.com/signup)
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

You need three things from the **FortSignal dashboard** (sign up first, then log in):

1. **API Key** — Authenticates requests to FortSignal's API
2. **User Registration** — Required for passkey (human-in-the-loop) mode
3. **Agent Registration** — Required for autonomous (agent) mode

### 0. Sign up

1. Go to [fortsignal.com/signup](https://fortsignal.com/signup), choose a plan, and create your account
2. After signing up, log in at [fortsignal.com/login](https://fortsignal.com/login)

### 1. Get your API key

1. In the dashboard → **Settings → API Keys**
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

For interactive use where a **human** must approve each risky tool call with
a WebAuthn passkey (Face ID, Touch ID, Windows Hello, hardware security key).

```bash
export FORTSIGNAL_USER_ID="my-user-id"
fortsignal-deepagents --model "openai:gpt-4o"
```

**What happens when a risky tool is called:**

1. The middleware intercepts the call and creates a challenge with FortSignal
2. Instead of auto-signing, it tells the agent to pause and wait for approval
3. The agent displays a message in the TUI like:

   ```
   ⚠️ FortSignal requires approval for `write_file` on `/etc/passwd`.
   Sign the challenge with your passkey, then paste the WebAuthn
   assertion JSON into the prompt.
   ```

4. **Sign the challenge** — use a browser-based WebAuthn tool
   (e.g. visit [webauthn.io](https://webauthn.io) or a custom dashboard)
   to authenticate with your registered passkey
5. **Paste the result** — copy the `AuthenticationResponseJSON` and paste
   it into the agent prompt. The agent re-submits the tool call with
   `_fortsignal_assertion` in the args
6. The middleware sends the assertion to FortSignal's `/challenge/verify`.
   If `"decision": "allow"` — the tool executes. If denied, the tool is
   blocked with an error message

**Note:** Agent mode (autonomous signing) is simpler for automated workflows.
Passkey mode requires the user to be present and responsive at the terminal.

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
