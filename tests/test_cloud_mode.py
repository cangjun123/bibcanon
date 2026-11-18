"""Unit and integration tests for --cloud shared lab deployment mode."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from bibcanon.models import AppConfig
from bibcanon.providers.base import RateLimitedHttpClient
from bibcanon.server.app import create_app
from bibcanon.server.auth import CloudSecurityConfig
from bibcanon.storage.cache import BibCache


def test_cloud_auth_disk_isolation_secret_masking_and_job_eviction(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("BIBCANON_HOME", str(tmp_path / "cloud_home"))
    cache = BibCache(db_path=tmp_path / "cloud_home" / "cache.sqlite3")

    def fast_client_factory(cfg: AppConfig) -> RateLimitedHttpClient:
        return RateLimitedHttpClient(config=cfg, enable_rate_sleep=False, backoff_base=0.0)

    # Verify auto-generation when password is omitted
    auto_sec = CloudSecurityConfig(enabled=True)
    assert auto_sec.username == "admin"
    assert auto_sec.auto_generated_password is True
    assert len(auto_sec.password) >= 12

    sec = CloudSecurityConfig(
        enabled=True, username="lab_member", password="unit_test_password_42"
    )

    app = create_app(
        cache=cache,
        client_factory=fast_client_factory,
        cloud_security=sec,
        max_retained_jobs=2,
    )

    with TestClient(app) as client:
        # 1. Public index.html & /api/auth/status work without auth so SPA login screen loads
        assert client.get("/").status_code == 200
        status_unauth = client.get("/api/auth/status").json()
        assert status_unauth == {
            "auth_required": True,
            "authenticated": False,
            "cloud_mode": True,
            "username": None,
        }

        # 2. Protected /api/* routes reject unauthenticated requests with 401
        assert client.get("/api/bootstrap").status_code == 401
        assert client.post("/api/jobs", json={"bib_content": "@misc{a,title={x}}"}).status_code == 401
        assert client.get("/api/settings").status_code == 401

        # 3. Wrong password returns 401
        bad_login = client.post(
            "/api/auth/login", json={"username": "lab_member", "password": "wrong"}
        )
        assert bad_login.status_code == 401

        # 4. Basic Auth works directly (for curl / CLI scripts)
        basic_boot = client.get(
            "/api/bootstrap", auth=("lab_member", "unit_test_password_42")
        )
        assert basic_boot.status_code == 200
        assert basic_boot.json()["cloud_mode"] is True

        # 5. Web Login sets HttpOnly session cookie
        ok_login = client.post(
            "/api/auth/login",
            json={"username": "lab_member", "password": "unit_test_password_42"},
        )
        assert ok_login.status_code == 200
        assert "bibcanon_session" in client.cookies

        # 6. Server-side local path reading (`bib_path`) & writing (`write-local`) are strictly 403 blocked!
        secret_file = tmp_path / "server_file.bib"
        secret_file.write_text("@misc{sec, title={Secret}}\n", encoding="utf-8")
        path_attempt = client.post("/api/jobs", json={"bib_path": str(secret_file)})
        assert path_attempt.status_code == 403

        # 7. API Key masking in /api/settings
        put_cfg = AppConfig(
            polite_email="member@lab.edu",
            openalex_api_key="oa_real_secret_key_123",
        )
        saved_masked = client.put("/api/settings", json=put_cfg.model_dump()).json()
        assert saved_masked["openalex_api_key"] == "********"
        # Updating polite_email while sending masked "********" preserves real key on disk
        saved_masked["polite_email"] = "updated@lab.edu"
        res2 = client.put("/api/settings", json=saved_masked)
        assert res2.status_code == 200
        from bibcanon.config import load_config

        disk_cfg = load_config()
        assert disk_cfg.polite_email == "updated@lab.edu"
        assert disk_cfg.openalex_api_key == "oa_real_secret_key_123"

        # 8. Uploading .bib content works & bounded memory eviction keeps <= max_retained_jobs (2)
        dummy_bib = """@misc{Authors14,
          author = {FirstName LastName},
          title = {The frobnicatable foo filter},
          year = 2014
        }"""
        job_ids: list[str] = []
        for _ in range(4):
            jr = client.post("/api/jobs", json={"bib_content": dummy_bib})
            assert jr.status_code == 200
            jid = jr.json()["job_id"]
            job_ids.append(jid)
            assert client.get(f"/api/jobs/{jid}/stream").status_code == 200

        assert len(app.state.job_manager.jobs) <= 3
        app.state.job_manager.prune_old_jobs()
        assert len(app.state.job_manager.jobs) == 2
        assert job_ids[0] not in app.state.job_manager.jobs
        assert job_ids[-1] in app.state.job_manager.jobs

        wl_res = client.post(
            "/api/export/write-local",
            json={
                "job_id": job_ids[-1],
                "style_mode": "canonical",
                "protect_title_case": True,
                "target_bib_path": str(secret_file),
                "decisions": {},
            },
        )
        assert wl_res.status_code == 403

        # 9. Logout clears cookie and re-locks /api/bootstrap
        client.post("/api/auth/logout")
        assert client.get("/api/bootstrap").status_code == 401
