"""Regression tests for real-world patterns discovered from user's curated examples/*.bib."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from bibcanon.adapters.openreview import fetch_openreview_or_neurips_bibtex
from bibcanon.core.bib_parser import parse_bib_content, parse_bib_file, splice_bib_document
from bibcanon.core.formatter import apply_title_case_protection
from bibcanon.core.normalizer import extract_entry_features, is_template_placeholder
from bibcanon.core.pipeline import build_initial_audit_entries, verify_single_entry
from bibcanon.core.scorer import elect_and_classify
from bibcanon.core.venue_dict import get_canonical_venue_id
from bibcanon.models import CandidateRecord, VerificationStatus, WarningCode
from bibcanon.providers.base import RateLimitedHttpClient


def test_ieee_and_acm_dois_never_produce_false_arxiv_ids_or_false_duplicates() -> None:
    bib = """
@INPROCEEDINGS{guan2024hallusionbench,
  author={Guan, Tianrui and Liu, Fuxiao},
  booktitle={2024 IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)},
  title={{HallusionBench}: An Advanced Diagnostic Suite},
  year={2024},
  doi={10.1109/CVPR52733.2024.01363}
}

@INPROCEEDINGS{li2024seedbench,
  author={Li, Bohao and Ge, Yuying},
  booktitle={2024 IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)},
  title={{SEED-Bench}: Benchmarking Multimodal Large Language Models},
  year={2024},
  doi={10.1109/CVPR52733.2024.01263}
}

@INPROCEEDINGS{acuna2018polygonrnnpp,
  author={Acuna, David and Fidler, Sanja},
  booktitle={2018 IEEE/CVF Conference on Computer Vision and Pattern Recognition},
  title={Efficient Interactive Annotation of Segmentation Datasets},
  year={2018},
  doi={10.1109/CVPR.2018.00096}
}

@article{sangkloy2016sketchy,
  author={Sangkloy, Patsorn and Hays, James},
  title={The {Sketchy} database},
  journal={ACM Trans. Graph.},
  year={2016},
  doi={10.1145/2897824.2925954}
}
"""
    doc = parse_bib_content(bib)
    for ent in doc.entries:
        feat = extract_entry_features(ent)
        assert feat.arxiv_id is None, f"Unexpected false arxiv_id={feat.arxiv_id} on {ent.cite_key}"
        assert feat.doi is not None

    audits = build_initial_audit_entries(doc)
    for a in audits:
        assert not any(w.code == WarningCode.DUPLICATE_IN_BIB for w in a.warnings)


def test_acl_braced_venues_and_expanded_venue_dictionary() -> None:
    assert (
        get_canonical_venue_id(
            "Proceedings of the 60th Annual Meeting of the {A}ssociation for {C}omputational {L}inguistics (Volume 1: Long Papers)"
        )
        == "ACL"
    )
    assert (
        get_canonical_venue_id(
            "Proceedings of the 2025 Conference of the Nations of the {A}mericas Chapter of the {A}ssociation for {C}omputational {L}inguistics"
        )
        == "NAACL"
    )
    assert get_canonical_venue_id("First Conference on Language Modeling") == "COLM"
    assert get_canonical_venue_id("Document Analysis and Recognition -- ICDAR 2024") == "ICDAR"
    assert get_canonical_venue_id("IEEE Robotics and Automation Letters") == "RA-L"
    assert (
        get_canonical_venue_id("Proc. ACM Interact. Mob. Wearable Ubiquitous Technol.")
        == "IMWUT"
    )


def test_partial_intra_word_braces_in_titles_preserved_intact() -> None:
    cases = [
        "{{P}oly{G}en: An Autoregressive Generative Model of 3{D} Meshes}",
        "{P}oly{G}en: An Autoregressive Generative Model of 3{D} Meshes",
        "Lo{RA}: Low-Rank Adaptation of Large Language Models",
        "Mini{CPM}: Unveiling the Potential of Small Language Models",
        "Modelling trajectories by using {B}{\\'e}zier curves",
        "DeepLab{V3} for Semantic Segmentation",
    ]
    for raw in cases:
        out = apply_title_case_protection(raw)
        assert "{{" not in out or raw.startswith("{{")
        # Re-applying must be strictly idempotent
        assert apply_title_case_protection(out) == out
    assert apply_title_case_protection("DeepLab{V3} for Semantic Segmentation") == "DeepLab{V3} for Semantic Segmentation"


@pytest.mark.asyncio
async def test_neurips_direct_pdf_url_fetches_bib_without_downloading_pdf() -> None:
    pdf_url = "https://proceedings.neurips.cc/paper_files/paper/2023/file/6dcf277ea32ce3288914faf369fe6de0-Paper-Conference.pdf"
    expected_bib_url = "https://proceedings.neurips.cc/paper_files/paper/2023/file/6dcf277ea32ce3288914faf369fe6de0-Bibtex-Conference.bib"
    nips_bib = """@inproceedings{liu2023llava,
      author = {Liu, Haotian and Li, Chunyuan},
      booktitle = {Advances in Neural Information Processing Systems},
      pages = {34892--34916},
      title = {Visual Instruction Tuning},
      volume = {36},
      year = {2023}
    }"""

    with respx.mock(assert_all_called=True) as router:
        # Notice we do NOT mock the .pdf URL: if code tried to download .pdf, respx would fail!
        router.get(expected_bib_url).mock(return_value=httpx.Response(200, text=nips_bib))
        async with RateLimitedHttpClient(enable_rate_sleep=False, backoff_base=0.0) as client:
            res = await fetch_openreview_or_neurips_bibtex(
                client,
                CandidateRecord(
                    source_discovery="dblp",
                    venue_tier="MAIN_CONF",
                    canonical_venue_id="NeurIPS",
                    matched_title="Visual Instruction Tuning",
                    matched_year=2023,
                    ee_urls=[pdf_url],
                ),
            )
    assert res is not None
    assert res[0] == "NeurIPS Proceedings"
    assert res[2]["pages"] == "34892--34916"


@pytest.mark.asyncio
async def test_template_placeholder_short_circuits_with_zero_network_calls() -> None:
    bib = """@article{Alpher02,
      author = {FirstName Alpher},
      title = {Frobnication},
      journal = {IEEE TPAMI},
      year = 2002
    }"""
    ent = parse_bib_content(bib).entries[0]
    assert is_template_placeholder(ent) is True

    with respx.mock(assert_all_called=True):
        async with RateLimitedHttpClient(enable_rate_sleep=False, backoff_base=0.0) as client:
            res = await verify_single_entry(ent, client)
    assert res.status == VerificationStatus.SUSPECTED_HALLUCINATION
    assert any("模板自带占位" in w.message for w in res.warnings)


def test_unlisted_venue_abbreviation_and_corporate_team_author_matching() -> None:
    # 1. Unlisted IEEE journal ("IEEE Sensors Journal" vs DBLP "IEEE Sens. J.") -> VERIFIED_CANONICAL
    bib_sens = """@article{Wang_2024_Recognition,
      author={Wang, Yifeng and Zhao, Yi},
      journal={IEEE Sensors Journal},
      title={Wearable Sensor Handwriting Recognition},
      year={2024}
    }"""
    feat_sens = extract_entry_features(parse_bib_content(bib_sens).entries[0])
    cand_sens = CandidateRecord(
        source_discovery="dblp",
        venue_tier="JOURNAL",
        matched_title="Wearable Sensor Handwriting Recognition",
        matched_authors=["Yifeng Wang", "Yi Zhao"],
        matched_year=2024,
        matched_venue="IEEE Sens. J.",
        doi="10.1109/JSEN.2024.12345",
    )
    out_sens = elect_and_classify(feat_sens, [cand_sens])
    assert out_sens.status == VerificationStatus.VERIFIED_CANONICAL
    assert not any(w.code == WarningCode.VENUE_DIFFERS_FROM_ORIGINAL for w in out_sens.warnings)

    # 2. Corporate Team author (`Team, Chameleon` on exact arXiv ID `2405.09818`)
    bib_team = """@article{chameleon2024,
      title={Chameleon: Mixed-modal early-fusion foundation models},
      author={Team, Chameleon},
      journal={arXiv preprint arXiv:2405.09818},
      year={2024}
    }"""
    feat_team = extract_entry_features(parse_bib_content(bib_team).entries[0])
    cand_team = CandidateRecord(
        source_discovery="arxiv",
        venue_tier="PREPRINT",
        matched_title="Chameleon: Mixed-Modal Early-Fusion Foundation Models",
        matched_authors=["Armen Aghajanyan", "Lili Yu"],
        matched_year=2024,
        matched_venue="arXiv:2405.09818",
        arxiv_id="2405.09818",
    )
    out_team = elect_and_classify(feat_team, [cand_team])
    assert out_team.status == VerificationStatus.VERIFIED_PREPRINT_ONLY
    assert not any(w.code == WarningCode.AUTHOR_MISMATCH for w in out_team.warnings)


def test_lossless_roundtrip_on_all_user_example_bib_files() -> None:
    examples_dir = Path(__file__).resolve().parent.parent / "examples"
    if not examples_dir.exists():
        pytest.skip("examples directory not present")

    bib_files = list(examples_dir.glob("*.bib"))
    assert len(bib_files) >= 3
    for bf in bib_files:
        doc = parse_bib_file(bf)
        assert len(doc.entries) >= 50
        audits = build_initial_audit_entries(doc)
        spliced, stats = splice_bib_document(doc.raw_text, audits)
        # When all entries are keep_original, spliced output is 100% byte-identical!
        assert spliced == doc.raw_text
        assert stats.kept_original_count == len(doc.entries)
