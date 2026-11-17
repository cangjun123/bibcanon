"""Phase 4 integration tests for FastAPI REST + SSE endpoints and Typer CLI subcommands."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import respx
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from bibcanon.cli import app as cli_app
from bibcanon.models import AppConfig, VerificationStatus
from bibcanon.providers.base import RateLimitedHttpClient
from bibcanon.server.app import create_app
from bibcanon.storage.cache import BibCache

runner = CliRunner()


SAMPLE_WORKFLOW_BIB = """% === Header Comment ===
@string{icml = "ICML"}

@article{lora2021preprint,
  title = {LoRA: Low-Rank Adaptation of Large Language Models},
  author = {Hu, Edward J. and Shen, Yelong},
  journal = {arXiv preprint arXiv:2106.09685},
  year = {2021}
}

% Keep this comment intact!
@inproceedings{hallucinated2025paper,
  title = {Nonexistent Hyper-Dimensional Teleportation Network},
  author = {Ghost, Zero and Phantom, One},
  booktitle = {CVPR},
  year = {2025}
}
"""


def _setup_upstream_mocks(router: respx.MockRouter) -> None:
    def _dblp_handler(request: httpx.Request) -> httpx.Response:
        q = request.url.params.get("q", "").lower()
        if "lora" in q:
            return httpx.Response(
                200,
                json={
                    "result": {
                        "hits": {
                            "hit": [
                                {
                                    "info": {
                                        "title": "LoRA: Low-Rank Adaptation of Large Language Models.",
                                        "authors": {
                                            "author": [
                                                {"text": "Edward J. Hu"},
                                                {"text": "Yelong Shen"},
                                            ]
                                        },
                                        "venue": "ICLR",
                                        "year": "2022",
                                        "type": "Conference and Workshop Papers",
                                        "key": "conf/iclr/HuSWALWWC22",
                                        "ee": "https://openreview.net/forum?id=nZeVKeeFYf9",
                                    }
                                }
                            ]
                        }
                    }
                },
            )
        return httpx.Response(200, json={"result": {"hits": {}}})

    router.get("https://dblp.org/search/publ/api").mock(side_effect=_dblp_handler)
    router.get("https://api.crossref.org/works").mock(
        return_value=httpx.Response(200, json={"message": {"items": []}})
    )
    router.get("https://api.openalex.org/works").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    def _arxiv_handler(request: httpx.Request) -> httpx.Response:
        id_list = request.url.params.get("id_list", "")
        sq = request.url.params.get("search_query", "").lower()
        if "2106.09685" in id_list or "lora" in sq:
            return httpx.Response(
                200,
                text="""<?xml version="1.0" encoding="UTF-8"?>
                <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
                  <entry>
                    <id>http://arxiv.org/abs/2106.09685v2</id>
                    <published>2021-06-17T00:00:00Z</published>
                    <title>LoRA: Low-Rank Adaptation of Large Language Models</title>
                    <author><name>Edward J. Hu</name></author>
                    <author><name>Yelong Shen</name></author>
                    <arxiv:primary_category term="cs.CL"/>
                  </entry>
                </feed>""",
            )
        return httpx.Response(
            200,
            text='<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>',
        )

    router.get("https://export.arxiv.org/api/query").mock(side_effect=_arxiv_handler)
    router.get("https://arxiv.org/bibtex/2106.09685").mock(
        return_value=httpx.Response(
            200,
            text="""@misc{hu2021lora,
              title={LoRA: Low-Rank Adaptation of Large Language Models},
              author={Edward J. Hu and Yelong Shen},
              year={2021},
              eprint={2106.09685},
              archivePrefix={arXiv},
              primaryClass={cs.CL},
              url={https://arxiv.org/abs/2106.09685}
            }""",
        )
    )
    router.get("https://api.semanticscholar.org/graph/v1/paper/search").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    router.get("https://api2.openreview.net/notes").mock(
        return_value=httpx.Response(
            200,
            json={
                "notes": [
                    {
                        "id": "nZeVKeeFYf9",
                        "content": {
                            "venue": {"value": "ICLR 2022"},
                            "_bibtex": {
                                "value": """@inproceedings{hu2022lora,
title={LoRA: Low-Rank Adaptation of Large Language Models},
author={Edward J Hu and Yelong Shen},
booktitle={International Conference on Learning Representations},
year={2022},
url={https://openreview.net/forum?id=nZeVKeeFYf9}
}"""
                            },
                        },
                    }
                ]
            },
        )
    )


def test_fastapi_rest_sse_paste_merge_and_write_local_closed_loop(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("BIBCANON_HOME", str(tmp_path / "home"))
    cache = BibCache(db_path=tmp_path / "home" / "cache.sqlite3")

    def fast_client_factory(cfg: AppConfig) -> RateLimitedHttpClient:
        return RateLimitedHttpClient(config=cfg, enable_rate_sleep=False, backoff_base=0.0)

    fastapi_app = create_app(cache=cache, client_factory=fast_client_factory)

    with respx.mock(assert_all_called=False) as mock_router:
        _setup_upstream_mocks(mock_router)

        with TestClient(fastapi_app) as client:
            # 1. Settings roundtrip
            put_res = client.put(
                "/api/settings",
                json=AppConfig(polite_email="lab@univ.edu").model_dump(),
            )
            assert put_res.status_code == 200
            assert client.get("/api/settings").json()["polite_email"] == "lab@univ.edu"

            # 2. Create scan job
            create_res = client.post(
                "/api/jobs",
                json={"bib_content": SAMPLE_WORKFLOW_BIB, "force_refresh": True},
            )
            assert create_res.status_code == 200
            job_data = create_res.json()
            job_id = job_data["job_id"]
            assert job_data["total_entries"] == 2

            # 3. Consume SSE stream (`entry_updated` + `job_completed`)
            sse_res = client.get(f"/api/jobs/{job_id}/stream")
            assert sse_res.status_code == 200
            sse_text = sse_res.text
            assert "event: entry_updated" in sse_text
            assert "event: job_completed" in sse_text

            snapshot = client.get(f"/api/jobs/{job_id}").json()
            entries_by_key = {e["cite_key"]: e for e in snapshot["entries"]}
            assert entries_by_key["lora2021preprint"]["status"] == "PREPRINT_UPGRADE"
            assert (
                entries_by_key["lora2021preprint"]["candidates"][0]["bibtex_origin"]
                == "OpenReview Official"
            )
            assert entries_by_key["hallucinated2025paper"]["status"] == "SUSPECTED_HALLUCINATION"

            # 4. Manual paste-merge on the hallucinated/difficult entry (locking original cite_key!)
            scholar_pasted = """@inproceedings{external_scholar_wrong_key,
              title={Real Verified Replacement Paper on 3D Vision},
              author={Real, Author and Coauthor, Two},
              booktitle={Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition},
              pages={10-20},
              year={2025},
              abstract={Noise abstract that must be stripped}
            }"""
            pm_res = client.post(
                f"/api/jobs/{job_id}/entries/hallucinated2025paper/paste-merge",
                json={"pasted_bibtex": scholar_pasted},
            )
            assert pm_res.status_code == 200
            pm_entry = pm_res.json()
            assert pm_entry["cite_key"] == "hallucinated2025paper"
            assert pm_entry["status"] == "VERIFIED_CANONICAL"
            assert pm_entry["decision"] == "accept"
            merged_bib = pm_entry["candidates"][0]["canonical_bibtex"]
            assert merged_bib.startswith("@inproceedings{hallucinated2025paper,\n")
            assert "pages = {10--20}" in merged_bib
            assert "abstract =" not in merged_bib

            # 5. Export render (canonical vs compact) & verify lossless comments/@string retention
            render_res = client.post(
                "/api/export/render",
                json={
                    "job_id": job_id,
                    "style_mode": "compact",
                    "protect_title_case": True,
                    "decisions": {
                        "lora2021preprint": {"decision": "accept", "selected_candidate_idx": 0},
                        "hallucinated2025paper": {"decision": "keep_original"},
                    },
                },
            )
            assert render_res.status_code == 200
            rendered_bib = render_res.json()["output_bibtex"]
            assert "% === Header Comment ===" in rendered_bib
            assert '@string{icml = "ICML"}' in rendered_bib
            assert "% Keep this comment intact!" in rendered_bib
            assert "booktitle = {ICLR}" in rendered_bib
            assert "@inproceedings{lora2021preprint," in rendered_bib
            assert "Nonexistent Hyper-Dimensional Teleportation Network" in rendered_bib

            # 6. Write back to local .bib with automatic .bak backup
            local_bib = tmp_path / "overleaf_refs.bib"
            local_bib.write_text(SAMPLE_WORKFLOW_BIB, encoding="utf-8")
            write_res = client.post(
                "/api/export/write-local",
                json={
                    "job_id": job_id,
                    "style_mode": "canonical",
                    "protect_title_case": True,
                    "target_bib_path": str(local_bib),
                    "decisions": {
                        "lora2021preprint": {"decision": "accept", "selected_candidate_idx": 0},
                        "hallucinated2025paper": {"decision": "accept", "selected_candidate_idx": 0},
                    },
                },
            )
            assert write_res.status_code == 200
            w_json = write_res.json()
            bak_file = Path(w_json["backup_path"])
            assert bak_file.exists()
            assert bak_file.read_text(encoding="utf-8") == SAMPLE_WORKFLOW_BIB
            new_disk_text = local_bib.read_text(encoding="utf-8")
            assert "@inproceedings{lora2021preprint," in new_disk_text
            assert "@inproceedings{hallucinated2025paper," in new_disk_text

            # 7. Clear cache endpoint
            del_res = client.delete("/api/cache?scope=all")
            assert del_res.status_code == 200


def test_cli_check_fix_and_cache_commands(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BIBCANON_HOME", str(tmp_path / "cli_home"))
    bib_path = tmp_path / "paper_refs.bib"
    bib_path.write_text(SAMPLE_WORKFLOW_BIB, encoding="utf-8")
    report_path = tmp_path / "audit_report.json"

    with respx.mock(assert_all_called=False) as mock_router:
        _setup_upstream_mocks(mock_router)

        # 1. `bibcanon check` returns exit code 1 because `hallucinated2025paper` is SUSPECTED_HALLUCINATION
        res_check = runner.invoke(
            cli_app, ["check", str(bib_path), "--json", str(report_path)]
        )
        assert res_check.exit_code == 1
        assert "lora2021preprint" in res_check.stdout
        assert "hallucinated2025paper" in res_check.stdout
        assert report_path.exists()
        report_items = json.loads(report_path.read_text(encoding="utf-8"))
        assert len(report_items) == 2
        assert report_items[0]["status"] == VerificationStatus.PREPRINT_UPGRADE.value
        assert report_items[1]["status"] == VerificationStatus.SUSPECTED_HALLUCINATION.value

        # 2. `bibcanon fix --in-place` upgrades `lora2021preprint`, backs up .bak, and keeps `hallucinated2025paper` untouched
        res_fix = runner.invoke(cli_app, ["fix", str(bib_path), "--in-place"])
        assert res_fix.exit_code == 0
        assert "hallucinated2025paper" in res_fix.stdout  # listed under manual review!

        baks = list(tmp_path.glob("paper_refs.bib.bak.*"))
        assert len(baks) == 1
        assert baks[0].read_text(encoding="utf-8") == SAMPLE_WORKFLOW_BIB

        fixed_text = bib_path.read_text(encoding="utf-8")
        assert "@inproceedings{lora2021preprint," in fixed_text
        assert "International Conference on Learning Representations" in fixed_text
        # Hallucinated entry preserved verbatim!
        assert "Nonexistent Hyper-Dimensional Teleportation Network" in fixed_text

        # 3. `bibcanon cache stats` and `bibcanon cache clear`
        res_stats = runner.invoke(cli_app, ["cache", "stats"])
        assert res_stats.exit_code == 0
        assert "SQLite" in res_stats.stdout

        res_clear = runner.invoke(cli_app, ["cache", "clear"])
        assert res_clear.exit_code == 0
