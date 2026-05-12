# FortSignal DeepAgents

**Run any Deep Agent with cryptographic tool-call protection powered by FortSignal.**

Every risky operation (file write, edit, execute, sub-task) is intercepted and routed through FortSignal’s challenge/verify flow — only cryptographically signed intents reach your machine.

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-blue)](https://www.python.org/)
[![PyPI](https://img.shields.io/badge/PyPI-latest-orange)](https://pypi.org/project/fortsignal-deepagents/)

---

## 📢 FortSignal Verifiable Intent Pilot – Now Open

We’re running a small, high-touch pilot for teams building real agents.

**Perfect if you want to test:**
- Natural Language Policies (plain-English rules)
- Cryptographically enforced agent behavior
- Full audit + compliance visibility

👉 **[Read the full Client Guide (PDF)](https://fortsignal.com/docs/client-guide.pdf)**  
Interested? Comment **“PILOT”** on any post, open an issue, or DM us.

---

## Quick Start

```bash
pip install fortsignal-deepagents
```

```bash
# Set your credentials (from FortSignal dashboard)
export FORTSIGNAL_API_KEY="fs_live_..."
export FORTSIGNAL_AGENT_ID="your-agent-id"
export FORTSIGNAL_AGENT_KEY="/path/to/agent-key.json"
# (or use FORTSIGNAL_USER_ID for passkey/human mode)
```

**Run your agent**
```bash
fortsignal-deepagents --model "openai:gpt-4o"
```

**One-shot prompt**
```bash
fortsignal-deepagents --model "openai:gpt-4o" --message "create hello.py with a greeting"
```

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

---

## How It Works

1. Agent calls a risky tool → FortSignalMiddleware intercepts it  
2. Challenge sent to FortSignal API  
3. Agent (Ed25519) or human (passkey/YubiKey) signs  
4. Only verified intents execute  

Safe read-only tools bypass the check.

---

## Development

```bash
git clone https://github.com/fortsignal/fortsignal-deepagents.git
cd fortsignal-deepagents
uv sync
uv run pytest
```

---

**Made with ❤️ by the FortSignal team**  
[fortsignal.com](https://fortsignal.com) • [Docs](https://fortsignal.com/docs)

---

**License**  
MIT © FortSignal

