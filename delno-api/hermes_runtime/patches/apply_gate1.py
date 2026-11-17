"""Fail-closed, exact-source patch for pinned Hermes v0.23.2.

Do not apply to a different upstream revision. Run at image build, never on a
live container or mounted profile volume.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


EXPECTED_REV = "ae2a81ccc00e9b7c06301523e5bb09608397149c"


def replace_once(path: Path, old: str, new: str) -> None:
    source = path.read_text(encoding="utf-8")
    if source.count(old) != 1:
        raise SystemExit(f"Gate 1 patch refused: expected one anchor in {path}")
    path.write_text(source.replace(old, new, 1), encoding="utf-8")


def main(root: Path) -> None:
    actual = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if actual != EXPECTED_REV:
        raise SystemExit(f"Gate 1 patch refused: Hermes revision {actual} is not {EXPECTED_REV}")
    runs = root / "gateway/platforms/api_server_runs.py"
    ingress = root / "gateway/session_ingress.py"
    handlers = root / "tools/mcp_tool_handlers.py"
    replace_once(runs, "from dataclasses import dataclass\n",
                 "from dataclasses import dataclass, field\n")
    replace_once(runs,
                 "    request_profile: Any\n    turn_author:",
                 "    request_profile: Any\n    delno_run_token: str = field(default=\"\", repr=False)\n"
                 "    delno_run_id: str = \"\"\n    turn_author:")
    replace_once(runs,
                 "        request_profile=_api_server._api_request_profile.get(),\n"
                 "        turn_author=turn_author,",
                 "        request_profile=_api_server._api_request_profile.get(),\n"
                 "        delno_run_token=request.headers.get(\"X-Delno-Run-Token\", \"\"),\n"
                 "        delno_run_id=request.headers.get(\"X-Delno-Run-Id\", \"\"),\n"
                 "        turn_author=turn_author,")
    replace_once(runs,
                 "    # A canonical Bot Chat that a Desktop holds live is that Desktop's to run:",
                 "    from tools.delno_run_scope import register_admitted_run\n"
                 "    register_admitted_run(request_id=run_id, token=launch.delno_run_token,\n"
                 "                          run_id=launch.delno_run_id, profile_id=launch.request_profile)\n"
                 "    # A canonical Bot Chat that a Desktop holds live is that Desktop's to run:")
    replace_once(runs,
                 "    with self._profile_scope(run.request_profile):\n        try:\n"
                 "            # Contextvars, not process env: concurrent runs must not share identity.",
                 "    with self._profile_scope(run.request_profile):\n"
                 "        from tools.delno_run_scope import bind_run_scope, reset_run_scope\n"
                 "        delno_scope_token = bind_run_scope(\n"
                 "            token=run.delno_run_token, run_id=run.delno_run_id,\n"
                 "            profile_id=run.request_profile or \"\")\n"
                 "        try:\n"
                 "            # Contextvars, not process env: concurrent runs must not share identity.")
    replace_once(runs,
                 "                for token, reset in resets:\n"
                 "                    with suppress(Exception):\n"
                 "                        reset(token)\n"
                 "        return r, _run_usage(agent), _served_runtime(agent)",
                 "                for token, reset in resets:\n"
                 "                    with suppress(Exception):\n"
                 "                        reset(token)\n"
                 "                reset_run_scope(delno_scope_token)\n"
                 "        return r, _run_usage(agent), _served_runtime(agent)")
    replace_once(handlers,
                 "        if error is not None:\n"
                 "            return error\n"
                 "        server, error = None, _check_circuit_breaker(server_name)",
                 "        if error is not None:\n"
                 "            return error\n"
                 "        if server_name == \"delno_office\":\n"
                 "            from tools.delno_run_scope import call_tool as delno_call_tool, scoped_mode_enabled\n"
                 "            if scoped_mode_enabled():\n"
                 "                return delno_call_tool(tool_name, args, timeout=tool_timeout)\n"
                 "        server, error = None, _check_circuit_breaker(server_name)")
    replace_once(ingress,
                 "    from agent.runtime_scope import bind_turn, claim_fence\n"
                 "    async with producer_turn(authority, row, event, captured):\n"
                 "        with await _execution_scope(authority, home), bind_turn(ref.session_id, row['admission_id'], claim_fence(row)):\n"
                 "            yield\n",
                 "    from agent.runtime_scope import bind_turn, claim_fence\n"
                 "    from tools.delno_run_scope import admitted_run_scope, bind_run_scope, reset_run_scope\n"
                 "    scope = admitted_run_scope(row.get('request_id', ''), authority.profile_id)\n"
                 "    async with producer_turn(authority, row, event, captured):\n"
                 "        with await _execution_scope(authority, home), bind_turn(ref.session_id, row['admission_id'], claim_fence(row)):\n"
                 "            scope_token = (bind_run_scope(token=scope.token, run_id=scope.run_id,\n"
                 "                                          profile_id=scope.profile_id) if scope else None)\n"
                 "            try:\n"
                 "                yield\n"
                 "            finally:\n"
                 "                if scope_token is not None:\n"
                 "                    reset_run_scope(scope_token)\n")
    source = runs.read_text(encoding="utf-8")
    retire = "\n        _retire_live_run(self, run_id)\n"
    if source.count(retire) != 2:
        raise SystemExit("Gate 1 patch refused: expected two run retirement paths")
    source = source.replace(retire,
        "        from tools.delno_run_scope import forget_admitted_run\n"
        "        forget_admitted_run(run_id)\n"
        "        _retire_live_run(self, run_id)\n")
    runs.write_text(source, encoding="utf-8")
    extra = root / "tools/delno_run_scope.py"
    extra.write_bytes(Path(__file__).with_name("delno_run_scope.py").read_bytes())
    for path in (runs, ingress, handlers, extra):
        subprocess.check_call([sys.executable, "-m", "py_compile", str(path)])


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "/opt/hermes-agent"))
