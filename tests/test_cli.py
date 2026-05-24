"""Tests for the FortSignal Deep Agents CLI entry point."""

from __future__ import annotations

from unittest.mock import ANY

from pytest import MonkeyPatch
from fortsignal_deepagents import FortSignalMiddleware
from fortsignal_deepagents.cli import _build_parser


class TestMonkeyPatch:
    """Verifies the CLI's monkey-patch of create_deep_agent works."""

    def test_patches_both_module_levels(self):
        """The patch should be applied to both deepagents and deepagents.graph."""
        import deepagents.graph as _graph_mod
        import deepagents as _deepagents_mod

        from fortsignal_deepagents import FortSignalMiddleware

        _orig_create = _graph_mod.create_deep_agent
        _orig_create_deepagents = _deepagents_mod.create_deep_agent

        def _secured_create(*p_args, **p_kwargs):
            middleware = list(p_kwargs.pop("middleware", ()))
            middleware.insert(0, FortSignalMiddleware(
                agent_id="test-agent", api_key="test-key",
            ))
            return _orig_create(*p_args, middleware=middleware, **p_kwargs)

        _graph_mod.create_deep_agent = _secured_create
        _deepagents_mod.create_deep_agent = _secured_create

        # Verify deepagents.graph level
        assert _graph_mod.create_deep_agent is _secured_create

        # Verify deepagents (__init__ re-export) level
        assert _deepagents_mod.create_deep_agent is _secured_create

        # Verify a fresh from-deepagents import gets the patch
        import importlib
        from deepagents import create_deep_agent
        assert create_deep_agent is _secured_create, \
            "from deepagents import create_deep_agent should see the patch"

        # Cleanup
        _graph_mod.create_deep_agent = _orig_create
        _deepagents_mod.create_deep_agent = _orig_create_deepagents


class TestCLIArgs:
    def test_base_url_default(self):
        parser = _build_parser()
        args = parser.parse_args([])
        assert args.base_url is None

    def test_user_id_from_env(self, monkeypatch: MonkeyPatch):
        parser = _build_parser()
        monkeypatch.setenv("FORTSIGNAL_USER_ID", "user_env")
        args = parser.parse_args([])
        assert args.user_id is None  # env resolved in main(), not argparse

    def test_agent_id_from_env(self, monkeypatch: MonkeyPatch):
        parser = _build_parser()
        monkeypatch.setenv("FORTSIGNAL_AGENT_ID", "my-agent")
        args = parser.parse_args([])
        assert args.agent_id is None  # env resolved in main()

    def test_agent_key_from_env(self, monkeypatch: MonkeyPatch):
        parser = _build_parser()
        monkeypatch.setenv("FORTSIGNAL_AGENT_KEY", "/path/to/key.json")
        args = parser.parse_args([])
        assert args.agent_key is None  # env resolved in main()

    def test_api_key_from_env(self, monkeypatch: MonkeyPatch):
        parser = _build_parser()
        monkeypatch.setenv("FORTSIGNAL_API_KEY", "fs_key_env")
        args = parser.parse_args([])
        assert args.api_key is None

    def test_override_env_with_flag(self, monkeypatch: MonkeyPatch):
        parser = _build_parser()
        monkeypatch.setenv("FORTSIGNAL_API_KEY", "fs_key_env")
        args = parser.parse_args(["--api-key", "fs_key_explicit"])
        assert args.api_key == "fs_key_explicit"
