import { CandidateRecord, DecisionPayload, EntryAuditResult, StyleMode } from "../types";

const PROTECTED_PROPER_NOUNS = new Set([
  "gaussian",
  "gaussians",
  "bayesian",
  "markov",
  "markovian",
  "fourier",
  "laplacian",
  "laplace",
  "euclidean",
  "riemannian",
  "hilbert",
  "poisson",
  "bernoulli",
  "boltzmann",
  "langevin",
  "wasserstein",
  "sinkhorn",
  "kalman",
  "monte",
  "carlo",
  "sobel",
  "canny",
  "hough",
  "gabor",
  "chebyshev",
  "legendre",
  "hermite",
  "jacobian",
  "hessian",
  "lagrangian",
  "hamiltonian",
  "cauchy",
  "dirichlet",
  "neumann",
  "euler",
  "runge",
  "kutta",
  "newton",
  "lorentz",
  "minkowski",
  "hausdorff",
  "jensen",
  "shannon",
  "kullback",
  "leibler",
  "mahalanobis",
  "frobenius",
  "hadamard",
  "kronecker",
  "toeplitz",
  "cholesky",
  "moore",
  "penrose",
  "turing",
  "boolean",
  "transformer",
  "transformers",
  "swin",
  "mamba",
  "llama",
  "mistral",
  "mixtral",
  "qwen",
  "python",
  "cuda",
  "linux",
  "windows",
  "kitti",
  "mnist",
  "cifar",
  "coco",
]);

function needsWordProtection(word: string): boolean {
  if (word.length < 2) return false;
  const alphas = [...word].filter((c) => /[A-Za-z]/.test(c));
  if (alphas.length === 0) return false;
  const upperCount = alphas.filter((c) => c >= "A" && c <= "Z").length;
  const hasDigit = /\d/.test(word);
  if (upperCount >= 2) return true;
  if (hasDigit && upperCount >= 1) return true;
  if (word[0] >= "a" && word[0] <= "z" && upperCount >= 1) return true;
  const base = word.replace(/\++$/, "").toLowerCase();
  if (word[0] >= "A" && word[0] <= "Z" && PROTECTED_PROPER_NOUNS.has(base)) {
    return true;
  }
  return false;
}

function protectCompoundToken(token: string): string {
  if (!token.includes("-") && !token.includes("/")) {
    return needsWordProtection(token) ? `{${token}}` : token;
  }
  if (/^[A-Z]-Net(?:s)?$/.test(token)) {
    return `{${token}}`;
  }
  const parts = token.split(/([-+/])/);
  const wordParts = parts.filter((p) => p && !"-+/".includes(p));
  if (wordParts.length >= 2) {
    const hasStrong = wordParts.some((p) => needsWordProtection(p));
    const allTech = wordParts.every(
      (p) =>
        needsWordProtection(p) ||
        (p.length === 1 && p >= "A" && p <= "Z") ||
        /^\d+$/.test(p)
    );
    if (hasStrong && allTech) {
      return `{${token}}`;
    }
  }
  return parts
    .map((p) => {
      if (!p || "-+/".includes(p)) return p;
      return needsWordProtection(p) ? `{${p}}` : p;
    })
    .join("");
}

export function protectTitleCaseClient(title: string): string {
  if (!title) return title;
  const trimmed = title.trim();
  if (trimmed.startsWith("{") && trimmed.endsWith("}")) {
    let d = 0;
    let closedEarly = false;
    for (let i = 0; i < trimmed.length; i++) {
      if (trimmed[i] === "\\") {
        i++;
        continue;
      }
      if (trimmed[i] === "{") d++;
      else if (trimmed[i] === "}") {
        d--;
        if (d === 0 && i < trimmed.length - 1) {
          closedEarly = true;
          break;
        }
      }
    }
    if (!closedEarly && d === 0) return title;
  }

  let out = "";
  let plain = "";
  let braceDepth = 0;
  let inMath = false;

  const flushPlain = () => {
    if (!plain) return;
    out += plain.replace(/[A-Za-z0-9]+(?:[-+/][A-Za-z0-9]+)*\+*/g, (m) =>
      protectCompoundToken(m)
    );
    plain = "";
  };

  for (let i = 0; i < title.length; i++) {
    const ch = title[i];
    if (ch === "\\" && i + 1 < title.length) {
      flushPlain();
      let end = i + 1;
      if (/[A-Za-z]/.test(title[end])) {
        while (end < title.length && /[A-Za-z]/.test(title[end])) end++;
      } else {
        end++;
      }
      out += title.slice(i, end);
      i = end - 1;
      continue;
    }
    if (ch === "$" && braceDepth === 0) {
      flushPlain();
      inMath = !inMath;
      out += ch;
      continue;
    }
    if (ch === "{") {
      if (braceDepth === 0 && !inMath) flushPlain();
      braceDepth++;
      out += ch;
      continue;
    }
    if (ch === "}") {
      if (braceDepth > 0) braceDepth--;
      out += ch;
      continue;
    }
    if (braceDepth === 0 && !inMath) {
      plain += ch;
    } else {
      out += ch;
    }
  }
  flushPlain();
  return out;
}

export function rekeyBibtexClient(bibtex: string, targetKey: string): string {
  return bibtex.replace(
    /^(\s*@\s*[A-Za-z0-9_-]+\s*[{(]\s*)([^,\s})]+)(\s*,)/,
    `$1${targetKey}$3`
  );
}

/**
 * Compute instant live preview of a candidate's BibTeX honoring styleMode,
 * protectTitleCase toggle, and optional user cite_key override without network calls.
 */
export function renderCandidateLivePreview(
  cand: CandidateRecord,
  citeKey: string,
  styleMode: StyleMode,
  protectTitleCase: boolean
): string {
  let base =
    styleMode === "compact" && cand.compact_bibtex
      ? cand.compact_bibtex
      : cand.canonical_bibtex;

  if (!base) return "";
  base = rekeyBibtexClient(base, citeKey);

  const rawTitle = cand.raw_publisher_fields?.title;
  if (!rawTitle) return base;

  const cleanRawTitle =
    rawTitle.endsWith(".") && !rawTitle.endsWith("...")
      ? rawTitle.slice(0, -1).trimEnd()
      : rawTitle;
  const escapedRaw = cleanRawTitle
    .replace(/(?<!\\)&amp;/g, "&")
    .replace(/(?<!\\)&/g, "\\&")
    .replace(/(?<!\\)%/g, "\\%")
    .replace(/\s+/g, " ")
    .trim();

  const desiredTitle = protectTitleCase
    ? protectTitleCaseClient(escapedRaw)
    : escapedRaw;

  return base.replace(
    /^(\s*title\s*=\s*\{)(.*)(\},?\s*)$/m,
    (_match, p1, _oldTitle, p3) => `${p1}${desiredTitle}${p3}`
  );
}

export function computeTargetEntryBibtex(
  entry: EntryAuditResult,
  decisionPayload: DecisionPayload | undefined,
  styleMode: StyleMode,
  protectTitleCase: boolean
): string {
  const dec = decisionPayload?.decision ?? entry.decision;
  const targetKey = decisionPayload?.override_cite_key || entry.cite_key;

  if (dec === "custom") {
    const custom = decisionPayload?.custom_bibtex ?? entry.custom_bibtex;
    if (custom && custom.trim()) {
      return decisionPayload?.override_cite_key
        ? rekeyBibtexClient(custom.trim(), targetKey)
        : custom.trim();
    }
  }

  if (dec === "accept" && entry.candidates.length > 0) {
    const idx =
      decisionPayload?.selected_candidate_idx ?? entry.selected_candidate_idx ?? 0;
    const safeIdx = idx >= 0 && idx < entry.candidates.length ? idx : 0;
    const cand = entry.candidates[safeIdx];
    const rendered = renderCandidateLivePreview(
      cand,
      targetKey,
      styleMode,
      protectTitleCase
    );
    if (rendered.trim()) return rendered.trim();
  }

  return entry.original_bibtex.trim();
}

export function isEntryAlreadyIdentical(
  entry: EntryAuditResult,
  styleMode: StyleMode,
  protectTitleCase: boolean
): boolean {
  if (entry.candidates.length === 0) return false;
  const cand = entry.candidates[entry.selected_candidate_idx ?? 0] ?? entry.candidates[0];
  const rendered = renderCandidateLivePreview(
    cand,
    entry.cite_key,
    styleMode,
    protectTitleCase
  );
  const norm = (s: string) => s.replace(/\r\n/g, "\n").trim();
  return norm(entry.original_bibtex) === norm(rendered);
}

export interface DiffLine {
  type: "same" | "removed" | "added";
  text: string;
  lineNo?: number;
}

export function computeSideBySideDiff(
  leftText: string,
  rightText: string
): { leftLines: DiffLine[]; rightLines: DiffLine[] } {
  const a = leftText.replace(/\r\n/g, "\n").split("\n");
  const b = rightText.replace(/\r\n/g, "\n").split("\n");
  const m = a.length;
  const n = b.length;

  // Standard LCS DP matrix (entries are ~10-25 lines so O(m*n) is <0.05ms)
  const dp: number[][] = Array.from({ length: m + 1 }, () =>
    new Array(n + 1).fill(0)
  );
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      if (a[i].trim() === b[j].trim()) {
        dp[i][j] = 1 + dp[i + 1][j + 1];
      } else {
        dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }
  }

  const leftLines: DiffLine[] = [];
  const rightLines: DiffLine[] = [];
  let i = 0;
  let j = 0;
  let lNo = 1;
  let rNo = 1;

  while (i < m && j < n) {
    if (a[i].trim() === b[j].trim()) {
      const exactSame = a[i] === b[j];
      leftLines.push({
        type: exactSame ? "same" : "removed",
        text: a[i],
        lineNo: lNo++,
      });
      rightLines.push({
        type: exactSame ? "same" : "added",
        text: b[j],
        lineNo: rNo++,
      });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      leftLines.push({ type: "removed", text: a[i], lineNo: lNo++ });
      i++;
    } else {
      rightLines.push({ type: "added", text: b[j], lineNo: rNo++ });
      j++;
    }
  }
  while (i < m) {
    leftLines.push({ type: "removed", text: a[i++], lineNo: lNo++ });
  }
  while (j < n) {
    rightLines.push({ type: "added", text: b[j++], lineNo: rNo++ });
  }

  return { leftLines, rightLines };
}
