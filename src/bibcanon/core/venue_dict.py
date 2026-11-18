"""CV/AI/ML venue synonym recognition, compact abbreviations, and proper-noun dictionary."""

from __future__ import annotations

import re
from dataclasses import dataclass

from bibcanon.models import VenueTier


@dataclass(frozen=True)
class VenueEntry:
    """Canonical venue metadata entry."""

    canonical_id: str
    compact_abbr: str
    tier: VenueTier
    patterns: tuple[re.Pattern[str], ...]


def _compile_patterns(*raw_patterns: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p, re.IGNORECASE) for p in raw_patterns)


def _clean_venue_for_match(venue_text: str | None) -> str:
    """Strip LaTeX protective braces (e.g. '{A}ssociation') and escapes before regex matching."""
    if not venue_text:
        return ""
    cleaned = venue_text.replace("{", "").replace("}", "")
    cleaned = cleaned.replace(r"\&", "&")
    return re.sub(r"\s+", " ", cleaned).strip()


WORKSHOP_KEYWORDS_RE = re.compile(
    r"\b(?:"
    r"workshops?|cvprw|iccvw|eccvw|icmlw|neuripsw|nipsw|iclrw|aaaiw|aclw|emnlpw|"
    r"wacvw|companion|extended\s+abstracts?|demos?\b|demonstrations?|"
    r"doctoral\s+consortium|tutorials?|late[\s\-]+breaking|student\s+abstract"
    r")\b",
    re.IGNORECASE,
)

PREPRINT_KEYWORDS_RE = re.compile(
    r"\b(?:arxiv|corr|biorxiv|medrxiv|ssrn|techrxiv|preprint|tech\.?\s*rep(?:ort)?|unpublished|hal-\d+)\b",
    re.IGNORECASE,
)

# Ordered so specific venues (e.g., SIGGRAPH Asia, IEEE TPAMI) match before broader patterns.
VENUE_ENTRIES: tuple[VenueEntry, ...] = (
    # --- Computer Vision Conferences ---
    VenueEntry(
        canonical_id="CVPR",
        compact_abbr="CVPR",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bcvpr\b",
            r"computer\s+vision\s+and\s+pattern\s+recognition",
            r"comput\.\s*vis\.\s*pattern\s*recognit",
        ),
    ),
    VenueEntry(
        canonical_id="ICCV",
        compact_abbr="ICCV",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\biccv\b",
            r"international\s+conference\s+on\s+computer\s+vision",
            r"int\.\s*conf\.\s*comput\.\s*vis\.",
        ),
    ),
    VenueEntry(
        canonical_id="ECCV",
        compact_abbr="ECCV",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\beccv\b",
            r"european\s+conference\s+on\s+computer\s+vision",
            r"eur\.\s*conf\.\s*comput\.\s*vis\.",
        ),
    ),
    VenueEntry(
        canonical_id="WACV",
        compact_abbr="WACV",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bwacv\b",
            r"winter\s+conference\s+on\s+applications\s+of\s+computer\s+vision",
        ),
    ),
    VenueEntry(
        canonical_id="BMVC",
        compact_abbr="BMVC",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bbmvc\b",
            r"british\s+machine\s+vision\s+conference",
        ),
    ),
    VenueEntry(
        canonical_id="3DV",
        compact_abbr="3DV",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\b3dv\b",
            r"international\s+conference\s+on\s+3d\s+vision",
        ),
    ),
    VenueEntry(
        canonical_id="MICCAI",
        compact_abbr="MICCAI",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bmiccai\b",
            r"medical\s+image\s+computing\s+and\s+computer[\s\-]+assisted\s+intervention",
        ),
    ),
    # --- Machine Learning & AI Conferences ---
    VenueEntry(
        canonical_id="ICML",
        compact_abbr="ICML",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bicml\b",
            r"international\s+conference\s+on\s+machine\s+learning",
            r"int\.\s*conf\.\s*mach\.\s*learn\.",
        ),
    ),
    VenueEntry(
        canonical_id="NeurIPS",
        compact_abbr="NeurIPS",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bneurips\b",
            r"\bnips\b",
            r"neural\s+information\s+processing\s+systems",
            r"adv\.\s*neural\s*inf\.\s*process\.\s*syst",
        ),
    ),
    VenueEntry(
        canonical_id="ICLR",
        compact_abbr="ICLR",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\biclr\b",
            r"international\s+conference\s+on\s+learning\s+representations",
        ),
    ),
    VenueEntry(
        canonical_id="AAAI",
        compact_abbr="AAAI",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\baaai\b",
            r"aaai\s+conference\s+on\s+artificial\s+intelligence",
            r"national\s+conference\s+on\s+artificial\s+intelligence",
        ),
    ),
    VenueEntry(
        canonical_id="IJCAI",
        compact_abbr="IJCAI",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bijcai\b",
            r"international\s+joint\s+conference\s+on\s+artificial\s+intelligence",
        ),
    ),
    VenueEntry(
        canonical_id="AISTATS",
        compact_abbr="AISTATS",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\baistats\b",
            r"artificial\s+intelligence\s+and\s+statistics",
        ),
    ),
    VenueEntry(
        canonical_id="UAI",
        compact_abbr="UAI",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\buai\b",
            r"uncertainty\s+in\s+artificial\s+intelligence",
        ),
    ),
    VenueEntry(
        canonical_id="COLT",
        compact_abbr="COLT",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bcolt\b",
            r"conference\s+on\s+learning\s+theory",
            r"computational\s+learning\s+theory",
        ),
    ),
    VenueEntry(
        canonical_id="CoRL",
        compact_abbr="CoRL",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bcorl\b",
            r"conference\s+on\s+robot\s+learning",
        ),
    ),
    VenueEntry(
        canonical_id="ACML",
        compact_abbr="ACML",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bacml\b",
            r"asian\s+conference\s+on\s+machine\s+learning",
        ),
    ),
    VenueEntry(
        canonical_id="ECAI",
        compact_abbr="ECAI",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\becai\b",
            r"european\s+conference\s+on\s+artificial\s+intelligence",
        ),
    ),
    VenueEntry(
        canonical_id="COLM",
        compact_abbr="COLM",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bcolm\b",
            r"conference\s+on\s+language\s+modeling",
        ),
    ),
    VenueEntry(
        canonical_id="ACCV",
        compact_abbr="ACCV",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\baccv\b",
            r"asian\s+conference\s+on\s+computer\s+vision",
        ),
    ),
    VenueEntry(
        canonical_id="ICPR",
        compact_abbr="ICPR",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bicpr\b",
            r"international\s+conference\s+on\s+pattern\s+recognition",
            r"int\.\s*conf\.\s*pattern\s*recog",
        ),
    ),
    VenueEntry(
        canonical_id="ICIP",
        compact_abbr="ICIP",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bicip\b",
            r"international\s+conference\s+on\s+image\s+processing",
            r"int\.\s*conf\.\s*image\s*process",
        ),
    ),
    VenueEntry(
        canonical_id="ICME",
        compact_abbr="ICME",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bicme\b",
            r"international\s+conference\s+on\s+multimedia\s+and\s+expo",
            r"int\.\s*conf\.\s*multimedia\s+and\s+expo",
        ),
    ),
    VenueEntry(
        canonical_id="ICDAR",
        compact_abbr="ICDAR",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bicdar\b",
            r"document\s+analysis\s+and\s+recognition",
        ),
    ),
    VenueEntry(
        canonical_id="ICFHR",
        compact_abbr="ICFHR",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bicfhr\b",
            r"frontiers\s+in\s+handwriting\s+recognition",
        ),
    ),
    VenueEntry(
        canonical_id="CHI",
        compact_abbr="CHI",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bchi\s+conference\b",
            r"human\s+factors\s+in\s+computing\s+systems",
        ),
    ),
    VenueEntry(
        canonical_id="UIST",
        compact_abbr="UIST",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\buist\b",
            r"user\s+interface\s+software\s+and\s+technology",
        ),
    ),
    # --- NLP Conferences ---
    VenueEntry(
        canonical_id="NAACL",
        compact_abbr="NAACL",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bnaacl\b",
            r"(?:north\s+american|nations\s+of\s+the\s+americas)\s+chapter\s+of\s+the\s+association\s+for\s+computational\s+linguistics",
        ),
    ),
    VenueEntry(
        canonical_id="EACL",
        compact_abbr="EACL",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\beacl\b",
            r"european\s+chapter\s+of\s+the\s+association\s+for\s+computational\s+linguistics",
        ),
    ),
    VenueEntry(
        canonical_id="EMNLP",
        compact_abbr="EMNLP",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bemnlp\b",
            r"empirical\s+methods\s+in\s+natural\s+language\s+processing",
        ),
    ),
    VenueEntry(
        canonical_id="ACL",
        compact_abbr="ACL",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bacl\b",
            r"annual\s+meeting\s+of\s+the\s+association\s+for\s+computational\s+linguistics",
            r"association\s+for\s+computational\s+linguistics",
        ),
    ),
    VenueEntry(
        canonical_id="COLING",
        compact_abbr="COLING",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bcoling\b",
            r"international\s+conference\s+on\s+computational\s+linguistics",
        ),
    ),
    # --- Graphics, Multimedia, Robotics, Speech & Data Mining ---
    VenueEntry(
        canonical_id="SIGGRAPH Asia",
        compact_abbr="SIGGRAPH Asia",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bsiggraph\s+asia\b",
        ),
    ),
    VenueEntry(
        canonical_id="SIGGRAPH",
        compact_abbr="SIGGRAPH",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bsiggraph\b",
            r"special\s+interest\s+group\s+on\s+computer\s+graphics",
        ),
    ),
    VenueEntry(
        canonical_id="ACM MM",
        compact_abbr="ACM MM",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bacm\s+mm\b",
            r"\bacm\s+multimedia\b",
            r"acm\s+international\s+conference\s+on\s+multimedia",
        ),
    ),
    VenueEntry(
        canonical_id="KDD",
        compact_abbr="KDD",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bsigkdd\b",
            r"\bkdd\b",
            r"knowledge\s+discovery\s+and\s+data\s+mining",
        ),
    ),
    VenueEntry(
        canonical_id="WWW",
        compact_abbr="WWW",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bwww\b",
            r"the\s+web\s+conference",
            r"international\s+world\s+wide\s+web\s+conference",
        ),
    ),
    VenueEntry(
        canonical_id="SIGIR",
        compact_abbr="SIGIR",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bsigir\b",
            r"research\s+and\s+development\s+in\s+information\s+retrieval",
        ),
    ),
    VenueEntry(
        canonical_id="WSDM",
        compact_abbr="WSDM",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bwsdm\b",
            r"web\s+search\s+and\s+data\s+mining",
        ),
    ),
    VenueEntry(
        canonical_id="ICRA",
        compact_abbr="ICRA",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bicra\b",
            r"international\s+conference\s+on\s+robotics\s+and\s+automation",
        ),
    ),
    VenueEntry(
        canonical_id="IROS",
        compact_abbr="IROS",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\biros\b",
            r"intelligent\s+robots\s+and\s+systems",
        ),
    ),
    VenueEntry(
        canonical_id="RSS",
        compact_abbr="RSS",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\brss\b",
            r"robotics:\s*science\s+and\s+systems",
        ),
    ),
    VenueEntry(
        canonical_id="ICASSP",
        compact_abbr="ICASSP",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\bicassp\b",
            r"acoustics,\s*speech\s+and\s+signal\s+processing",
        ),
    ),
    VenueEntry(
        canonical_id="INTERSPEECH",
        compact_abbr="INTERSPEECH",
        tier="MAIN_CONF",
        patterns=_compile_patterns(
            r"\binterspeech\b",
        ),
    ),
    # --- Premier Journals ---
    VenueEntry(
        canonical_id="TPAMI",
        compact_abbr="IEEE TPAMI",
        tier="JOURNAL",
        patterns=_compile_patterns(
            r"\btpami\b",
            r"\bpami\b",
            r"pattern\s+analysis\s+and\s+machine\s+intelligence",
            r"trans\.\s*pattern\s*anal\.\s*mach\.\s*intell",
        ),
    ),
    VenueEntry(
        canonical_id="IJCV",
        compact_abbr="IJCV",
        tier="JOURNAL",
        patterns=_compile_patterns(
            r"\bijcv\b",
            r"international\s+journal\s+of\s+computer\s+vision",
            r"int\.\s*j\.\s*comput\.\s*vis",
        ),
    ),
    VenueEntry(
        canonical_id="TIP",
        compact_abbr="IEEE TIP",
        tier="JOURNAL",
        patterns=_compile_patterns(
            r"\bieee\s+tip\b",
            r"transactions\s+on\s+image\s+processing",
            r"trans\.\s*image\s*process",
        ),
    ),
    VenueEntry(
        canonical_id="TNNLS",
        compact_abbr="IEEE TNNLS",
        tier="JOURNAL",
        patterns=_compile_patterns(
            r"\btnnls\b",
            r"neural\s+networks\s+and\s+learning\s+systems",
        ),
    ),
    VenueEntry(
        canonical_id="TMM",
        compact_abbr="IEEE TMM",
        tier="JOURNAL",
        patterns=_compile_patterns(
            r"\bieee\s+tmm\b",
            r"transactions\s+on\s+multimedia",
        ),
    ),
    VenueEntry(
        canonical_id="TCSVT",
        compact_abbr="IEEE TCSVT",
        tier="JOURNAL",
        patterns=_compile_patterns(
            r"\btcsvt\b",
            r"circuits\s+and\s+systems\s+for\s+video\s+technology",
        ),
    ),
    VenueEntry(
        canonical_id="TVCG",
        compact_abbr="IEEE TVCG",
        tier="JOURNAL",
        patterns=_compile_patterns(
            r"\btvcg\b",
            r"visualization\s+and\s+computer\s+graphics",
        ),
    ),
    VenueEntry(
        canonical_id="JMLR",
        compact_abbr="JMLR",
        tier="JOURNAL",
        patterns=_compile_patterns(
            r"\bjmlr\b",
            r"journal\s+of\s+machine\s+learning\s+research",
            r"j\.\s*mach\.\s*learn\.\s*res",
        ),
    ),
    VenueEntry(
        canonical_id="TMLR",
        compact_abbr="TMLR",
        tier="JOURNAL",
        patterns=_compile_patterns(
            r"\btmlr\b",
            r"transactions\s+on\s+machine\s+learning\s+research",
        ),
    ),
    VenueEntry(
        canonical_id="TOG",
        compact_abbr="ACM TOG",
        tier="JOURNAL",
        patterns=_compile_patterns(
            r"\bacm\s+tog\b",
            r"transactions\s+on\s+graphics",
            r"acm\s+trans\.\s*graph",
        ),
    ),
    VenueEntry(
        canonical_id="TACL",
        compact_abbr="TACL",
        tier="JOURNAL",
        patterns=_compile_patterns(
            r"\btacl\b",
            r"transactions\s+of\s+the\s+association\s+for\s+computational\s+linguistics",
        ),
    ),
    VenueEntry(
        canonical_id="AIJ",
        compact_abbr="AIJ",
        tier="JOURNAL",
        patterns=_compile_patterns(
            r"^artificial\s+intelligence$",
            r"artif\.\s*intell\.",
        ),
    ),
    VenueEntry(
        canonical_id="PR",
        compact_abbr="Pattern Recognition",
        tier="JOURNAL",
        patterns=_compile_patterns(
            r"^pattern\s+recognition$",
            r"^pattern\s+recognit\.?$",
        ),
    ),
    VenueEntry(
        canonical_id="Nature Machine Intelligence",
        compact_abbr="Nat. Mach. Intell.",
        tier="JOURNAL",
        patterns=_compile_patterns(
            r"nature\s+machine\s+intelligence",
            r"nat\.\s*mach\.\s*intell",
        ),
    ),
    VenueEntry(
        canonical_id="Nature Communications",
        compact_abbr="Nat. Commun.",
        tier="JOURNAL",
        patterns=_compile_patterns(
            r"nature\s+communications",
            r"nat\.\s*commun",
        ),
    ),
    VenueEntry(
        canonical_id="Nature",
        compact_abbr="Nature",
        tier="JOURNAL",
        patterns=_compile_patterns(
            r"^nature$",
        ),
    ),
    VenueEntry(
        canonical_id="Science",
        compact_abbr="Science",
        tier="JOURNAL",
        patterns=_compile_patterns(
            r"^science$",
        ),
    ),
    VenueEntry(
        canonical_id="RA-L",
        compact_abbr="IEEE RA-L",
        tier="JOURNAL",
        patterns=_compile_patterns(
            r"\bra-l\b",
            r"robotics\s+and\s+automation\s+letters",
        ),
    ),
    VenueEntry(
        canonical_id="T-RO",
        compact_abbr="IEEE T-RO",
        tier="JOURNAL",
        patterns=_compile_patterns(
            r"\bt-ro\b",
            r"ieee\s+transactions\s+on\s+robotics",
        ),
    ),
    VenueEntry(
        canonical_id="IMWUT",
        compact_abbr="Proc. ACM IMWUT",
        tier="JOURNAL",
        patterns=_compile_patterns(
            r"\bimwut\b",
            r"interact\.\s*mob\.\s*wearable\s*ubiquitous\s*technol",
            r"interactive,\s*mobile,\s*wearable\s+and\s+ubiquitous\s+technologies",
        ),
    ),
    VenueEntry(
        canonical_id="CGF",
        compact_abbr="Comput. Graph. Forum",
        tier="JOURNAL",
        patterns=_compile_patterns(
            r"computer\s+graphics\s+forum",
            r"comput\.\s*graph\.\s*forum",
        ),
    ),
    VenueEntry(
        canonical_id="TVC",
        compact_abbr="Vis. Comput.",
        tier="JOURNAL",
        patterns=_compile_patterns(
            r"^the\s+visual\s+computer$",
            r"the\s+vis\.\s*comput",
        ),
    ),
    VenueEntry(
        canonical_id="IJDAR",
        compact_abbr="IJDAR",
        tier="JOURNAL",
        patterns=_compile_patterns(
            r"\bijdar\b",
            r"international\s+journal\s+on\s+document\s+analysis\s+and\s+recognition",
        ),
    ),
    VenueEntry(
        canonical_id="SPL",
        compact_abbr="IEEE SPL",
        tier="JOURNAL",
        patterns=_compile_patterns(
            r"signal\s+processing\s+letters",
            r"sign\.\s*process\.\s*letters",
        ),
    ),
)

VENUE_BY_ID: dict[str, VenueEntry] = {v.canonical_id: v for v in VENUE_ENTRIES}


# Proper nouns & domain terms whose capitalization must be preserved in BibTeX titles.
PROTECTED_PROPER_NOUNS: dict[str, str] = {
    word.lower(): word
    for word in (
        "Gaussian",
        "Gaussians",
        "Bayesian",
        "Markov",
        "Markovian",
        "Fourier",
        "Laplacian",
        "Laplace",
        "Euclidean",
        "Riemannian",
        "Hilbert",
        "Poisson",
        "Bernoulli",
        "Boltzmann",
        "Langevin",
        "Wasserstein",
        "Sinkhorn",
        "Kalman",
        "Monte",
        "Carlo",
        "Sobel",
        "Canny",
        "Hough",
        "Gabor",
        "Chebyshev",
        "Legendre",
        "Hermite",
        "Jacobian",
        "Hessian",
        "Lagrangian",
        "Hamiltonian",
        "Cauchy",
        "Dirichlet",
        "Neumann",
        "Euler",
        "Runge",
        "Kutta",
        "Newton",
        "Lorentz",
        "Minkowski",
        "Hausdorff",
        "Jensen",
        "Shannon",
        "Kullback",
        "Leibler",
        "Mahalanobis",
        "Frobenius",
        "Hadamard",
        "Kronecker",
        "Toeplitz",
        "Cholesky",
        "Moore",
        "Penrose",
        "Turing",
        "Nash",
        "Boolean",
        "Transformer",
        "Transformers",
        "Swin",
        "Mamba",
        "Llama",
        "Mistral",
        "Mixtral",
        "Qwen",
        "Python",
        "CUDA",
        "Linux",
        "Windows",
        "KITTI",
        "MNIST",
        "CIFAR",
        "COCO",
    )
}


def is_workshop_venue(venue_text: str | None) -> bool:
    """Return True if the venue string contains workshop/companion/demo indicators."""
    cleaned = _clean_venue_for_match(venue_text)
    if not cleaned:
        return False
    return bool(WORKSHOP_KEYWORDS_RE.search(cleaned))


def is_preprint_venue(venue_text: str | None) -> bool:
    """Return True if the venue string denotes a preprint server or tech report."""
    cleaned = _clean_venue_for_match(venue_text)
    if not cleaned:
        return False
    return bool(PREPRINT_KEYWORDS_RE.search(cleaned))


def match_venue_entry(venue_text: str | None) -> VenueEntry | None:
    """Match a raw venue name (booktitle or journal) to a known VenueEntry.

    Note: Workshop venues return None here unless handled via match_canonical_venue_id
    so workshops are never confused with main conferences.
    """
    cleaned = _clean_venue_for_match(venue_text)
    if not cleaned or is_preprint_venue(cleaned):
        return None
    if is_workshop_venue(cleaned):
        return None
    # Note: TACL contains "Association for Computational Linguistics", so TACL is placed
    # carefully; check journal-specific TACL before ACL if needed.
    if re.search(
        r"\btacl\b|transactions\s+of\s+the\s+association\s+for\s+computational\s+linguistics",
        cleaned,
        re.IGNORECASE,
    ):
        return VENUE_BY_ID["TACL"]
    for entry in VENUE_ENTRIES:
        for pat in entry.patterns:
            if pat.search(cleaned):
                return entry
    return None


def get_canonical_venue_id(venue_text: str | None) -> str | None:
    """Extract canonical venue identifier (e.g., 'CVPR', 'CVPRW', 'TPAMI')."""
    cleaned = _clean_venue_for_match(venue_text)
    if not cleaned or is_preprint_venue(cleaned):
        return None
    if is_workshop_venue(cleaned):
        # Identify parent conference if recognizable, appending 'W' so CVPRW != CVPR
        for entry in VENUE_ENTRIES:
            if entry.tier == "MAIN_CONF":
                for pat in entry.patterns:
                    if pat.search(cleaned):
                        return f"{entry.canonical_id}W"
        if re.search(r"\bcvprw\b", cleaned, re.IGNORECASE):
            return "CVPRW"
        if re.search(r"\biccvw\b", cleaned, re.IGNORECASE):
            return "ICCVW"
        if re.search(r"\beccvw\b", cleaned, re.IGNORECASE):
            return "ECCVW"
        if re.search(r"\bicmlw\b", cleaned, re.IGNORECASE):
            return "ICMLW"
        if re.search(r"\b(?:neuripsw|nipsw)\b", cleaned, re.IGNORECASE):
            return "NeurIPSW"
        return "WORKSHOP"
    matched = match_venue_entry(cleaned)
    return matched.canonical_id if matched else None


def get_compact_venue_name(venue_text: str | None) -> str | None:
    """Return compact venue abbreviation (e.g. 'CVPR', 'IEEE TPAMI', 'CVPRW') if known."""
    if not venue_text:
        return None
    vid = get_canonical_venue_id(venue_text)
    if not vid:
        return None
    if vid in VENUE_BY_ID:
        return VENUE_BY_ID[vid].compact_abbr
    if vid.endswith("W") and vid[:-1] in VENUE_BY_ID:
        return f"{VENUE_BY_ID[vid[:-1]].compact_abbr}W"
    return None
