"""Phase 3 deterministic tests for all 10 publisher BibTeX classes, router, and async pipeline."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from bibcanon.adapters.router import enrich_candidate_with_publisher_bibtex
from bibcanon.core.bib_parser import parse_bib_content
from bibcanon.core.pipeline import run_verification_pipeline
from bibcanon.models import AppConfig, CandidateRecord, VerificationStatus
from bibcanon.providers.base import RateLimitedHttpClient
from bibcanon.storage.cache import BibCache


@pytest.mark.asyncio
async def test_all_ten_publisher_adapters_verbatim_and_cite_key_lock(tmp_path: Path) -> None:
    cache = BibCache(db_path=tmp_path / "cvf_test.sqlite3")

    # 1. CVPR via CVF Open Access (including ?day=all ToC lookup when no direct HTML link!)
    cvf_toc_html = """
    <html><body>
      <dt class="ptitle"><a href="content/CVPR2024/html/Doe_3D_Vision_CVPR_2024_paper.html">3D Vision Foundation Models</a></dt>
    </body></html>
    """
    cvf_paper_html = """
    <html><body>
      <div class="bibref">
        @InProceedings{Doe_2024_CVPR,<br>
        author = {Doe, Jane and Roe, Richard},<br>
        title = {3D Vision Foundation Models},<br>
        booktitle = {Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)},<br>
        month = {June},<br>
        year = {2024},<br>
        pages = {1200-1210}<br>
        }
      </div>
    </body></html>
    """

    # 2. ICML via PMLR (#bibtex with editor, volume, series, pdf, url, plus abstract noise to strip)
    pmlr_html = """
    <html><body>
      <code id="bibtex">@InProceedings{pmlr-v235-smith24a,
  title = \t {Scaling Vision Transformers},
  author =       {Smith, Alice and Bob, Charlie},
  booktitle = \t {Proceedings of the 41st International Conference on Machine Learning},
  pages = \t {45001--45015},
  year = \t {2024},
  editor = \t {Salakhutdinov, Ruslan and Kolter, Zico},
  volume = \t {235},
  series = \t {Proceedings of Machine Learning Research},
  month = \t {21--27 Jul},
  publisher =    {PMLR},
  pdf = \t {https://raw.githubusercontent.com/mlresearch/v235/main/assets/smith24a/smith24a.pdf},
  url = \t {https://proceedings.mlr.press/v235/smith24a.html},
  abstract = \t {Should be stripped by noise blacklist.}
}</code>
    </body></html>
    """

    # 3. ICLR via OpenReview API v2
    openreview_v2_json = {
        "notes": [
            {
                "id": "abc123iclr",
                "content": {
                    "venue": {"value": "ICLR 2024 spotlight"},
                    "_bibtex": {
                        "value": """@inproceedings{
lee2024lora,
title={LoRA-Next for {ViT} Adaptation},
author={David Lee and Sarah Kim},
booktitle={The Twelfth International Conference on Learning Representations},
year={2024},
url={https://openreview.net/forum?id=abc123iclr}
}"""
                    },
                },
            }
        ]
    }

    # 4. NeurIPS via NeurIPS Proceedings HTML -> Bibtex .bib link
    neurips_page_html = """
    <html><body>
      <a href="/paper_files/paper/2023/file/9999-Bibtex.bib">Bibtex</a>
    </body></html>
    """
    neurips_bib = """@inproceedings{NEURIPS2023_9999,
 author = {Wang, Wei and Chen, Lin},
 booktitle = {Advances in Neural Information Processing Systems},
 editor = {A. Oh and T. Naumann},
 pages = {10100--10112},
 publisher = {Curran Associates, Inc.},
 title = {Diffusion Models Beat GANs Revisited},
 url = {https://proceedings.neurips.cc/paper_files/paper/2023/file/9999-Paper-Conference.pdf},
 volume = {36},
 year = {2023}
}"""

    # 5. ACL via ACL Anthology .bib
    acl_bib = """@inproceedings{zhang-etal-2024-multimodal,
    title = "Multimodal {LLM} Reasoning",
    author = "Zhang, San and Li, Si",
    editor = "Ku, Lun-Wei",
    booktitle = "Proceedings of the 62nd Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers)",
    month = aug,
    year = "2024",
    address = "Bangkok, Thailand",
    publisher = "Association for Computational Linguistics",
    url = "https://aclanthology.org/2024.acl-long.10/",
    doi = "10.18653/v1/2024.acl-long.10",
    pages = "150--165"
}"""

    # 6. IEEE TPAMI via DOI Content Negotiation (with missing pages filled from Crossref extra)
    tpami_bib = """@article{He_2024,
   title={Masked Autoencoders Are Scalable Vision Learners},
   volume={46},
   ISSN={1939-3539},
   url={http://dx.doi.org/10.1109/TPAMI.2024.11111},
   DOI={10.1109/tpami.2024.11111},
   number={5},
   journal={IEEE Transactions on Pattern Analysis and Machine Intelligence},
   publisher={Institute of Electrical and Electronics Engineers (IEEE)},
   author={He, Kaiming and Chen, Xinlei},
   year={2024},
   month=may
}"""

    # 7. ACM MM via DOI Content Negotiation (retaining articleno, numpages, location, isbn)
    acm_bib = """@inproceedings{10.1145/3581783.3611700,
author = {Zhao, Ming and Sun, Hao},
title = {Neural Audio-Visual Rendering},
year = {2023},
isbn = {9798400701085},
publisher = {Association for Computing Machinery},
address = {New York, NY, USA},
url = {https://doi.org/10.1145/3581783.3611700},
doi = {10.1145/3581783.3611700},
booktitle = {Proceedings of the 31st ACM International Conference on Multimedia},
articleno = {88},
numpages = {9},
location = {Ottawa ON, Canada},
series = {MM '23}
}"""

    # 8. ECCV via Springer LNCS DOI Content Negotiation (MUST repair @inbook -> @inproceedings!)
    eccv_springer_bib = """@inbook{Carion_2020,
   title={End-to-End Object Detection with Transformers},
   ISBN={9783030584528},
   ISSN={1611-3349},
   url={http://dx.doi.org/10.1007/978-3-030-58452-8_13},
   DOI={10.1007/978-3-030-58452-8_13},
   booktitle={Computer Vision – ECCV 2020},
   series={Lecture Notes in Computer Science},
   publisher={Springer International Publishing},
   author={Carion, Nicolas and Massa, Francisco},
   year={2020},
   pages={213–229}
}"""

    # 9. AAAI via DOI Content Negotiation (10.1609/...)
    aaai_bib = """@article{Liu_2024_AAAI,
   title={Fast Graph Representation &amp; Reasoning},
   volume={38},
   url={https://ojs.aaai.org/index.php/AAAI/article/view/28000},
   DOI={10.1609/aaai.v38i10.28000},
   number={10},
   journal={Proceedings of the AAAI Conference on Artificial Intelligence},
   author={Liu, Yang and Wu, Bo},
   year={2024},
   month={Mar.},
   pages={11000-11008}
}"""

    # 10. Pure arXiv Preprint via Official https://arxiv.org/bibtex/{id} @misc
    arxiv_official_bib = """@misc{kirillov2023segment,
      title={Segment Anything}, 
      author={Alexander Kirillov and Eric Mintun and Nikhila Ravi},
      year={2023},
      eprint={2304.02643},
      archivePrefix={arXiv},
      primaryClass={cs.CV},
      url={https://arxiv.org/abs/2304.02643}, 
}"""

    with respx.mock(assert_all_called=True) as router:
        router.get("https://openaccess.thecvf.com/CVPR2024?day=all").mock(
            return_value=httpx.Response(200, text=cvf_toc_html)
        )
        router.get(
            "https://openaccess.thecvf.com/content/CVPR2024/html/Doe_3D_Vision_CVPR_2024_paper.html"
        ).mock(return_value=httpx.Response(200, text=cvf_paper_html))

        router.get("https://proceedings.mlr.press/v235/smith24a.html").mock(
            return_value=httpx.Response(200, text=pmlr_html)
        )
        router.get("https://api2.openreview.net/notes").mock(
            return_value=httpx.Response(200, json=openreview_v2_json)
        )
        router.get(
            "https://proceedings.neurips.cc/paper_files/paper/2023/hash/9999-Abstract-Conference.html"
        ).mock(return_value=httpx.Response(200, text=neurips_page_html))
        router.get(
            "https://proceedings.neurips.cc/paper_files/paper/2023/file/9999-Bibtex.bib"
        ).mock(return_value=httpx.Response(200, text=neurips_bib))
        router.get("https://aclanthology.org/2024.acl-long.10.bib").mock(
            return_value=httpx.Response(200, text=acl_bib)
        )
        router.get("https://doi.org/10.1109/TPAMI.2024.11111").mock(
            return_value=httpx.Response(200, text=tpami_bib)
        )
        router.get("https://doi.org/10.1145/3581783.3611700").mock(
            return_value=httpx.Response(200, text=acm_bib)
        )
        router.get("https://doi.org/10.1007/978-3-030-58452-8_13").mock(
            return_value=httpx.Response(200, text=eccv_springer_bib)
        )
        router.get("https://doi.org/10.1609/aaai.v38i10.28000").mock(
            return_value=httpx.Response(200, text=aaai_bib)
        )
        router.get("https://arxiv.org/bibtex/2304.02643").mock(
            return_value=httpx.Response(200, text=arxiv_official_bib)
        )

        cfg = AppConfig()
        async with RateLimitedHttpClient(config=cfg, enable_rate_sleep=False, backoff_base=0.0) as client:
            # 1. CVPR (CVF ToC lookup)
            c_cvpr = await enrich_candidate_with_publisher_bibtex(
                client,
                CandidateRecord(
                    source_discovery="crossref",
                    venue_tier="MAIN_CONF",
                    canonical_venue_id="CVPR",
                    matched_title="3D Vision Foundation Models",
                    matched_year=2024,
                    doi="10.1109/CVPR.2024.001",
                ),
                cite_key="my_cvpr_key",
                cache=cache,
                config=cfg,
            )
            assert c_cvpr.bibtex_origin == "CVF Open Access"
            assert c_cvpr.canonical_bibtex.startswith("@inproceedings{my_cvpr_key,\n")
            assert "pages = {1200--1210}" in c_cvpr.canonical_bibtex
            assert "month = {June}" in c_cvpr.canonical_bibtex

            # 2. ICML (PMLR)
            c_icml = await enrich_candidate_with_publisher_bibtex(
                client,
                CandidateRecord(
                    source_discovery="dblp",
                    venue_tier="MAIN_CONF",
                    canonical_venue_id="ICML",
                    matched_title="Scaling Vision Transformers",
                    matched_year=2024,
                    ee_urls=["https://proceedings.mlr.press/v235/smith24a.html"],
                ),
                cite_key="my_icml_key",
                config=cfg,
            )
            assert c_icml.bibtex_origin == "PMLR Official"
            assert c_icml.canonical_bibtex.startswith("@inproceedings{my_icml_key,\n")
            assert "editor = {Salakhutdinov, Ruslan and Kolter, Zico}" in c_icml.canonical_bibtex
            assert "pdf = {https://raw.githubusercontent.com/" in c_icml.canonical_bibtex
            assert "abstract =" not in c_icml.canonical_bibtex

            # 3. ICLR (OpenReview)
            c_iclr = await enrich_candidate_with_publisher_bibtex(
                client,
                CandidateRecord(
                    source_discovery="dblp",
                    venue_tier="MAIN_CONF",
                    canonical_venue_id="ICLR",
                    matched_title="LoRA-Next for ViT Adaptation",
                    matched_year=2024,
                    ee_urls=["https://openreview.net/forum?id=abc123iclr"],
                ),
                cite_key="my_iclr_key",
                config=cfg,
            )
            assert c_iclr.bibtex_origin == "OpenReview Official"
            assert c_iclr.canonical_bibtex.startswith("@inproceedings{my_iclr_key,\n")
            assert "url = {https://openreview.net/forum?id=abc123iclr}" in c_iclr.canonical_bibtex

            # 4. NeurIPS (NeurIPS Proceedings)
            c_nips = await enrich_candidate_with_publisher_bibtex(
                client,
                CandidateRecord(
                    source_discovery="dblp",
                    venue_tier="MAIN_CONF",
                    canonical_venue_id="NeurIPS",
                    matched_title="Diffusion Models Beat GANs Revisited",
                    matched_year=2023,
                    ee_urls=[
                        "https://proceedings.neurips.cc/paper_files/paper/2023/hash/9999-Abstract-Conference.html"
                    ],
                ),
                cite_key="my_neurips_key",
                config=cfg,
            )
            assert c_nips.bibtex_origin == "NeurIPS Proceedings"
            assert c_nips.canonical_bibtex.startswith("@inproceedings{my_neurips_key,\n")
            assert "publisher = {Curran Associates, Inc.}" in c_nips.canonical_bibtex
            assert "volume = {36}" in c_nips.canonical_bibtex

            # 5. ACL (ACL Anthology)
            c_acl = await enrich_candidate_with_publisher_bibtex(
                client,
                CandidateRecord(
                    source_discovery="crossref",
                    venue_tier="MAIN_CONF",
                    canonical_venue_id="ACL",
                    matched_title="Multimodal LLM Reasoning",
                    matched_year=2024,
                    doi="10.18653/v1/2024.acl-long.10",
                ),
                cite_key="my_acl_key",
                config=cfg,
            )
            assert c_acl.bibtex_origin == "ACL Anthology"
            assert c_acl.canonical_bibtex.startswith("@inproceedings{my_acl_key,\n")
            assert "address = {Bangkok, Thailand}" in c_acl.canonical_bibtex

            # 6. IEEE TPAMI (DOI + missing page completion from Crossref JSON)
            c_tpami = await enrich_candidate_with_publisher_bibtex(
                client,
                CandidateRecord(
                    source_discovery="crossref",
                    venue_tier="JOURNAL",
                    canonical_venue_id="TPAMI",
                    matched_title="Masked Autoencoders Are Scalable Vision Learners",
                    matched_year=2024,
                    doi="10.1109/TPAMI.2024.11111",
                    crossref_extra={"page": "3100-3116"},
                ),
                cite_key="my_tpami_key",
                config=cfg,
            )
            assert c_tpami.bibtex_origin == "DOI Official (IEEE)"
            assert c_tpami.canonical_bibtex.startswith("@article{my_tpami_key,\n")
            assert "pages = {3100--3116}" in c_tpami.canonical_bibtex
            assert "url = {https://doi.org/10.1109/TPAMI.2024.11111}" in c_tpami.canonical_bibtex

            # 7. ACM MM (DOI retaining articleno & numpages)
            c_acm = await enrich_candidate_with_publisher_bibtex(
                client,
                CandidateRecord(
                    source_discovery="crossref",
                    venue_tier="MAIN_CONF",
                    canonical_venue_id="ACM MM",
                    matched_title="Neural Audio-Visual Rendering",
                    matched_year=2023,
                    doi="10.1145/3581783.3611700",
                ),
                cite_key="my_acm_key",
                config=cfg,
            )
            assert c_acm.bibtex_origin == "DOI Official (ACM)"
            assert c_acm.canonical_bibtex.startswith("@inproceedings{my_acm_key,\n")
            assert "articleno = {88}" in c_acm.canonical_bibtex
            assert "numpages = {9}" in c_acm.canonical_bibtex

            # 8. ECCV (Springer LNCS DOI repairing @inbook -> @inproceedings!)
            c_eccv = await enrich_candidate_with_publisher_bibtex(
                client,
                CandidateRecord(
                    source_discovery="dblp",
                    venue_tier="MAIN_CONF",
                    canonical_venue_id="ECCV",
                    dblp_type="Conference and Workshop Papers",
                    matched_title="End-to-End Object Detection with Transformers",
                    matched_year=2020,
                    doi="10.1007/978-3-030-58452-8_13",
                ),
                cite_key="my_eccv_key",
                config=cfg,
            )
            assert c_eccv.bibtex_origin == "DOI Official (Springer)"
            assert c_eccv.entry_type == "inproceedings"
            assert c_eccv.canonical_bibtex.startswith("@inproceedings{my_eccv_key,\n")
            assert "pages = {213--229}" in c_eccv.canonical_bibtex

            # 9. AAAI (DOI + &amp; -> \& escaping)
            c_aaai = await enrich_candidate_with_publisher_bibtex(
                client,
                CandidateRecord(
                    source_discovery="crossref",
                    venue_tier="MAIN_CONF",
                    canonical_venue_id="AAAI",
                    matched_title="Fast Graph Representation & Reasoning",
                    matched_year=2024,
                    doi="10.1609/aaai.v38i10.28000",
                ),
                cite_key="my_aaai_key",
                config=cfg,
            )
            assert c_aaai.bibtex_origin == "DOI Official (AAAI)"
            assert c_aaai.canonical_bibtex.startswith("@article{my_aaai_key,\n")
            assert r"title = {Fast Graph Representation \& Reasoning}" in c_aaai.canonical_bibtex

            # 10. Pure arXiv Preprint (Official @misc with eprint, archivePrefix, primaryClass, url)
            c_arxiv = await enrich_candidate_with_publisher_bibtex(
                client,
                CandidateRecord(
                    source_discovery="arxiv",
                    venue_tier="PREPRINT",
                    matched_title="Segment Anything",
                    matched_year=2023,
                    arxiv_id="2304.02643",
                ),
                cite_key="my_sam_key",
                config=cfg,
            )
            assert c_arxiv.bibtex_origin == "arXiv Official"
            assert c_arxiv.canonical_bibtex.startswith("@misc{my_sam_key,\n")
            assert "eprint = {2304.02643}" in c_arxiv.canonical_bibtex
            assert "archivePrefix = {arXiv}" in c_arxiv.canonical_bibtex
            assert "primaryClass = {cs.CV}" in c_arxiv.canonical_bibtex
            assert "url = {https://arxiv.org/abs/2304.02643}" in c_arxiv.canonical_bibtex


@pytest.mark.asyncio
async def test_pipeline_end_to_end_and_cache_rekeying(tmp_path: Path) -> None:
    cache = BibCache(db_path=tmp_path / "pipe.sqlite3")
    bib_input = """
@article{sam_first_key,
  title={Segment Anything},
  author={Kirillov, Alexander and others},
  journal={arXiv preprint arXiv:2304.02643},
  year={2023}
}
"""
    arxiv_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
      <entry>
        <id>http://arxiv.org/abs/2304.02643v1</id>
        <published>2023-04-05T00:00:00Z</published>
        <title>Segment Anything</title>
        <author><name>Alexander Kirillov</name></author>
        <author><name>Eric Mintun</name></author>
        <arxiv:primary_category term="cs.CV"/>
      </entry>
    </feed>"""

    arxiv_bib = """@misc{kirillov2023segment,
      title={Segment Anything},
      author={Alexander Kirillov and Eric Mintun},
      year={2023},
      eprint={2304.02643},
      archivePrefix={arXiv},
      primaryClass={cs.CV},
      url={https://arxiv.org/abs/2304.02643}
    }"""

    with respx.mock(assert_all_called=False) as router:
        router.get("https://dblp.org/search/publ/api").mock(
            return_value=httpx.Response(200, json={"result": {"hits": {}}})
        )
        router.get("https://api.crossref.org/works").mock(
            return_value=httpx.Response(200, json={"message": {"items": []}})
        )
        router.get("https://api.openalex.org/works").mock(
            return_value=httpx.Response(200, json={"results": []})
        )
        router.get("https://api.semanticscholar.org/graph/v1/paper/search").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        router.get("https://export.arxiv.org/api/query").mock(
            return_value=httpx.Response(200, text=arxiv_xml)
        )
        router.get("https://arxiv.org/bibtex/2304.02643").mock(
            return_value=httpx.Response(200, text=arxiv_bib)
        )

        cfg = AppConfig()
        doc1 = parse_bib_content(bib_input)
        progress_events: list[tuple[str, int, int]] = []

        async with RateLimitedHttpClient(config=cfg, enable_rate_sleep=False, backoff_base=0.0) as client:
            res1 = await run_verification_pipeline(
                doc1,
                config=cfg,
                cache=cache,
                client=client,
                on_entry_updated=lambda e, c, t: progress_events.append((e.cite_key, c, t)),
            )

        assert len(res1) == 1
        assert progress_events == [("sam_first_key", 1, 1)]
        assert res1[0].status == VerificationStatus.VERIFIED_PREPRINT_ONLY
        assert res1[0].candidates[0].canonical_bibtex.startswith("@misc{sam_first_key,\n")

        # Second run with a DIFFERENT cite_key hitting SQLite cache (with ZERO network calls allowed!)
    with respx.mock(assert_all_called=True):
        bib_input_2 = bib_input.replace("sam_first_key", "kirillov2023_custom_key")
        doc2 = parse_bib_content(bib_input_2)
        async with RateLimitedHttpClient(config=cfg, enable_rate_sleep=False, backoff_base=0.0) as client2:
            res2 = await run_verification_pipeline(doc2, config=cfg, cache=cache, client=client2)
        assert res2[0].cite_key == "kirillov2023_custom_key"
        assert res2[0].candidates[0].canonical_bibtex.startswith(
            "@misc{kirillov2023_custom_key,\n"
        )
