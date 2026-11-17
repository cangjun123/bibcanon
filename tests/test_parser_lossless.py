"""Unit tests for lossless character-span BibTeX parsing, patching, backup, normalizer, and dedup."""

from __future__ import annotations

from pathlib import Path

from bibcanon.config import load_config, save_config
from bibcanon.core.bib_parser import (
    parse_bib_content,
    parse_bib_file,
    splice_bib_document,
    write_bib_with_backup,
)
from bibcanon.core.dedup import mark_duplicate_entries
from bibcanon.core.normalizer import (
    extract_author_surnames,
    extract_entry_features,
    normalize_title,
)
from bibcanon.models import (
    AppConfig,
    CandidateRecord,
    EntryAuditResult,
    VerificationStatus,
    WarningCode,
)


SAMPLE_COMPLEX_BIB = """% ==========================================
% Overleaf References - Backbone & 3D Vision
% ==========================================

@string{cvpr = "Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition"}
@preamble{"\\newcommand{\\noop}[1]{}"}

% Commented-out entry must NEVER be parsed as active:
% @inproceedings{ghost2020fake,
%   title = {Should Be Ignored},
%   author = {Nobody},
%   year = {2020}
% }

@inproceedings{he2016deep,
    title={Deep Residual Learning for Image Recognition},
    author={He, Kaiming and Zhang, Xiangyu and Ren, Shaoqing and Sun, Jian},
    booktitle = cvpr,
    pages={770--778},
    year={2016}
}

% --- Section 2: Preprints to upgrade ---
@article{kerbl20233d,
  title={3D Gaussian Splatting for Real-Time Radiance Field Rendering},
  author={Kerbl, Bernhard and Kopanas, Georgios and Leimk{\\"u}hler, Thomas and Drettakis, George},
  journal={arXiv preprint arXiv:2308.04079},
  year={2023}
}

% --- Section 3: Untouched tail entry with custom indentation ---
@book{scholkopf2002learning,
\ttitle = "Learning with Kernels: Support Vector Machines, Regularization, Optimization, and Beyond",
\tauthor = "Bernhard Sch{\\"o}lkopf and Alexander J. Smola",
\tpublisher = "MIT Press",
\tyear = 2002
}
% Trailing file comment
"""


def test_lossless_span_parsing_and_partial_splicing() -> None:
    doc = parse_bib_content(SAMPLE_COMPLEX_BIB)
    assert len(doc.entries) == 3
    assert [e.cite_key for e in doc.entries] == [
        "he2016deep",
        "kerbl20233d",
        "scholkopf2002learning",
    ]
    # Verify @string macro interpolation worked for verification features without altering raw text
    assert "Computer Vision and Pattern Recognition" in doc.entries[0].fields["booktitle"]
    for ent in doc.entries:
        assert SAMPLE_COMPLEX_BIB[ent.span_start : ent.span_end] == ent.raw_bibtex

    # Build audit results: ONLY replace middle entry `kerbl20233d`, keep first & third untouched
    audit_entries: list[EntryAuditResult] = []
    for ent in doc.entries:
        ae = EntryAuditResult(
            cite_key=ent.cite_key,
            entry_index=ent.entry_index,
            span_start=ent.span_start,
            span_end=ent.span_end,
            original_bibtex=ent.raw_bibtex,
            original_fields=ent.fields,
            status=VerificationStatus.VERIFIED_CANONICAL,
            decision="keep_original",
        )
        audit_entries.append(ae)

    audit_entries[1].decision = "accept"
    audit_entries[1].status = VerificationStatus.PREPRINT_UPGRADE
    audit_entries[1].selected_candidate_idx = 0
    audit_entries[1].candidates = [
        CandidateRecord(
            source_discovery="dblp",
            bibtex_origin="DOI Official (ACM)",
            venue_tier="JOURNAL",
            canonical_venue_id="TOG",
            score=99.0,
            entry_type="article",
            raw_publisher_fields={
                "author": "Kerbl, Bernhard and Kopanas, Georgios and Leimk{\\\"u}hler, Thomas and Drettakis, George",
                "title": "3D Gaussian Splatting for Real-Time Radiance Field Rendering",
                "journal": "ACM Transactions on Graphics",
                "volume": "42",
                "number": "4",
                "articleno": "139",
                "numpages": "14",
                "year": "2023",
                "publisher": "Association for Computing Machinery",
                "doi": "10.1145/3592433",
            },
        )
    ]

    spliced, stats = splice_bib_document(SAMPLE_COMPLEX_BIB, audit_entries)
    assert stats.total_entries == 3
    assert stats.accepted_count == 1
    assert stats.kept_original_count == 2

    # 1. Exact byte-for-byte prefix before entry[1] (including header comments, @string, @preamble, commented entry, entry[0], section 2 comment)
    expected_prefix = SAMPLE_COMPLEX_BIB[: doc.entries[1].span_start]
    assert spliced.startswith(expected_prefix)

    # 2. Exact byte-for-byte suffix after entry[1] (including section 3 comment, tab-indented entry[2], trailing comment)
    expected_suffix = SAMPLE_COMPLEX_BIB[doc.entries[1].span_end :]
    assert spliced.endswith(expected_suffix)

    # 3. Replaced middle entry strictly preserves original cite_key `kerbl20233d`
    middle_segment = spliced[len(expected_prefix) : len(spliced) - len(expected_suffix)]
    assert middle_segment.startswith("@article{kerbl20233d,")
    assert "articleno = {139}" in middle_segment
    assert "title = {{3D} {Gaussian} Splatting for Real-Time Radiance Field Rendering}" in middle_segment


def test_windows_utf8_and_latex_accent_equivalence(tmp_path: Path) -> None:
    bib_escaped = """@article{scholkopf1,
  title = {Estimating the Support of a High-Dimensional Distribution},
  author = {Sch{\\"o}lkopf, Bernhard and Platt, John C. and Shawe-Taylor, John},
  year = {2001}
}
"""
    bib_utf8 = """@article{scholkopf2,
  title = {Estimating the Support of a High-Dimensional Distribution},
  author = {Bernhard Schölkopf and John C. Platt and John Shawe-Taylor},
  year = {2001}
}
"""
    f1 = tmp_path / "escaped.bib"
    f2 = tmp_path / "utf8.bib"
    f1.write_text(bib_escaped, encoding="utf-8")
    f2.write_text(bib_utf8, encoding="utf-8")

    doc1 = parse_bib_file(f1)
    doc2 = parse_bib_file(f2)

    surnames1, et_al1 = extract_author_surnames(doc1.entries[0].fields["author"])
    surnames2, et_al2 = extract_author_surnames(doc2.entries[0].fields["author"])
    assert surnames1 == surnames2 == ["scholkopf", "platt", "shawe-taylor"]
    assert et_al1 is False and et_al2 is False
    assert normalize_title(doc1.entries[0].fields["title"]) == normalize_title(
        doc2.entries[0].fields["title"]
    )


def test_backup_before_write_local(tmp_path: Path) -> None:
    orig_path = tmp_path / "references.bib"
    original_content = "% Original header\n@misc{foo2024,\n  title={Foo — Bar}\n}\n"
    orig_path.write_text(original_content, encoding="utf-8")

    updated_content = "% Original header\n@inproceedings{foo2024,\n  title={Foo -- Bar}\n}\n"
    bak_path = write_bib_with_backup(orig_path, updated_content)

    assert bak_path.exists()
    assert bak_path.name.startswith("references.bib.bak.")
    assert bak_path.read_text(encoding="utf-8") == original_content
    assert orig_path.read_text(encoding="utf-8") == updated_content


def test_arxiv_doi_classified_as_arxiv_preprint_and_dedup() -> None:
    bib_text = """
@misc{vaswani2017arxiv,
  title = {Attention Is All You Need},
  author = {Ashish Vaswani and others},
  doi = {10.48550/arXiv.1706.03762},
  year = {2017}
}

@inproceedings{vaswani2017nips,
  title = {Attention is all you need},
  author = {Vaswani, Ashish and Shazeer, Noam and Parmar, Niki},
  booktitle = {Advances in Neural Information Processing Systems},
  year = {2017}
}
"""
    doc = parse_bib_content(bib_text)
    feat0 = extract_entry_features(doc.entries[0])
    feat1 = extract_entry_features(doc.entries[1])

    # 10.48550/arXiv.* must map to arxiv_id, NOT published doi
    assert feat0.arxiv_id == "1706.03762"
    assert feat0.doi is None
    assert feat0.is_preprint is True
    assert feat0.has_et_al is True

    assert feat1.canonical_venue_id == "NeurIPS"
    assert feat1.is_preprint is False

    audits = [
        EntryAuditResult(
            cite_key=e.cite_key,
            entry_index=e.entry_index,
            span_start=e.span_start,
            span_end=e.span_end,
            original_bibtex=e.raw_bibtex,
            original_fields=e.fields,
        )
        for e in doc.entries
    ]
    mark_duplicate_entries(audits, doc.entries)
    assert any(w.code == WarningCode.DUPLICATE_IN_BIB for w in audits[0].warnings)
    assert audits[0].warnings[0].other_cite_keys == ["vaswani2017nips"]
    assert audits[1].warnings[0].other_cite_keys == ["vaswani2017arxiv"]


def test_config_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BIBCANON_HOME", str(tmp_path))
    cfg = AppConfig(polite_email="researcher@univ.edu", proxy_url="http://127.0.0.1:7890")
    save_config(cfg)
    loaded = load_config()
    assert loaded.polite_email == "researcher@univ.edu"
    assert loaded.proxy_url == "http://127.0.0.1:7890"
