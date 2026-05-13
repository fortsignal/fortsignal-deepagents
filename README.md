# FortSignal DeepAgents

**Run any Deep Agent with cryptographic tool-call protection powered by FortSignal.**

Every risky operation (file write, edit, execute, sub-task) is intercepted and routed through FortSignal's challenge/verify flow — only cryptographically signed intents reach your machine.

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-blue)](https://www.python.org/)
[![PyPI](https://img.shields.io/badge/PyPI-latest-orange)](https://pypi.org/project/fortsignal-deepagents/)

---

## Verifiable Intent Pilot — Now Open

Running a small, high-touch pilot for teams building real agents. Natural language policies, cryptographically enforced agent behavior, full audit visibility.

👉 **[Client Guide →](https://docs.google.com/document/u/1/d/e/2PACX-1vTy4idnepjsfJL6xAyvbBC6EhNIG3zdyMgUx5Yx7vDI9A65Hol86qFv9QJb2xXTzlGgAaHvAB8cT390/pub)**  
Interested? [Contact us](mailto:hr@fortsignal.com) or open an issue.

---

## Before you start

1. **API key** — Sign up at [fortsignal.com/signup](https://fortsignal.com/signup) → Dashboard → **API Keys**. Your key starts with `fs_live_`.
2. **Register your agent** — In the [dashboard](https://www.fortsignal.com/login), create an agent and generate an Ed25519 keypair. Download the private key as `agent-key.json`.
3. **Approve a delegation** — In the [dashboard](https://www.fortsignal.com/login), approve a delegation with your passkey. Agent calls return `delegation_invalid` until this is done.

---

## Install

```bash
pip install fortsignal-deepagents
```

---

## Quick Start

**Agent mode** (autonomous — Ed25519 signs each challenge automatically):

```bash
export FORTSIGNAL_API_KEY="fs_live_..."
export FORTSIGNAL_AGENT_ID="your-agent-id"
export FORTSIGNAL_AGENT_KEY="/path/to/agent-key.json"

fortsignal-deepagents --model "openai:gpt-4o"
```

**Human mode** (passkey approval required per risky action):

```bash
export FORTSIGNAL_API_KEY="fs_live_..."
export FORTSIGNAL_USER_ID="your-user-id"

fortsignal-deepagents --model "openai:gpt-4o"
```

One-shot prompt:

```bash
fortsignal-deepagents --model "openai:gpt-4o" --message "create hello.py with a greeting"
```

---

## Agent key file

`FORTSIGNAL_AGENT_KEY` points to a JSON file with your Ed25519 private key:

```json
{ "privateKey": "<base64url-encoded Ed25519 private key>" }
```

Generate from the dashboard (recommended), or create it manually:

```python
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import base64, json

key = Ed25519PrivateKey.generate()
priv = base64.urlsafe_b64encode(key.private_bytes_raw()).rstrip(b"=").decode()
pub  = base64.urlsafe_b64encode(key.public_key().public_bytes_raw()).rstrip(b"=").decode()

with open("agent-key.json", "w") as f:
    json.dump({"privateKey": priv}, f)

print("Public key to register:", pub)
```

Register the public key in the dashboard, then approve a delegation before running.

---

## How it works

1. Agent calls a risky tool → FortSignalMiddleware intercepts it
2. `/challenge/start` — challenge bound to exact action + target
3. Agent signs with Ed25519 (autonomous) or human signs with passkey (human-in-the-loop)
4. `/challenge/verify` — only verified intents execute

**Risky tools intercepted:** `write_file`, `edit_file`, `execute`, `task`, `write_todos`

**Read-only tools pass through** without any verification check.

---

## Python API

```python
from fortsignal_deepagents import create_fortsignal_deep_agent

agent = create_fortsignal_deep_agent(
    model="openai:gpt-4o",
    agent_id="my-agent-id",
    agent_key_path="/path/to/agent-key.json",
)
```

Or use the middleware directly:

```python
from fortsignal_deepagents import FortSignalMiddleware
from deepagents import create_deep_agent

middleware = FortSignalMiddleware(
    agent_id="my-agent-id",
    agent_key_path="/path/to/agent-key.json",
)
agent = create_deep_agent(model="openai:gpt-4o", middleware=[middleware])
```

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `FORTSIGNAL_API_KEY` | Yes | Your `fs_live_...` API key |
| `FORTSIGNAL_AGENT_ID` | Agent mode | Your registered agent ID |
| `FORTSIGNAL_AGENT_KEY` | Agent mode | Path to `agent-key.json` |
| `FORTSIGNAL_USER_ID` | Human mode | Your userId for passkey approval |
| `FORTSIGNAL_BASE_URL` | No | Override API base (default: `https://api.fortsignal.com`) |
| `FORTSIGNAL_LOG_LEVEL` | No | Log verbosity (default: `WARNING`) |

---

## Development

```bash
git clone https://github.com/fortsignal/fortsignal-deepagents.git
cd fortsignal-deepagents
uv sync
uv run pytest
```

---

Full detail → [api.fortsignal.com/docs](https://api.fortsignal.com/docs)

---

**License**  
MIT © FortSignal
