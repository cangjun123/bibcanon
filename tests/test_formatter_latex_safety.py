"""Unit tests for canonical publisher field retention, compact mode, and LaTeX safety."""

from __future__ import annotations

from bibcanon.core.formatter import (
    apply_title_case_protection,
    format_bibtex_entry,
    normalize_pages,
)


def test_canonical_mode_retains_all_publisher_fields_and_strips_only_noise() -> None:
    raw_fields = {
        "ENTRYTYPE": "inproceedings",
        "ID": "publisher_internal_key_999",
        "author": "Doe, Jane and Smith, John",
        "title": "Learning 3D RGB-D Representations with ResNet and Gaussian Splatting.",
        "booktitle": "Proceedings of the IEEE/CVF Conference on Computer Vision & Pattern Recognition",
        "editor": "Editor One and Editor Two",
        "volume": "14",
        "number": "2",
        "series": "CVPR '24",
        "pages": "105-114",
        "articleno": "42",
        "numpages": "10",
        "year": "2024",
        "month": "June",
        "publisher": "IEEE & CVF",
        "organization": "IEEE Computer Society",
        "address": "Seattle, WA, USA",
        "location": "Seattle, WA",
        "isbn": "979-8-3503-5300-6",
        "issn": "1063-6919",
        "doi": "https://doi.org/10.1109/CVPR52733.2024.00042",
        "pdf": "https://openaccess.thecvf.com/content/CVPR2024/papers/Doe_paper.pdf",
        "url": "https://openaccess.thecvf.com/content/CVPR2024/html/Doe_paper.html?foo=1&bar=2",
        # Noise fields that MUST be stripped:
        "abstract": "This is a huge 500-word abstract exported by Zotero.",
        "file": ":Users/jane/Zotero/storage/ABCD/paper.pdf:pdf",
        "local-url": "file:///localhost/Users/jane/paper.pdf",
        "mendeley-tags": "3d,vision",
        "zotero-key": "XYZ123",
        "annote": "Personal reading note",
        "biburl": "https://dblp.org/rec/conf/cvpr/DoeS24.bib",
        "bibsource": "dblp computer science bibliography, https://dblp.org",
        "timestamp": "Wed, 17 Nov 2026 10:00:00 +0100",
    }

    formatted = format_bibtex_entry(
        cite_key="my_locked_key_2024",
        entry_type="inproceedings",
        raw_fields=raw_fields,
        style_mode="canonical",
        protect_title_case=True,
    )

    # Citation key strictly locked
    assert formatted.startswith("@inproceedings{my_locked_key_2024,\n")
    assert "publisher_internal_key_999" not in formatted

    # Authentic publisher fields 100% retained
    for retained in (
        "editor = {Editor One and Editor Two}",
        "volume = {14}",
        "number = {2}",
        "series = {CVPR '24}",
        "pages = {105--114}",
        "articleno = {42}",
        "numpages = {10}",
        "month = {June}",
        r"publisher = {IEEE \& CVF}",
        "organization = {IEEE Computer Society}",
        "address = {Seattle, WA, USA}",
        "location = {Seattle, WA}",
        "isbn = {979-8-3503-5300-6}",
        "issn = {1063-6919}",
        "doi = {10.1109/CVPR52733.2024.00042}",
        "pdf = {https://openaccess.thecvf.com/content/CVPR2024/papers/Doe_paper.pdf}",
        "url = {https://openaccess.thecvf.com/content/CVPR2024/html/Doe_paper.html?foo=1&bar=2}",
    ):
        assert retained in formatted

    # Bare '&' in booktitle/publisher escaped, while '&' in url is UNTOUCHED
    assert (
        r"booktitle = {Proceedings of the IEEE/CVF Conference on Computer Vision \& Pattern Recognition}"
        in formatted
    )
    assert "?foo=1&bar=2" in formatted
    assert r"?foo=1\&bar=2" not in formatted

    # Noise fields completely stripped
    for noise in (
        "abstract =",
        "file =",
        "local-url =",
        "mendeley-tags =",
        "zotero-key =",
        "annote =",
        "biburl =",
        "bibsource =",
        "timestamp =",
    ):
        assert noise not in formatted


def test_compact_mode_abbreviates_venue_and_strips_verbose_fields() -> None:
    raw_fields = {
        "author": "He, Kaiming and Sun, Jian",
        "title": "Deep Residual Learning",
        "booktitle": "Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition",
        "pages": "770–778",
        "year": "2016",
        "month": "June",
        "publisher": "IEEE",
        "url": "https://example.com",
        "doi": "10.1109/CVPR.2016.90",
    }
    compact = format_bibtex_entry(
        cite_key="he2016deep",
        entry_type="inproceedings",
        raw_fields=raw_fields,
        style_mode="compact",
        protect_title_case=True,
    )
    assert "booktitle = {CVPR}" in compact
    assert "pages = {770--778}" in compact
    assert "year = {2016}" in compact
    assert "publisher =" not in compact
    assert "url =" not in compact
    assert "doi =" not in compact
    assert "month =" not in compact


def test_arxiv_native_misc_format_preserves_eprint_fields() -> None:
    raw_fields = {
        "title": "LoRA: Low-Rank Adaptation of Large Language Models",
        "author": "Edward J. Hu and others",
        "year": "2021",
        "eprint": "2106.09685",
        "archiveprefix": "arXiv",
        "primaryclass": "cs.CL",
        "url": "https://arxiv.org/abs/2106.09685",
    }
    out = format_bibtex_entry(
        cite_key="hu2021lora",
        entry_type="misc",
        raw_fields=raw_fields,
        style_mode="canonical",
        protect_title_case=True,
    )
    assert out.startswith("@misc{hu2021lora,\n")
    assert "eprint = {2106.09685}" in out
    assert "archivePrefix = {arXiv}" in out
    assert "primaryClass = {cs.CL}" in out
    assert "url = {https://arxiv.org/abs/2106.09685}" in out
    assert "title = {{LoRA}: Low-Rank Adaptation of Large Language Models}" in out


def test_page_dash_and_title_case_protection_idempotency() -> None:
    assert normalize_pages("105-114") == "105--114"
    assert normalize_pages("105–114") == "105--114"
    assert normalize_pages("105—114") == "105--114"
    assert normalize_pages("105--114") == "105--114"

    raw_title = (
        "3D RGB-D SLAM with ResNet, ViT, NeRF, LLMs and Bayesian Gaussian Transformer ($L_2 & L_1$)"
    )
    once = apply_title_case_protection(raw_title)
    twice = apply_title_case_protection(once)
    assert once == twice
    assert "{{3D}}" not in twice
    assert "{{ResNet}}" not in twice
    assert "{3D}" in once
    assert "{RGB-D}" in once
    assert "{SLAM}" in once
    assert "{ResNet}" in once
    assert "{ViT}" in once
    assert "{NeRF}" in once
    assert "{LLMs}" in once
    assert "{Bayesian}" in once
    assert "{Gaussian}" in once
    assert "{Transformer}" in once

    # Globally double-braced title (represented as single outer '{...}' after bibtexparser strips field braces)
    already_global = "{3D ResNet for Image Recognition}"
    assert apply_title_case_protection(already_global) == already_global
