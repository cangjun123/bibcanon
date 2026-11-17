"""Phase 5 end-to-end verification of static Web Workbench hosting and mixed .bib scenarios."""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import respx
from fastapi.testclient import TestClient

from bibcanon.models import AppConfig
from bibcanon.providers.base import RateLimitedHttpClient
from bibcanon.server.app import create_app
from bibcanon.storage.cache import BibCache


def _configure_comprehensive_mocks(router: respx.MockRouter) -> None:
    def _dblp_handler(req: httpx.Request) -> httpx.Response:
        q = req.url.params.get("q", "").lower()
        if "masked autoencoders" in q:
            return httpx.Response(
                200,
                json={
                    "result": {
                        "hits": {
                            "hit": [
                                {
                                    "info": {
                                        "title": "Masked Autoencoders Are Scalable Vision Learners.",
                                        "authors": {
                                            "author": [
                                                {"text": "Kaiming He"},
                                                {"text": "Xinlei Chen"},
                                                {"text": "Saining Xie"},
                                            ]
                                        },
                                        "venue": "CVPR",
                                        "year": "2022",
                                        "type": "Conference and Workshop Papers",
                                        "key": "conf/cvpr/HeCXLDG22",
                                        "ee": "https://openaccess.thecvf.com/content/CVPR2022/html/He_MAE_CVPR_2022_paper.html",
                                    }
                                },
                                {
                                    "info": {
                                        "title": "Masked Autoencoders Are Scalable Vision Learners.",
                                        "authors": {
                                            "author": [
                                                {"text": "Kaiming He"},
                                                {"text": "Xinlei Chen"},
                                                {"text": "Saining Xie"},
                                            ]
                                        },
                                        "venue": "IEEE Trans. Pattern Anal. Mach. Intell.",
                                        "year": "2024",
                                        "type": "Journal Articles",
                                        "key": "journals/pami/He24",
                                        "doi": "10.1109/TPAMI.2024.99999",
                                        "ee": "https://doi.org/10.1109/TPAMI.2024.99999",
                                    }
                                },
                            ]
                        }
                    }
                },
            )
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
                                        "key": "conf/iclr/Hu22",
                                        "ee": "https://openreview.net/forum?id=nZeVKeeFYf9",
                                    }
                                }
                            ]
                        }
                    }
                },
            )
        if "scaling vision transformers" in q:
            return httpx.Response(
                200,
                json={
                    "result": {
                        "hits": {
                            "hit": [
                                {
                                    "info": {
                                        "title": "Scaling Vision Transformers.",
                                        "authors": {
                                            "author": [
                                                {"text": "Alice Smith"},
                                                {"text": "Charlie Bob"},
                                            ]
                                        },
                                        "venue": "ICML",
                                        "year": "2024",
                                        "type": "Conference and Workshop Papers",
                                        "key": "conf/icml/SmithB24",
                                        "ee": "https://proceedings.mlr.press/v235/smith24a.html",
                                    }
                                }
                            ]
                        }
                    }
                },
            )
        return httpx.Response(200, json={"result": {"hits": {}}})

    def _arxiv_handler(req: httpx.Request) -> httpx.Response:
        id_list = req.url.params.get("id_list", "")
        sq = req.url.params.get("search_query", "").lower()
        if "2304.02643" in id_list or "segment anything" in sq:
            return httpx.Response(
                200,
                text="""<?xml version="1.0" encoding="UTF-8"?>
                <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
                  <entry>
                    <id>http://arxiv.org/abs/2304.02643v1</id>
                    <published>2023-04-05T00:00:00Z</published>
                    <title>Segment Anything</title>
                    <author><name>Alexander Kirillov</name></author>
                    <author><name>Eric Mintun</name></author>
                    <arxiv:primary_category term="cs.CV"/>
                  </entry>
                </feed>""",
            )
        if "2106.09685" in id_list:
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
        if "2111.06377" in id_list:
            return httpx.Response(
                200,
                text="""<?xml version="1.0" encoding="UTF-8"?>
                <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
                  <entry>
                    <id>http://arxiv.org/abs/2111.06377v1</id>
                    <published>2021-11-11T00:00:00Z</published>
                    <title>Masked Autoencoders Are Scalable Vision Learners</title>
                    <author><name>Kaiming He</name></author>
                    <author><name>Xinlei Chen</name></author>
                    <arxiv:primary_category term="cs.CV"/>
                  </entry>
                </feed>""",
            )
        return httpx.Response(
            200,
            text='<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>',
        )

    router.get("https://dblp.org/search/publ/api").mock(side_effect=_dblp_handler)
    router.get("https://export.arxiv.org/api/query").mock(side_effect=_arxiv_handler)
    router.get("https://api.crossref.org/works").mock(
        return_value=httpx.Response(200, json={"message": {"items": []}})
    )
    router.get("https://api.openalex.org/works").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    router.get("https://api.semanticscholar.org/graph/v1/paper/search").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    # Publisher adapters
    router.get(
        "https://openaccess.thecvf.com/content/CVPR2022/html/He_MAE_CVPR_2022_paper.html"
    ).mock(
        return_value=httpx.Response(
            200,
            text="""<html><body><div class="bibref">
            @InProceedings{He_2022_CVPR,<br>
            author = {He, Kaiming and Chen, Xinlei and Xie, Saining},<br>
            title = {Masked Autoencoders Are Scalable Vision Learners},<br>
            booktitle = {Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)},<br>
            month = {June},<br>
            year = {2022},<br>
            pages = {16000-16009}<br>
            }</div></body></html>""",
        )
    )
    router.get("https://doi.org/10.1109/TPAMI.2024.99999").mock(
        return_value=httpx.Response(
            200,
            text="""@article{He_2024_TPAMI,
            author={He, Kaiming and Chen, Xinlei and Xie, Saining},
            title={Masked Autoencoders Are Scalable Vision Learners},
            journal={IEEE Transactions on Pattern Analysis and Machine Intelligence},
            year={2024},
            volume={46},
            pages={100-115},
            doi={10.1109/TPAMI.2024.99999}
            }""",
        )
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
                                author={Edward J. Hu and Yelong Shen},
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
    router.get("https://arxiv.org/bibtex/2304.02643").mock(
        return_value=httpx.Response(
            200,
            text="""@misc{kirillov2023segment,
            title={Segment Anything},
            author={Alexander Kirillov and Eric Mintun},
            year={2023},
            eprint={2304.02643},
            archivePrefix={arXiv},
            primaryClass={cs.CV},
            url={https://arxiv.org/abs/2304.02643}
            }""",
        )
    )
    router.get("https://arxiv.org/bibtex/2111.06377").mock(
        return_value=httpx.Response(
            200,
            text="""@misc{he2021masked,
            title={Masked Autoencoders Are Scalable Vision Learners},
            author={Kaiming He and Xinlei Chen},
            year={2021},
            eprint={2111.06377},
            archivePrefix={arXiv},
            primaryClass={cs.CV},
            url={https://arxiv.org/abs/2111.06377}
            }""",
        )
    )
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
    router.get("https://proceedings.mlr.press/v235/smith24a.html").mock(
        return_value=httpx.Response(
            200,
            text="""<html><body><code id="bibtex">@InProceedings{pmlr-v235-smith24a,
            title = {Scaling Vision Transformers},
            author = {Smith, Alice and Bob, Charlie},
            booktitle = {Proceedings of the 41st International Conference on Machine Learning},
            pages = {1000--1012},
            year = {2024},
            volume = {235},
            series = {Proceedings of Machine Learning Research},
            publisher = {PMLR},
            url = {https://proceedings.mlr.press/v235/smith24a.html}
            }</code></body></html>""",
        )
    )


def test_phase5_bundled_frontend_and_comprehensive_bib_workflow(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("BIBCANON_HOME", str(tmp_path / "e2e_home"))
    cache = BibCache(db_path=tmp_path / "e2e_home" / "cache.sqlite3")
    fixture_bib = Path(__file__).parent / "fixtures" / "comprehensive_sample.bib"
    assert fixture_bib.exists()

    def fast_client_factory(cfg: AppConfig) -> RateLimitedHttpClient:
        return RateLimitedHttpClient(config=cfg, enable_rate_sleep=False, backoff_base=0.0)

    app = create_app(
        initial_bib_path=str(fixture_bib),
        cache=cache,
        client_factory=fast_client_factory,
    )

    with respx.mock(assert_all_called=False) as mock_router:
        _configure_comprehensive_mocks(mock_router)

        with TestClient(app) as client:
            # 1. Verify bundled React frontend index.html & JS/CSS assets are hosted on single port
            index_res = client.get("/")
            assert index_res.status_code == 200
            assert "bibcanon" in index_res.text
            js_match = re.search(r'src="(/assets/index-[^"]+\.js)"', index_res.text)
            css_match = re.search(r'href="(/assets/index-[^"]+\.css)"', index_res.text)
            assert js_match is not None and css_match is not None
            assert client.get(js_match.group(1)).status_code == 200
            assert client.get(css_match.group(1)).status_code == 200

            # 2. Verify /api/bootstrap exposes initial_bib_path from `bibcanon serve <file.bib>`
            boot = client.get("/api/bootstrap").json()
            assert boot["initial_bib_path"] == str(fixture_bib)

            # 3. Create job from comprehensive_sample.bib & stream SSE to completion
            job_res = client.post(
                "/api/jobs",
                json={"bib_path": str(fixture_bib), "force_refresh": True},
            )
            assert job_res.status_code == 200
            job_id = job_res.json()["job_id"]
            assert job_res.json()["total_entries"] == 6

            sse_res = client.get(f"/api/jobs/{job_id}/stream")
            assert sse_res.status_code == 200
            assert "event: job_completed" in sse_res.text

            final_entries = {
                e["cite_key"]: e for e in client.get(f"/api/jobs/{job_id}").json()["entries"]
            }

            # Scenario 1: CVPR + TPAMI dual version -> respects CVPR as candidates[0], TPAMI as candidates[1]
            mae_conf = final_entries["he2022mae_conf"]
            assert mae_conf["status"] == "VERIFIED_CANONICAL"
            assert mae_conf["candidates"][0]["bibtex_origin"] == "CVF Open Access"
            assert mae_conf["candidates"][1]["bibtex_origin"] == "DOI Official (IEEE)"
            assert any(
                w["code"] == "JOURNAL_EXTENSION_AVAILABLE" for w in mae_conf["warnings"]
            )

            # Scenario 2: Duplicate entry cross-detected & preprint auto-upgraded to TPAMI!
            mae_dup = final_entries["mae_duplicate_entry"]
            assert mae_dup["status"] == "PREPRINT_UPGRADE"
            assert mae_dup["candidates"][0]["canonical_venue_id"] == "TPAMI"
            assert any(w["code"] == "DUPLICATE_IN_BIB" for w in mae_dup["warnings"])
            assert any(w["code"] == "DUPLICATE_IN_BIB" for w in mae_conf["warnings"])

            # Scenario 3: LoRA arXiv upgraded to OpenReview ICLR
            assert final_entries["hu2021lora"]["status"] == "PREPRINT_UPGRADE"
            assert (
                final_entries["hu2021lora"]["candidates"][0]["bibtex_origin"]
                == "OpenReview Official"
            )

            # Scenario 4: Pure arXiv preprint -> Official @misc
            sam = final_entries["kirillov2023sam"]
            assert sam["status"] == "VERIFIED_PREPRINT_ONLY"
            assert sam["candidates"][0]["canonical_bibtex"].startswith(
                "@misc{kirillov2023sam,\n"
            )
            assert "archivePrefix = {arXiv}" in sam["candidates"][0]["canonical_bibtex"]

            # Scenario 5: Standard ICML paper via PMLR
            vit = final_entries["smith2024vit"]
            assert vit["status"] == "VERIFIED_CANONICAL"
            assert vit["candidates"][0]["bibtex_origin"] == "PMLR Official"

            # Scenario 6: Hallucinated paper
            fake = final_entries["ghost2025fake"]
            assert fake["status"] == "SUSPECTED_HALLUCINATION"
