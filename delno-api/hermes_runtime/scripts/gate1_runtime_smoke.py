"""Run inside an isolated gate1-test Hermes image, with no external services.

Exercises the *installed patched upstream modules*, not source-text assertions.
"""

from __future__ import annotations

import json
import os
import sys
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, asynccontextmanager, nullcontext
from types import SimpleNamespace

from gateway.platforms.api_server_runs import _RunLaunch, _run_agent_sync
from gateway import session_ingress
from tools import delno_run_scope, mcp_tool_handlers


def main() -> None:
    assert "delno_run_token" in _RunLaunch.__dataclass_fields__
    os.environ["DELNO_MCP_RUN_SCOPE_ENABLED"] = "1"
    assert delno_run_scope.scoped_mode_enabled()

    # Avoid the approval UI and network; the tested boundary is the upstream
    # registry handler selecting the per-turn scoped adapter.
    original_gate = mcp_tool_handlers._trust_gate_check
    original_call = delno_run_scope.call_tool
    mcp_tool_handlers._trust_gate_check = lambda *_a, **_k: None

    def fake_call(name, _args, *, timeout):
        scope = delno_run_scope.current_run_scope()
        return json.dumps({"tool": name, "run": scope.run_id if scope else None,
                           "profile": scope.profile_id if scope else None})

    live_http = "--live-http" in sys.argv
    live_api = "--live-api" in sys.argv
    identities = json.load(open("/tmp/gate1-identities.json", encoding="utf-8")) if live_api else None
    if not live_http and not live_api:
        delno_run_scope.call_tool = fake_call
    try:
        handler = mcp_tool_handlers._make_tool_handler(
            "delno_office", "get_tenant_summary" if live_api else "office.health", 5)

        class Owner:
            _memory_sessions = SimpleNamespace(checkin=lambda _agent: None)

            @contextmanager
            def _profile_scope(self, _profile):
                yield

            def _bind_api_server_session(self, **_kwargs):
                return None

        class Agent:
            def run_conversation(self, **_kwargs):
                return json.loads(handler({}))

        owner = Owner()
        api_server = SimpleNamespace(
            _publish_turn_process_ownership=lambda *_args: None,
            _clear_turn_process_ownership=lambda *_args: None,
        )

        def one_run(i):
            identity = identities[i % len(identities)] if identities else None
            profile = identity["profile"] if identity else f"tenant_gate-{i % 2}__company_main"
            run = _RunLaunch(
                owner, f"upstream-{i}", None, f"session-{i}", None, False,
                "test", [], False, {"room_dispatch": None}, profile,
                delno_run_token=identity["token"] if identity else f"test-token-{i}",
                delno_run_id=identity["run_id"] if identity else f"run-{i}",
            )
            result, _, _ = _run_agent_sync(owner, run, Agent(), lambda *_args: None,
                                           _api_server=api_server)
            return result

        with ThreadPoolExecutor(max_workers=8) as pool:
            actual_runs = list(pool.map(one_run, range(24)))
        if live_api:
            assert [r["tenant_slug"] for r in actual_runs] == [
                identities[i % len(identities)]["tenant_slug"] for i in range(24)
            ]
            assert all("mcp_api_key" not in json.dumps(r) and
                       "run_tokens" not in json.dumps(r) for r in actual_runs)
        else:
            assert [r["run"] for r in actual_runs] == [f"run-{i}" for i in range(24)]
            assert [r["profile"] for r in actual_runs] == [
                f"tenant_gate-{i % 2}__company_main" for i in range(24)
            ]
        if live_http or live_api:
            assert json.loads(handler({}))["error"] == "delno_run_scope_missing"
            swapped = delno_run_scope.bind_run_scope(
                token=identities[0]["token"] if live_api else "test-token-0",
                run_id=identities[2]["run_id"] if live_api else "run-1",
                profile_id=identities[2]["profile"] if live_api else "tenant_gate-1__company_main")
            try:
                denied = json.loads(handler({}))
                assert denied == {"error": "delno_mcp_rejected", "status": 403}
            finally:
                delno_run_scope.reset_run_scope(swapped)
        if live_api:
            from httpx import Client

            with Client(trust_env=False, timeout=5) as client:
                for identity in identities:
                    headers = {"Authorization": f"Bearer {identity['legacy_key']}"}
                    catalog = client.get("http://delno-api:8020/v1/mcp/tools", headers=headers)
                    assert catalog.status_code == 200
                    assert catalog.json()["auth_via"] == "legacy_catalog"
                    legacy_call = client.post("http://delno-api:8020/v1/mcp/tools/call",
                                              headers=headers,
                                              json={"name": "get_tenant_summary", "arguments": {}})
                    assert legacy_call.status_code == 403
                evidence = client.get("http://delno-api:8020/lab/evidence").json()
                assert len(evidence) == 24
                expected = {item["run_id"]: item["tenant_id"] for item in identities}
                assert all(item["auth_via"] == "run_token" and
                           expected[item["run_id"]] == item["tenant_id"] and
                           item["tool"] == "get_tenant_summary" for item in evidence)
                # A token cannot be replayed for a different run or profile.
                first = identities[0]
                wrong_profile = client.post("http://delno-api:8020/v1/mcp/tools/call",
                    headers={"Authorization": f"Bearer {first['token']}",
                             "X-Delno-Run-Id": first["run_id"],
                             "X-Delno-Profile-Id": identities[2]["profile"]},
                    json={"name": "get_tenant_summary", "arguments": {}})
                assert wrong_profile.status_code == 403
                # Background runs are system-scoped and cannot send mail.
                assert "send_mail_draft" not in identities[1]["grants"]
            denied_handler = mcp_tool_handlers._make_tool_handler(
                "delno_office", "send_mail_draft", 5)
            authorized = delno_run_scope.bind_run_scope(
                token=identities[1]["token"], run_id=identities[1]["run_id"],
                profile_id=identities[1]["profile"])
            try:
                assert json.loads(denied_handler({})) == {
                    "error": "delno_mcp_rejected", "status": 403,
                }
            finally:
                delno_run_scope.reset_run_scope(authorized)

        def one(i):
            profile = f"tenant_gate-{i % 2}__company_main"
            token = delno_run_scope.bind_run_scope(
                token=f"test-token-{i}", run_id=f"run-{i}", profile_id=profile)
            try:
                return json.loads(handler({}))
            finally:
                delno_run_scope.reset_run_scope(token)

        if not live_api:
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(one, range(24)))
            assert [r["run"] for r in results] == [f"run-{i}" for i in range(24)]
            assert [r["profile"] for r in results] == [
                f"tenant_gate-{i % 2}__company_main" for i in range(24)
            ]

        # The real /v1/runs path uses Session Authority. Its drain enters
        # _admission_scope, not _run_agent_sync. Exercise that exact boundary.
        import agent.runtime_scope as runtime_scope
        original_producer = session_ingress.producer_turn
        original_execution = session_ingress._execution_scope
        original_bind = runtime_scope.bind_turn
        original_fence = runtime_scope.claim_fence

        @asynccontextmanager
        async def fake_producer(*_args):
            yield

        async def fake_execution(*_args):
            return nullcontext()

        session_ingress.producer_turn = fake_producer
        session_ingress._execution_scope = fake_execution
        runtime_scope.bind_turn = lambda *_args: nullcontext()
        runtime_scope.claim_fence = lambda *_args: None
        try:
            async def admitted_turn(i, profile=None):
                own = f"tenant_gate-{i % 2}__company_main"
                authority = SimpleNamespace(profile_id=profile or own)
                row = {"request_id": f"upstream-{i}", "admission_id": f"admission-{i}"}
                ref = SimpleNamespace(session_id=f"session-{i}")
                async with session_ingress._admission_scope(authority, ref, None, row, None, {}):
                    scope = delno_run_scope.current_run_scope()
                    return (scope.run_id, scope.profile_id) if scope else None

            for i in range(24):
                delno_run_scope.register_admitted_run(
                    request_id=f"upstream-{i}", token=f"token-{i}",
                    run_id=f"run-{i}", profile_id=f"tenant_gate-{i % 2}__company_main")
            async def all_admitted():
                return await asyncio.gather(*(admitted_turn(i) for i in range(24)))

            actual = asyncio.run(all_admitted())
            assert actual == [(f"run-{i}", f"tenant_gate-{i % 2}__company_main")
                              for i in range(24)]
            assert asyncio.run(admitted_turn(0, "tenant_gate-1__company_main")) is None
            for i in range(24):
                delno_run_scope.forget_admitted_run(f"upstream-{i}")
            assert asyncio.run(admitted_turn(0)) is None
        finally:
            session_ingress.producer_turn = original_producer
            session_ingress._execution_scope = original_execution
            runtime_scope.bind_turn = original_bind
            runtime_scope.claim_fence = original_fence
    finally:
        mcp_tool_handlers._trust_gate_check = original_gate
        if not live_http and not live_api:
            delno_run_scope.call_tool = original_call
    print("gate1_runtime_scope_smoke_ok")


if __name__ == "__main__":
    main()
