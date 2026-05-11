# FortSignal DeepAgents


**Run any Deep Agent with cryptographic tool‑call protection powered by FortSignal.**

Every risky operation (write file, edit file, execute, sub‑task) is intercepted and routed through FortSignal's challenge/verify flow — only signed, cryptographically verified intents reach your machine.

[![GitHub stars](https://img.shields.io/github/stars/fortsignal/fortsignal-deepagents.svg?style=social)](https://github.com/fortsignal/fortsignal-deepagents)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)

---

## 🚀 FortSignal Verifiable Intent Pilot Program – Now Open

We’re running a small, high-touch pilot for teams building real agents.

**Perfect if you want to test:**
- Natural Language Policies (write rules in plain English)
- Cryptographically enforced agent behavior
- Full audit + compliance visibility

👉 **[Read the full Client Guide (PDF)](https://docs.google.com/document/u/1/d/e/2PACX-1vTy4idnepjsfJL6xAyvbBC6EhNIG3zdyMgUx5Yx7vDI9A65Hol86qFv9QJb2xXTzlGgAaHvAB8cT390/pub)**

Interested? Comment **“PILOT”** below, open an issue, or DM me.

---

## Quick Start

```bash
pip install fortsignal-deepagents
Get credentials — sign up at fortsignal.com/signup
Create an API Key in Settings → API Keys
Create an Agent Passport (or User for passkey mode)
Set environment variables (see below)
Run your agent


Why?
Deep Agents are trusted with powerful tools — file writes, shell commands, sub‑agent spawning. FortSignal adds a signing layer so every destructive action requires a signed challenge. This prevents prompt‑injection attacks from escalating into real damage.

Setup
You need three things from the FortSignal dashboard (sign up first, then log in):
1. Get your API key

Dashboard → Settings → API Keys → Create a new key

2. Create an Agent Passport (recommended for autonomous mode)

Dashboard → Agent Passports → + New Agent Passport
Enter a unique agent ID
Download the generated Ed25519 key file (FORTSIGNAL_AGENT_KEY)
Assign a policy with your allowed actions

3. Set environment variables

export FORTSIGNAL_API_KEY="fs_live_..."
export FORTSIGNAL_AGENT_ID="my-agent"
export FORTSIGNAL_AGENT_KEY="/path/to/agent-key.json"
export DEEPSEEK_API_KEY="sk-..."   # or OPENAI_API_KEY, etc.

Usage
Agent mode (autonomous)

fortsignal-deepagents --model "openai:gpt-4o"

Passkey mode (human-in-the-loop)

export FORTSIGNAL_USER_ID="user_alice"
fortsignal-deepagents --model "openai:gpt-4o"

One-shot prompt

fortsignal-deepagents --model "openai:gpt-4o" --message "write hello.py"

Python API

from fortsignal_deepagents import create_fortsignal_deep_agent

agent = create_fortsignal_deep_agent(
    model="openai:gpt-4o",
    agent_id="my-agent-id",
    agent_key_path="/path/to/agent-key.json",
)

How it works

Agent calls "write_file" → FortSignalMiddleware catches it
                         → POST /challenge/start to FortSignal API
                         → Ed25519 signs challenge (agent mode) or WebAuthn (passkey mode)
                         → POST /challenge/verify
                         → Allow → tool executes
                         → Deny  → tool blocked

Safe (read-only) tools (ls, read_file, etc.) pass through without any check.

Environment Variable,Description
FORTSIGNAL_API_KEY,Required – Your FortSignal API key
FORTSIGNAL_AGENT_ID,Agent ID for autonomous mode
FORTSIGNAL_AGENT_KEY,Path to agent key JSON file
FORTSIGNAL_USER_ID,User ID for passkey mode
FORTSIGNAL_BASE_URL,Default: https://api.fortsignal.com

Development

git clone https://github.com/fortsignal/fortsignal-deepagents
cd fortsignal-deepagents
uv sync
uv run pytest tests/

Tests
63 tests covering configuration, safe-tool passthrough, risky-tool interception, challenge/verify flow, and more.

uv run pytest tests/ -v

Made with ❤️ by the FortSignal team
fortsignal.com · Dashboard


