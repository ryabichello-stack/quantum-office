"""Slice B: Social LPR search adapters + clustering."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from modules.clients import ClientsStore
from modules.dadata import DaDataStore
from modules.social import SocialStore, list_capabilities
from modules.social.search import build_coverage, cluster_candidates, score_candidate


def test_capabilities_include_search_and_stubs():
    caps = {c["source_id"]: c for c in list_capabilities()}
    assert caps["clients"]["search"] is True
    assert caps["dadata"]["search"] is True
    assert caps["vk"]["import_only"] is True
    assert caps["linkedin"]["auto_dm"] is False


def test_lpr_search_from_clients_and_dadata_and_imports():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        clients = ClientsStore(tmp_path / "clients.db")
        with clients.connect() as conn:
            conn.execute(
                """
                INSERT INTO companies(
                    bitrix_id, title, emails_json, phones_json, inn,
                    synced_at, updated_at
                ) VALUES ('55', 'Ломбард Астра', '[]', '[]', '7707083893', 't', 't')
                """
            )
            conn.execute(
                """
                INSERT INTO contacts(
                    bitrix_id, display_name, primary_email, post,
                    company_bitrix_id, synced_at, updated_at
                ) VALUES ('c1', 'Иван Петров', 'ivan@astra.ru', 'финансовый директор',
                          '55', 't', 't')
                """
            )
        dadata = DaDataStore(tmp_path / "modules.db")
        with dadata.connect() as conn:
            conn.execute(
                """
                INSERT INTO dadata_parties(
                    inn, company_name, director_name, director_post,
                    raw_json, fetched_at, source
                ) VALUES (?, ?, ?, ?, '{}', 't', 'test')
                """,
                ("7707083893", "Ломбард Астра", "Иван Петров", "генеральный директор"),
            )

        store = SocialStore(tmp_path / "modules.db")
        with patch("modules.clients.ClientsStore", return_value=clients), patch(
            "modules.dadata.DaDataStore", return_value=dadata
        ):
            out = store.run_search(
                bitrix_company_id="55",
                company_title="Ломбард Астра",
                inn="7707083893",
                sources=["clients", "dadata", "web_import"],
                imports=[
                    {
                        "source": "web_import",
                        "full_name": "Иван Петров",
                        "profile_url": "https://example.com/ivan",
                        "role": "директор",
                    }
                ],
            )
        assert out["ok"] is True
        sources = {c["source"] for c in out["candidates"]}
        assert "clients" in sources
        assert "dadata" in sources
        assert "web_import" in sources
        # same name from 3 sources → cluster_pending, not auto-merge
        clustered = [c for c in out["candidates"] if c.get("cluster_id")]
        assert clustered
        assert all(c["status"] == "cluster_pending" for c in clustered)
        assert out["run"]["cost_estimate"] > 0
        assert "missing_roles" in out["coverage"]


def test_reject_blocks_action_task():
    with tempfile.TemporaryDirectory() as tmp:
        store = SocialStore(Path(tmp) / "m.db")
        out = store.run_search(
            company_title="X",
            sources=["web_import"],
            imports=[
                {
                    "source": "web_import",
                    "full_name": "Анна",
                    "profile_url": "https://example.com/anna",
                }
            ],
        )
        cid = out["candidates"][0]["id"]
        store.set_candidate_status(cid, "rejected")
        try:
            store.create_action_task(candidate_id=cid, draft_text="hi")
            raised = False
        except ValueError:
            raised = True
        assert raised is True


def test_manual_task_without_auto_dm():
    with tempfile.TemporaryDirectory() as tmp:
        store = SocialStore(Path(tmp) / "m.db")
        out = store.run_search(
            sources=["telegram"],
            imports=[
                {
                    "source": "telegram",
                    "username": "boss_lombard",
                    "full_name": "Босс",
                }
            ],
        )
        cid = out["candidates"][0]["id"]
        task = store.create_action_task(
            candidate_id=cid,
            draft_text="Черновик — только вручную",
            action_type="open_profile",
        )
        assert task["status"] == "open"
        assert "t.me/boss_lombard" in (task.get("profile_url") or "")
        done = store.complete_action_task(task["id"], result={"note": "opened"})
        assert done and done["status"] == "done"


def test_score_and_coverage_helpers():
    roles = [
        {"id": "economic_buyer", "labels": ["директор", "CEO"], "primary": True},
        {"id": "cfo", "labels": ["CFO", "финансовый"], "primary": True},
    ]
    c1 = score_candidate(
        {"full_name": "A", "role_guess": "генеральный директор", "source": "dadata"},
        roles=roles,
    )
    assert c1["score"] > 0.4
    c2 = score_candidate(
        {"full_name": "B", "role_guess": "CFO", "email": "b@x.ru", "source": "clients"},
        roles=roles,
    )
    cov = build_coverage([c1, c2], roles)
    assert not cov["missing_roles"] or "economic_buyer" not in cov["missing_roles"]

    clustered = cluster_candidates(
        [
            {"id": "1", "full_name": "Иван Иванов", "source": "a"},
            {"id": "2", "full_name": "Иван  Иванов", "source": "b"},
        ]
    )
    assert clustered[0]["cluster_id"] == clustered[1]["cluster_id"]
    assert clustered[0]["status"] == "cluster_pending"
