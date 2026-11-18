"""Phase 2 deterministic unit tests for SQLite cache, discovery providers, scorer, and election."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from bibcanon.core.bib_parser import parse_bib_content
from bibcanon.core.normalizer import extract_entry_features
from bibcanon.core.scorer import elect_and_classify
from bibcanon.models import (
    AppConfig,
    CandidateRecord,
    VerificationStatus,
    WarningCode,
)
from bibcanon.providers.arxiv import lookup_arxiv_by_id, search_arxiv_by_title
from bibcanon.providers.base import RateLimitedHttpClient, UpstreamNetworkError
from bibcanon.providers.crossref import lookup_crossref_doi, search_crossref
from bibcanon.providers.dblp import search_dblp
from bibcanon.providers.openalex import search_openalex
from bibcanon.providers.semantic_scholar import search_semantic_scholar
from bibcanon.storage.cache import BibCache


@pytest.mark.asyncio
async def test_dblp_single_vs_multi_author_and_ee_and_suffix_stripping() -> None:
    mock_payload = {
        "result": {
            "hits": {
                "hit": [
                    {
                        "info": {
                            "title": "Single Author Vision Paper.",
                            # Single author is a dict (NOT list) in DBLP JSON!
                            "authors": {"author": {"@pid": "12/34", "text": "Yang Liu 0001"}},
                            "venue": "CVPR",
                            "year": "2024",
                            "type": "Conference and Workshop Papers",
                            "key": "conf/cvpr/Liu24",
                            # Single ee is a str (NOT list) in DBLP JSON!
                            "ee": "https://openaccess.thecvf.com/content/CVPR2024/html/Liu_Single_CVPR_2024_paper.html",
                        }
                    },
                    {
                        "info": {
                            "title": "Multi Author Vision Paper.",
                            # Multiple authors is a list[dict]
                            "authors": {
                                "author": [
                                    {"text": "Kaiming He"},
                                    {"text": "Xiangyu Zhang 0002"},
                                ]
                            },
                            "venue": "CoRR",
                            "volume": "abs/2401.12345",
                            "year": "2024",
                            "type": "Informal and Other Publications",
                            "key": "journals/corr/abs-2401-12345",
                            # Multiple ee is a list[str]
                            "ee": [
                                "https://doi.org/10.48550/arXiv.2401.12345",
                                "https://arxiv.org/abs/2401.12345",
                            ],
                        }
                    },
                ]
            }
        }
    }

    with respx.mock(assert_all_called=True) as router:
        router.get("https://dblp.org/search/publ/api").mock(
            return_value=httpx.Response(200, json=mock_payload)
        )
        async with RateLimitedHttpClient(enable_rate_sleep=False, backoff_base=0.0) as client:
            cands = await search_dblp(client, "Single Author Vision Paper")

    assert len(cands) == 2
    assert cands[0].matched_authors == ["Yang Liu"]
    assert cands[0].ee_urls == [
        "https://openaccess.thecvf.com/content/CVPR2024/html/Liu_Single_CVPR_2024_paper.html"
    ]
    assert cands[0].venue_tier == "MAIN_CONF"
    assert cands[0].canonical_venue_id == "CVPR"
    assert cands[0].matched_title == "Single Author Vision Paper"

    assert cands[1].matched_authors == ["Kaiming He", "Xiangyu Zhang"]
    assert len(cands[1].ee_urls) == 2
    assert cands[1].venue_tier == "PREPRINT"
    assert cands[1].arxiv_id == "2401.12345"
    assert cands[1].doi is None  # 10.48550/arXiv.* must NOT be treated as formal DOI


def test_respect_original_venue_vs_preprint_auto_upgrade() -> None:
    # Shared upstream candidate pool containing:
    # 1. CoRR preprint (2021)
    # 2. CVPRW workshop (2022)
    # 3. CVPR main conference (2022)
    # 4. TPAMI journal extension (2024)
    def make_pool() -> list[CandidateRecord]:
        return [
            CandidateRecord(
                source_discovery="dblp",
                venue_tier="PREPRINT",
                matched_title="Masked Autoencoders Are Scalable Vision Learners",
                matched_authors=["Kaiming He", "Xinlei Chen", "Saining Xie"],
                matched_year=2021,
                matched_venue="CoRR",
                arxiv_id="2111.06377",
            ),
            CandidateRecord(
                source_discovery="dblp",
                venue_tier="MAIN_CONF",  # Even if upstream mislabeled, refine_candidate_tier must enforce WORKSHOP!
                matched_title="Masked Autoencoders Are Scalable Vision Learners",
                matched_authors=["Kaiming He", "Xinlei Chen", "Saining Xie"],
                matched_year=2022,
                matched_venue="CVPR Workshops (CVPRW)",
                doi="10.1109/CVPRW.2022.001",
            ),
            CandidateRecord(
                source_discovery="dblp",
                venue_tier="MAIN_CONF",
                canonical_venue_id="CVPR",
                matched_title="Masked Autoencoders Are Scalable Vision Learners",
                matched_authors=["Kaiming He", "Xinlei Chen", "Saining Xie"],
                matched_year=2022,
                matched_venue="CVPR",
                doi="10.1109/CVPR52688.2022.01553",
            ),
            CandidateRecord(
                source_discovery="crossref",
                venue_tier="JOURNAL",
                canonical_venue_id="TPAMI",
                matched_title="Masked Autoencoders Are Scalable Vision Learners",
                matched_authors=["Kaiming He", "Xinlei Chen", "Saining Xie"],
                matched_year=2024,
                matched_venue="IEEE Transactions on Pattern Analysis and Machine Intelligence",
                doi="10.1109/TPAMI.2024.99999",
            ),
        ]

    # Case A: Original .bib explicitly cites CVPR -> MUST keep CVPR as candidates[0] and list TPAMI at candidates[1]
    bib_cvpr = """@inproceedings{he2022mae,
      title={Masked Autoencoders Are Scalable Vision Learners},
      author={He, Kaiming and Chen, Xinlei and Xie, Saining},
      booktitle={CVPR},
      year={2022}
    }"""
    feat_cvpr = extract_entry_features(parse_bib_content(bib_cvpr).entries[0])
    outcome_cvpr = elect_and_classify(feat_cvpr, make_pool())

    assert outcome_cvpr.status == VerificationStatus.VERIFIED_CANONICAL
    assert outcome_cvpr.decision == "accept"
    assert outcome_cvpr.candidates[0].canonical_venue_id == "CVPR"
    assert outcome_cvpr.candidates[1].canonical_venue_id == "TPAMI"
    assert any(
        w.code == WarningCode.JOURNAL_EXTENSION_AVAILABLE and w.severity == "info"
        for w in outcome_cvpr.warnings
    )
    # Workshop candidate must be strictly classified as WORKSHOP
    workshop_cands = [c for c in outcome_cvpr.candidates if "CVPRW" in (c.matched_venue or "")]
    assert workshop_cands and workshop_cands[0].venue_tier == "WORKSHOP"

    # Case B: Original .bib is an arXiv preprint -> MUST auto-upgrade to highest formal tier (TPAMI > CVPR > CVPRW > CoRR)
    bib_arxiv = """@article{he2021mae,
      title={Masked Autoencoders Are Scalable Vision Learners},
      author={He, Kaiming and Chen, Xinlei and others},
      journal={arXiv preprint arXiv:2111.06377},
      year={2021}
    }"""
    feat_arxiv = extract_entry_features(parse_bib_content(bib_arxiv).entries[0])
    outcome_arxiv = elect_and_classify(feat_arxiv, make_pool())

    assert outcome_arxiv.status == VerificationStatus.PREPRINT_UPGRADE
    assert outcome_arxiv.decision == "accept"
    assert outcome_arxiv.candidates[0].canonical_venue_id == "TPAMI"
    assert outcome_arxiv.candidates[1].canonical_venue_id == "CVPR"


def test_anti_hallucination_guardrails_and_network_error_distinction() -> None:
    # 1. Fabricated paper title -> SUSPECTED_HALLUCINATION
    bib_fake = """@inproceedings{fake2025quantum,
      title={Quantum Hyperbolic Mamba-99 for Zero-Shot Telepathic Segmentation},
      author={Nobody, Alice and Ghost, Bob},
      booktitle={CVPR},
      year={2025}
    }"""
    feat_fake = extract_entry_features(parse_bib_content(bib_fake).entries[0])
    out_fake = elect_and_classify(feat_fake, [])
    assert out_fake.status == VerificationStatus.SUSPECTED_HALLUCINATION
    assert out_fake.decision == "keep_original"

    # 2. Real paper title, fabricated/mismatched authors -> AUTHOR_MISMATCH (NEVER VERIFIED!)
    bib_wrong_author = """@inproceedings{he2016tampered,
      title={Deep Residual Learning for Image Recognition},
      author={Smith, John and Doe, Alice},
      booktitle={CVPR},
      year={2016}
    }"""
    feat_wa = extract_entry_features(parse_bib_content(bib_wrong_author).entries[0])
    real_cand = CandidateRecord(
        source_discovery="dblp",
        venue_tier="MAIN_CONF",
        canonical_venue_id="CVPR",
        matched_title="Deep Residual Learning for Image Recognition",
        matched_authors=["Kaiming He", "Xiangyu Zhang", "Shaoqing Ren", "Jian Sun"],
        matched_year=2016,
        matched_venue="CVPR",
    )
    out_wa = elect_and_classify(feat_wa, [real_cand])
    assert out_wa.status == VerificationStatus.METADATA_MISMATCH
    assert out_wa.decision == "keep_original"
    assert any(w.code == WarningCode.AUTHOR_MISMATCH for w in out_wa.warnings)

    # 2b. First author matches, but co-authors are fabricated -> MUST also trigger AUTHOR_MISMATCH!
    bib_partial_fake_author = """@inproceedings{he2016partialfake,
      title={Deep Residual Learning for Image Recognition},
      author={He, Kaiming and Fake, Alice and Ghost, Bob},
      booktitle={CVPR},
      year={2016}
    }"""
    feat_pfa = extract_entry_features(parse_bib_content(bib_partial_fake_author).entries[0])
    out_pfa = elect_and_classify(feat_pfa, [real_cand.model_copy(deep=True)])
    assert out_pfa.status == VerificationStatus.METADATA_MISMATCH
    assert out_pfa.decision == "keep_original"
    assert any(w.code == WarningCode.AUTHOR_MISMATCH for w in out_pfa.warnings)

    # 2c. Real co-authors, but first author swapped -> MUST also trigger AUTHOR_MISMATCH!
    bib_swapped_first = """@inproceedings{zhang2016swapped,
      title={Deep Residual Learning for Image Recognition},
      author={Zhang, Xiangyu and He, Kaiming and Ren, Shaoqing and Sun, Jian},
      booktitle={CVPR},
      year={2016}
    }"""
    feat_sf = extract_entry_features(parse_bib_content(bib_swapped_first).entries[0])
    out_sf = elect_and_classify(feat_sf, [real_cand.model_copy(deep=True)])
    assert out_sf.status == VerificationStatus.METADATA_MISMATCH
    assert out_sf.decision == "keep_original"
    assert any(w.code == WarningCode.AUTHOR_MISMATCH for w in out_sf.warnings)

    # 3. Preprint-only paper falsely claiming ICCV -> METADATA_MISMATCH + FALSE_PUBLISHED_VENUE
    bib_false_venue = """@inproceedings{smith2024onlyarxiv,
      title={A Purely Unpublished Preprint on Neural Rendering},
      author={Smith, Jane and Lee, David},
      booktitle={ICCV},
      year={2024}
    }"""
    feat_fv = extract_entry_features(parse_bib_content(bib_false_venue).entries[0])
    arxiv_only_cand = CandidateRecord(
        source_discovery="arxiv",
        venue_tier="PREPRINT",
        matched_title="A Purely Unpublished Preprint on Neural Rendering",
        matched_authors=["Jane Smith", "David Lee"],
        matched_year=2024,
        matched_venue="arXiv:2405.99999",
        arxiv_id="2405.99999",
    )
    out_fv = elect_and_classify(feat_fv, [arxiv_only_cand])
    assert out_fv.status == VerificationStatus.METADATA_MISMATCH
    assert out_fv.decision == "keep_original"
    assert any(w.code == WarningCode.FALSE_PUBLISHED_VENUE for w in out_fv.warnings)

    # 4. Venue differs from original (claims CVPR, actually published in ICCV) -> VENUE_DIFFERS_FROM_ORIGINAL
    iccv_cand = CandidateRecord(
        source_discovery="dblp",
        venue_tier="MAIN_CONF",
        canonical_venue_id="ICCV",
        matched_title="A Purely Unpublished Preprint on Neural Rendering",
        matched_authors=["Jane Smith", "David Lee"],
        matched_year=2024,
        matched_venue="ICCV",
        doi="10.1109/ICCV.2024.123",
    )
    bib_wrong_conf = bib_false_venue.replace("{ICCV}", "{CVPR}")
    feat_wc = extract_entry_features(parse_bib_content(bib_wrong_conf).entries[0])
    out_wc = elect_and_classify(feat_wc, [iccv_cand])
    assert out_wc.status == VerificationStatus.METADATA_MISMATCH
    assert any(w.code == WarningCode.VENUE_DIFFERS_FROM_ORIGINAL for w in out_wc.warnings)

    # 5. All upstream sources fail with network/timeout -> MUST be ERROR, NEVER SUSPECTED_HALLUCINATION
    out_net_err = elect_and_classify(feat_fake, [], all_sources_failed=True)
    assert out_net_err.status == VerificationStatus.ERROR
    assert out_net_err.decision == "keep_original"


@pytest.mark.asyncio
async def test_providers_crossref_openalex_arxiv_s2_and_network_errors() -> None:
    arxiv_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
      <entry>
        <id>http://arxiv.org/abs/2106.09685v2</id>
        <published>2021-06-17T17:51:00Z</published>
        <title>LoRA: Low-Rank Adaptation of Large Language Models</title>
        <author><name>Edward J. Hu</name></author>
        <author><name>Yelong Shen</name></author>
        <arxiv:primary_category term="cs.CL"/>
      </entry>
    </feed>"""

    with respx.mock(assert_all_called=True) as router:
        # Crossref 404 dead DOI
        router.get("https://api.crossref.org/works/10.1109%2FDEAD.2099.000").mock(
            return_value=httpx.Response(404)
        )
        # Crossref bibliographic search
        router.get("https://api.crossref.org/works").mock(
            return_value=httpx.Response(
                200,
                json={
                    "message": {
                        "items": [
                            {
                                "title": ["LoRA: Low-Rank Adaptation of Large Language Models"],
                                "author": [{"given": "Edward J.", "family": "Hu"}],
                                "container-title": ["ICLR"],
                                "published-print": {"date-parts": [[2022]]},
                                "DOI": "10.1000/iclr.2022.lora",
                                "type": "proceedings-article",
                            }
                        ]
                    }
                },
            )
        )
        # OpenAlex search
        router.get("https://api.openalex.org/works").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "title": "LoRA: Low-Rank Adaptation of Large Language Models",
                            "publication_year": 2022,
                            "type": "proceedings-article",
                            "authorships": [{"author": {"display_name": "Edward J. Hu"}}],
                            "primary_location": {
                                "landing_page_url": "https://openreview.net/forum?id=nZeVKeeFYf9",
                                "source": {
                                    "display_name": "International Conference on Learning Representations",
                                    "type": "conference",
                                },
                            },
                            "locations": [],
                        }
                    ]
                },
            )
        )
        # arXiv ID lookup & title search
        router.get("https://export.arxiv.org/api/query").mock(
            return_value=httpx.Response(200, text=arxiv_xml)
        )
        # Semantic Scholar 429 must gracefully degrade to [] without raising!
        router.get("https://api.semanticscholar.org/graph/v1/paper/search").mock(
            return_value=httpx.Response(429)
        )
        # DBLP 503 retry exhaustion -> raises UpstreamNetworkError
        router.get("https://dblp.org/search/publ/api").mock(
            return_value=httpx.Response(503)
        )

        cfg = AppConfig(polite_email="test@example.edu")
        async with RateLimitedHttpClient(
            config=cfg, enable_rate_sleep=False, backoff_base=0.0, max_retries=1
        ) as client:
            cand_404, is_404 = await lookup_crossref_doi(client, "10.1109/DEAD.2099.000")
            assert cand_404 is None and is_404 is True

            cr_cands = await search_crossref(client, "LoRA", "hu")
            assert len(cr_cands) == 1 and cr_cands[0].canonical_venue_id == "ICLR"

            oa_cands = await search_openalex(client, "LoRA")
            assert len(oa_cands) == 1
            assert "https://openreview.net/forum?id=nZeVKeeFYf9" in oa_cands[0].ee_urls

            ax_cands, ax_bad = await lookup_arxiv_by_id(client, "2106.09685")
            assert not ax_bad and ax_cands[0].raw_publisher_fields["primaryClass"] == "cs.CL"
            ax_search = await search_arxiv_by_title(client, "LoRA")
            assert len(ax_search) == 1

            s2_cands = await search_semantic_scholar(client, "LoRA")
            assert s2_cands == []

            with pytest.raises(UpstreamNetworkError):
                await search_dblp(client, "LoRA")


def test_sqlite_cache_ttl_and_cvf_toc(tmp_path: Path) -> None:
    cache = BibCache(db_path=tmp_path / "test_cache.sqlite3", ttl_days=30)
    cache.set_query_result("k1", {"status": "VERIFIED_CANONICAL", "confidence": 98.5})
    assert cache.get_query_result("k1") == {"status": "VERIFIED_CANONICAL", "confidence": 98.5}

    cache.save_cvf_toc(
        "CVPR",
        2024,
        [
            (
                "deep residual learning for image recognition",
                "Deep Residual Learning for Image Recognition",
                "https://openaccess.thecvf.com/content/CVPR2024/html/He_paper.html",
            )
        ],
    )
    assert cache.has_cvf_toc("CVPR", 2024)
    url = cache.lookup_cvf_paper_url("CVPR", 2024, "deep residual learning for image recognition")
    assert url == "https://openaccess.thecvf.com/content/CVPR2024/html/He_paper.html"

    stats = cache.get_stats()
    assert stats["query_cache_count"] == 1
    assert stats["cvf_toc_papers_count"] == 1

    deleted_q = cache.clear(scope="queries")
    assert deleted_q == 1
    assert cache.get_query_result("k1") is None
    assert cache.has_cvf_toc("CVPR", 2024)

    cache.clear(scope="all")
    assert not cache.has_cvf_toc("CVPR", 2024)
