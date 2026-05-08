"""Tests for FortSignal Deep Agents integration.

These tests use mocked HTTP responses to verify the middleware flow
without contacting the real FortSignal API.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from pytest import MonkeyPatch

from fortsignal_deepagents import FortSignalMiddleware, RISKY_TOOLS, create_fortsignal_deep_agent
from fortsignal_deepagents.middleware import _PendingChallenge, _post_with_retry, _parse_retry_after


# ── Fake ToolCallRequest with override support ──────────────────────────

class _FakeToolCallRequest:
    """Minimal stand-in for ToolCallRequest that supports .override()."""

    def __init__(self, tool_call: dict) -> None:
        self.tool_call = tool_call
        self.state = None
        self.runtime = None

    def override(self, **overrides) -> _FakeToolCallRequest:
        new = _FakeToolCallRequest(dict(self.tool_call))
        for k, v in overrides.items():
            if k == "tool_call":
                new.tool_call = dict(v)
            else:
                setattr(new, k, v)
        return new


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_tool_call_request(tool_name: str, args: dict[str, Any] | None = None) -> _FakeToolCallRequest:
    """Build a minimal ToolCallRequest-like object for testing."""
    return _FakeToolCallRequest({
        "name": tool_name,
        "args": args or {},
        "id": f"call_{tool_name}_123",
    })


async def _fake_handler(request) -> MagicMock:
    """Handler that simulates a successful tool execution."""
    result = MagicMock()
    result.content = f"executed {request.tool_call['name']}"
    result.tool_call_id = request.tool_call["id"]
    result.status = "success"
    return result


def _mock_post_response(status_code: int = 200, json_data: dict | None = None):
    """Build a mocked POST response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = {}
    resp.json.return_value = json_data or {}
    return resp


def _install_mock_client(mw: FortSignalMiddleware) -> AsyncMock:
    """Replace the middleware's HTTP client with a mock and return it."""
    client = AsyncMock()
    mw._client = client
    return client


# ── Configuration tests ──────────────────────────────────────────────────

class TestConfig:
    def test_default_base_url(self):
        mw = FortSignalMiddleware(api_key="test_key", user_id="user_1")
        assert mw.base_url == "https://api.fortsignal.com"

    def test_custom_base_url(self):
        mw = FortSignalMiddleware(api_key="test_key", user_id="user_1", base_url="http://localhost:8000")
        assert mw.base_url == "http://localhost:8000"

    def test_strips_trailing_slash(self):
        mw = FortSignalMiddleware(api_key="test_key", user_id="user_1", base_url="https://api.fortsignal.com/")
        assert mw.base_url == "https://api.fortsignal.com"

    def test_api_key_from_env(self, monkeypatch: MonkeyPatch):
        monkeypatch.setenv("FORTSIGNAL_API_KEY", "env_key_123")
        monkeypatch.setenv("FORTSIGNAL_USER_ID", "user_env")
        mw = FortSignalMiddleware()
        assert mw.api_key == "env_key_123"
        assert mw.user_id == "user_env"

    def test_constructor_overrides_env(self, monkeypatch: MonkeyPatch):
        monkeypatch.setenv("FORTSIGNAL_API_KEY", "env_key")
        monkeypatch.setenv("FORTSIGNAL_USER_ID", "user_env")
        mw = FortSignalMiddleware(api_key="explicit_key", user_id="user_explicit")
        assert mw.api_key == "explicit_key"
        assert mw.user_id == "user_explicit"

    def test_no_api_key(self):
        mw = FortSignalMiddleware()
        assert mw.api_key == ""
        assert mw.user_id == ""


# ── RISKY_TOOLS ──────────────────────────────────────────────────────────

class TestRiskyTools:
    def test_contains_write_file(self):
        assert "write_file" in RISKY_TOOLS

    def test_contains_edit_file(self):
        assert "edit_file" in RISKY_TOOLS

    def test_contains_execute(self):
        assert "execute" in RISKY_TOOLS

    def test_contains_task(self):
        assert "task" in RISKY_TOOLS

    def test_contains_write_todos(self):
        assert "write_todos" in RISKY_TOOLS

    def test_safe_tools_not_included(self):
        safe = {"ls", "read_file", "glob", "grep", "fetch_url", "ask_user"}
        for tool in safe:
            assert tool not in RISKY_TOOLS, f"{tool} should not be risky"


# ── awrap_tool_call: safe tools pass through ────────────────────────────

class TestSafeToolPassthrough:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("safe_tool", ["ls", "read_file", "glob", "grep", "fetch_url"])
    async def test_safe_tools_pass_through(self, safe_tool):
        mw = FortSignalMiddleware(api_key="test_key", user_id="user_1")
        request = _make_tool_call_request(safe_tool)

        result = await mw.awrap_tool_call(request, _fake_handler)

        assert result.content == f"executed {safe_tool}"
        assert result.status == "success"


# ── awrap_tool_call: missing config ────────────────────────────────────

class TestMissingConfig:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("risky_tool", sorted(RISKY_TOOLS))
    async def test_blocks_without_api_key(self, risky_tool):
        mw = FortSignalMiddleware(user_id="user_1")  # no API key
        request = _make_tool_call_request(risky_tool)

        result = await mw.awrap_tool_call(request, _fake_handler)

        assert result.status == "error"
        assert "FORTSIGNAL_API_KEY" in result.content

    @pytest.mark.asyncio
    @pytest.mark.parametrize("risky_tool", sorted(RISKY_TOOLS))
    async def test_blocks_without_user_id(self, risky_tool):
        mw = FortSignalMiddleware(api_key="test_key")  # no user_id
        request = _make_tool_call_request(risky_tool)

        result = await mw.awrap_tool_call(request, _fake_handler)

        assert result.status == "error"
        assert "FORTSIGNAL_USER_ID" in result.content

    @pytest.mark.asyncio
    async def test_blocks_without_either(self):
        mw = FortSignalMiddleware()
        request = _make_tool_call_request("write_file")

        result = await mw.awrap_tool_call(request, _fake_handler)

        assert result.status == "error"
        assert "FORTSIGNAL_API_KEY" in result.content

    @pytest.mark.asyncio
    async def test_blocks_without_user_id_or_agent(self):
        """With api_key set but no user_id or agent config, should error."""
        mw = FortSignalMiddleware(api_key="test_key")
        request = _make_tool_call_request("write_file")

        result = await mw.awrap_tool_call(request, _fake_handler)

        assert result.status == "error"
        assert "no agent key or userId" in result.content


# ── awrap_tool_call: challenge start flow ───────────────────────────────

class TestChallengeStart:
    """Tests for the /challenge/start initiation phase."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("risky_tool", "tool_args", "expected_recipient"),
        [
            ("write_file", {"file_path": "/tmp/test.txt"}, "/tmp/test.txt"),
            ("edit_file", {"file_path": "/tmp/test.txt"}, "/tmp/test.txt"),
            ("execute", {"command": "ls -la"}, "ls -la"),
        ],
    )
    async def test_returns_webauthn_options_on_success(self, risky_tool, tool_args, expected_recipient):
        mw = FortSignalMiddleware(api_key="test_key", user_id="user_1")
        _install_mock_client(mw)
        webauthn_resp = {
            "challenge": "base64url_challenge...",
            "timeout": 60000,
            "rpId": "api.fortsignal.com",
            "allowCredentials": [{"type": "public-key"}],
        }
        mw._client.post.return_value = _mock_post_response(200, webauthn_resp)

        request = _make_tool_call_request(risky_tool, tool_args)
        result = await mw.awrap_tool_call(request, _fake_handler)

        assert result.status == "error"
        payload = json.loads(result.content)
        assert payload["action"] == "fortsignal_challenge_required"
        assert payload["tool"] == risky_tool
        assert payload["verification_type"] == "passkey"
        assert payload["webauthn_options"] == webauthn_resp

        # Verify the sent payload
        sent_json = mw._client.post.call_args[1]["json"]
        assert sent_json["userId"] == "user_1"
        assert sent_json["action"] == risky_tool
        assert sent_json["recipient"] == expected_recipient
        assert sent_json["metadata"]["tool"] == risky_tool

        # Verify pending challenge stored
        assert f"call_{risky_tool}_123" in mw._pending

    @pytest.mark.asyncio
    async def test_handles_api_error(self):
        mw = FortSignalMiddleware(api_key="test_key", user_id="user_1")
        _install_mock_client(mw)
        from httpx import HTTPStatusError, Request, Response
        response = Response(status_code=403, json={"error": "Invalid API key"})
        mw._client.post.side_effect = HTTPStatusError(
            "403 Forbidden", request=Request("POST", "/challenge/start"), response=response
        )

        request = _make_tool_call_request("write_file")
        result = await mw.awrap_tool_call(request, _fake_handler)

        assert result.status == "error"
        assert "/challenge/start (403)" in result.content
        assert "Invalid API key" in result.content

    @pytest.mark.asyncio
    async def test_handles_network_error(self):
        mw = FortSignalMiddleware(api_key="test_key", user_id="user_1")
        _install_mock_client(mw)
        from httpx import ConnectError
        mw._client.post.side_effect = ConnectError("connection refused")

        request = _make_tool_call_request("write_file")
        result = await mw.awrap_tool_call(request, _fake_handler)

        assert result.status == "error"
        assert "network error" in result.content.lower()


# ── awrap_tool_call: action/recipient mapping ───────────────────────────

class TestActionMapping:
    @pytest.mark.asyncio
    async def test_write_file_sends_file_path_as_recipient(self):
        mw = FortSignalMiddleware(api_key="test_key", user_id="user_1")
        _install_mock_client(mw)
        mw._client.post.return_value = _mock_post_response(200, {"challenge": "abc"})

        request = _make_tool_call_request("write_file", {"file_path": "/home/test/main.py", "content": "..."})
        await mw.awrap_tool_call(request, _fake_handler)

        sent = mw._client.post.call_args[1]["json"]
        assert sent["recipient"] == "/home/test/main.py"
        assert sent["action"] == "write_file"

    @pytest.mark.asyncio
    async def test_execute_sends_command_as_recipient(self):
        mw = FortSignalMiddleware(api_key="test_key", user_id="user_1")
        _install_mock_client(mw)
        mw._client.post.return_value = _mock_post_response(200, {"challenge": "abc"})

        request = _make_tool_call_request("execute", {"command": "rm -rf /data"})
        await mw.awrap_tool_call(request, _fake_handler)

        sent = mw._client.post.call_args[1]["json"]
        assert sent["recipient"] == "rm -rf /data"

    @pytest.mark.asyncio
    async def test_metadata_contains_full_args(self):
        mw = FortSignalMiddleware(api_key="test_key", user_id="user_1")
        _install_mock_client(mw)
        mw._client.post.return_value = _mock_post_response(200, {"challenge": "abc"})

        args = {"file_path": "/tmp/x.txt", "content": "hello"}
        request = _make_tool_call_request("write_file", args)
        await mw.awrap_tool_call(request, _fake_handler)

        sent = mw._client.post.call_args[1]["json"]
        assert sent["metadata"]["tool"] == "write_file"
        assert sent["metadata"]["args"] == args


# ── awrap_tool_call: full challenge/verify flow ─────────────────────────

class TestChallengeVerify:
    """Tests for the /challenge/verify completion phase."""

    @pytest.fixture
    def mw_with_pending(self) -> FortSignalMiddleware:
        mw = FortSignalMiddleware(api_key="test_key", user_id="user_1")
        _install_mock_client(mw)
        mw._pending["call_write_file_123"] = _PendingChallenge(
            challenge_token="call_write_file_123",
            tool_call_id="call_write_file_123",
            tool_name="write_file",
            args={"file_path": "/tmp/test.txt", "content": "hello"},
            user_id="user_1",
        )
        return mw

    @pytest.mark.asyncio
    async def test_verify_allow_executes_tool(self, mw_with_pending):
        """Allow decision should execute the tool."""
        mw = mw_with_pending
        mw._client.post.return_value = _mock_post_response(200, {
            "decision": "allow",
            "signalId": "sig_abc",
            "verifiedBy": "human",
        })

        assertion = {"id": "cred_1", "response": {"signature": "..."}}
        request = _make_tool_call_request("write_file", {
            "file_path": "/tmp/test.txt",
            "_fortsignal_assertion": assertion,
        })
        result = await mw.awrap_tool_call(request, _fake_handler)

        assert result.status == "success"
        assert result.content == "executed write_file"

        # Verify assertion was sent to /challenge/verify
        mw._client.post.assert_awaited_once_with("/challenge/verify", json=assertion)

        # Pending state cleaned up
        assert "call_write_file_123" not in mw._pending

    @pytest.mark.asyncio
    async def test_verify_deny_blocks_tool(self, mw_with_pending):
        mw = mw_with_pending
        mw._client.post.return_value = _mock_post_response(200, {
            "decision": "deny",
            "reason": "verification_failed",
        })

        request = _make_tool_call_request("write_file", {
            "_fortsignal_assertion": {"id": "bad_cred"},
        })
        result = await mw.awrap_tool_call(request, _fake_handler)

        assert result.status == "error"
        assert "verification_failed" in result.content
        assert "call_write_file_123" not in mw._pending

    @pytest.mark.asyncio
    async def test_verify_http_error(self, mw_with_pending):
        mw = mw_with_pending
        from httpx import HTTPStatusError, Request, Response
        response = Response(status_code=400, json={"error": "invalid_assertion"})
        mw._client.post.side_effect = HTTPStatusError(
            "400 Bad Request", request=Request("POST", "/challenge/verify"), response=response
        )

        request = _make_tool_call_request("write_file", {
            "_fortsignal_assertion": {"bad": "data"},
        })
        result = await mw.awrap_tool_call(request, _fake_handler)

        assert result.status == "error"
        assert "/challenge/verify (400)" in result.content
        assert "call_write_file_123" not in mw._pending

    @pytest.mark.asyncio
    async def test_verify_without_assertion_returns_challenge(self, mw_with_pending):
        mw = mw_with_pending

        request = _make_tool_call_request("write_file", {"file_path": "/tmp/test.txt"})
        result = await mw.awrap_tool_call(request, _fake_handler)

        assert result.status == "error"
        payload = json.loads(result.content)
        assert payload["action"] == "fortsignal_challenge_required"

        # Pending state should still exist
        assert "call_write_file_123" in mw._pending

    @pytest.mark.asyncio
    async def test_preserves_original_args_after_verify(self, mw_with_pending):
        mw = mw_with_pending
        mw._client.post.return_value = _mock_post_response(200, {"decision": "allow"})

        original_handler_args = {}

        async def capture_handler(request):
            original_handler_args["tool_call"] = dict(request.tool_call)
            return await _fake_handler(request)

        request = _make_tool_call_request("write_file", {
            "file_path": "/tmp/test.txt",
            "extra": 42,
            "_fortsignal_assertion": {"id": "cred_1"},
        })
        await mw.awrap_tool_call(request, capture_handler)

        # Handler receives original stored args, not the ones with assertion
        assert original_handler_args["tool_call"]["args"] == {"file_path": "/tmp/test.txt", "content": "hello"}
        assert "_fortsignal_assertion" not in original_handler_args["tool_call"]["args"]

    @pytest.mark.asyncio
    async def test_assertion_as_json_string(self, mw_with_pending):
        """Assertion passed as a JSON string should be parsed."""
        mw = mw_with_pending
        mw._client.post.return_value = _mock_post_response(200, {"decision": "allow"})

        request = _make_tool_call_request("write_file", {
            "_fortsignal_assertion": '{"id": "cred_json_str", "response": {"sig": "x"}}',
        })
        result = await mw.awrap_tool_call(request, _fake_handler)

        assert result.status == "success"
        # Verify the parsed JSON was sent
        sent_json = mw._client.post.call_args[1]["json"]
        assert sent_json["id"] == "cred_json_str"


# ── create_fortsignal_deep_agent ────────────────────────────────────────

class TestCreateFortSignalAgent:
    def test_injects_middleware(self):
        with patch("deepagents.create_deep_agent") as mock_create:
            mock_create.return_value = "agent_graph"

            agent = create_fortsignal_deep_agent(
                model="openai:gpt-4o",
                user_id="user_1",
                api_key="test_key",
            )

            mock_create.assert_called_once()
            _, kwargs = mock_create.call_args
            assert kwargs["model"] == "openai:gpt-4o"
            assert len(kwargs["middleware"]) >= 1
            assert isinstance(kwargs["middleware"][0], FortSignalMiddleware)
            assert kwargs["middleware"][0].user_id == "user_1"

    def test_preserves_additional_middleware(self):
        class DummyMiddleware:
            pass

        with patch("deepagents.create_deep_agent") as mock_create:
            mock_create.return_value = "agent_graph"

            agent = create_fortsignal_deep_agent(
                model="openai:gpt-4o",
                api_key="test_key",
                user_id="user_1",
                middleware=[DummyMiddleware()],
            )

            _, kwargs = mock_create.call_args
            mw_list = list(kwargs["middleware"])
            assert isinstance(mw_list[0], FortSignalMiddleware)
            assert isinstance(mw_list[1], DummyMiddleware)


# ── awrap_model_call ────────────────────────────────────────────────────

class TestModelCall:
    @pytest.mark.asyncio
    async def test_injects_system_prompt_when_key_set(self):
        mw = FortSignalMiddleware(api_key="test_key", user_id="user_1")

        request = MagicMock()
        request.system_message = None

        async def handler(req):
            return MagicMock()

        await mw.awrap_model_call(request, handler)

        assert request.system_message is not None

    @pytest.mark.asyncio
    async def test_no_injection_when_key_not_set(self):
        mw = FortSignalMiddleware()

        request = MagicMock()
        request.system_message = None

        async def handler(req):
            return MagicMock()

        await mw.awrap_model_call(request, handler)

        assert request.system_message is None


# ── Edge cases ──────────────────────────────────────────────────────────

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_concurrent_different_tools(self):
        mw = FortSignalMiddleware(api_key="test_key", user_id="user_1")
        _install_mock_client(mw)

        # First challenge
        mw._client.post.return_value = _mock_post_response(200, {"challenge": "abc"})
        req_a = _make_tool_call_request("write_file", {"file_path": "/a.txt"})
        result_a = await mw.awrap_tool_call(req_a, _fake_handler)
        assert json.loads(result_a.content)["action"] == "fortsignal_challenge_required"

        # Second challenge
        mw._client.post.reset_mock()
        mw._client.post.return_value = _mock_post_response(200, {"challenge": "def"})
        req_b = _make_tool_call_request("execute", {"command": "test"})
        result_b = await mw.awrap_tool_call(req_b, _fake_handler)
        assert json.loads(result_b.content)["action"] == "fortsignal_challenge_required"

        assert len(mw._pending) == 2

    @pytest.mark.asyncio
    async def test_no_args_tool_call(self):
        mw = FortSignalMiddleware(api_key="test_key", user_id="user_1")
        _install_mock_client(mw)
        mw._client.post.return_value = _mock_post_response(200, {"challenge": "abc"})

        request = _make_tool_call_request("write_todos", None)
        result = await mw.awrap_tool_call(request, _fake_handler)

        payload = json.loads(result.content)
        assert payload["action"] == "fortsignal_challenge_required"


# ── Retry logic ─────────────────────────────────────────────────────────

class TestRetryLogic:
    @pytest.mark.asyncio
    async def test_retry_on_429_then_succeeds(self):
        mw = FortSignalMiddleware(api_key="test_key", user_id="user_1")
        client = _install_mock_client(mw)

        from httpx import HTTPStatusError, Request, Response

        def _resp_429():
            resp = MagicMock(spec=Response)
            resp.status_code = 429
            resp.headers = {}
            resp.json.return_value = {}
            resp.raise_for_status.side_effect = HTTPStatusError(
                "429 Too Many Requests",
                request=Request("POST", "/challenge/start"),
                response=resp,
            )
            return resp

        def _resp_200():
            resp = MagicMock(spec=Response)
            resp.status_code = 200
            resp.headers = {}
            resp.json.return_value = {"challenge": "abc"}
            return resp

        client.post.side_effect = [_resp_429(), _resp_200()]

        request = _make_tool_call_request("write_file", {"file_path": "/test.txt"})
        result = await mw.awrap_tool_call(request, _fake_handler)

        payload = json.loads(result.content)
        assert payload["action"] == "fortsignal_challenge_required"
        assert client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_all_429_returns_error(self):
        mw = FortSignalMiddleware(api_key="test_key", user_id="user_1")
        client = _install_mock_client(mw)

        from httpx import HTTPStatusError, Request, Response

        def _resp_429():
            resp = MagicMock(spec=Response)
            resp.status_code = 429
            resp.headers = {}
            resp.json.return_value = {}
            resp.raise_for_status.side_effect = HTTPStatusError(
                "429 Too Many Requests",
                request=Request("POST", "/challenge/start"),
                response=resp,
            )
            return resp

        client.post.return_value = _resp_429()

        request = _make_tool_call_request("write_file", {"file_path": "/test.txt"})
        result = await mw.awrap_tool_call(request, _fake_handler)

        assert result.status == "error"
        assert "429" in result.content

    def test_parse_retry_after_header(self):
        resp = MagicMock()
        resp.headers = {"Retry-After": "5"}
        assert _parse_retry_after(resp) == 5.0

    def test_parse_retry_after_missing(self):
        resp = MagicMock()
        resp.headers = {}
        assert _parse_retry_after(resp) == 1.0

    def test_parse_retry_after_invalid(self):
        resp = MagicMock()
        resp.headers = {"Retry-After": "abc"}
        assert _parse_retry_after(resp) == 1.0


class TestAgentMode:
    """Tests for autonomous Ed25519 agent mode."""

    @pytest.fixture
    def agent_key_file(self, tmp_path):
        """Create a temporary agent key file."""
        import json, base64
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        key = Ed25519PrivateKey.generate()
        priv_bytes = key.private_bytes_raw()
        priv_b64 = base64.urlsafe_b64encode(priv_bytes).rstrip(b"=").decode()
        path = tmp_path / "agent_key.json"
        path.write_text(json.dumps({"privateKey": priv_b64}))
        return str(path)

    @pytest.mark.asyncio
    async def test_agent_mode_uses_agent_id_in_payload(self, agent_key_file):
        """Agent mode sends agentId instead of userId."""
        mw = FortSignalMiddleware(api_key="test_key", agent_id="test-agent", agent_key_path=agent_key_file)
        _install_mock_client(mw)
        mw._client.post.return_value = _mock_post_response(200, {
            "challenge": "base64url_challenge...",
            "agentId": "test-agent",
            "delegationId": "del_abc",
        })

        request = _make_tool_call_request("write_file", {"file_path": "/tmp/test.txt"})
        # In agent mode, the middleware should auto-sign and verify
        result = await mw.awrap_tool_call(request, _fake_handler)

        # Verify the sent payload used agentId
        sent_json = mw._client.post.call_args[1]["json"]
        assert "agentId" in sent_json
        assert sent_json["agentId"] == "test-agent"
        assert "userId" not in sent_json

    @pytest.mark.asyncio
    async def test_agent_mode_auto_signs_and_verifies(self, agent_key_file):
        """Agent mode should automatically complete the verify step."""
        mw = FortSignalMiddleware(api_key="test_key", agent_id="test-agent", agent_key_path=agent_key_file)
        _install_mock_client(mw)

        # First call: /challenge/start returns challenge
        # Second call: /challenge/verify returns allow
        from httpx import Request, Response
        start_resp = MagicMock(spec=Response)
        start_resp.status_code = 200
        start_resp.headers = {}
        start_resp.json.return_value = {
            "challenge": "dGVzdC1jaGFsbGVuZ2U",  # "test-challenge" base64url
        }

        verify_resp = MagicMock(spec=Response)
        verify_resp.status_code = 200
        verify_resp.headers = {}
        verify_resp.json.return_value = {
            "decision": "allow",
            "signalId": "sig_123",
            "verifiedBy": "agent",
            "agentId": "test-agent",
        }

        mw._client.post.side_effect = [start_resp, verify_resp]

        request = _make_tool_call_request("write_file", {"file_path": "/tmp/test.txt"})
        result = await mw.awrap_tool_call(request, _fake_handler)

        # Should have succeeded (tool executed)
        assert result.status == "success"
        # Should have called both endpoints
        assert mw._client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_agent_mode_denied_blocks_tool(self, agent_key_file):
        """Agent mode with a deny decision should block the tool."""
        mw = FortSignalMiddleware(api_key="test_key", agent_id="test-agent", agent_key_path=agent_key_file)
        _install_mock_client(mw)

        from httpx import Request, Response
        start_resp = MagicMock(spec=Response)
        start_resp.status_code = 200
        start_resp.headers = {}
        start_resp.json.return_value = {
            "challenge": "dGVzdC1kZW55",
        }

        verify_resp = MagicMock(spec=Response)
        verify_resp.status_code = 200
        verify_resp.headers = {}
        verify_resp.json.return_value = {
            "decision": "deny",
            "reason": "action_not_allowed",
        }

        mw._client.post.side_effect = [start_resp, verify_resp]

        request = _make_tool_call_request("write_file", {"file_path": "/tmp/test.txt"})
        result = await mw.awrap_tool_call(request, _fake_handler)

        assert result.status == "error"
        assert "action_not_allowed" in result.content
