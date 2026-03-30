"""
repo_analyzer.py
================
Collect key files from a GitHub URL or a local directory, then call an LLM
(Claude or vLLM) to produce a structured system-description string suitable
for feeding directly into evaluate_agent(system_description=...).

Usage (Python):
    from council.repo_analyzer import analyze_repo

    description = analyze_repo(
        source  = "https://github.com/owner/repo",  # or "/path/to/local/dir"
        backend = "vllm",     # or "claude" (fallback/test)
    )
    report = evaluate_agent(agent_id="my-sys", system_description=description)

Usage (HTTP):
    POST /analyze/repo   {"source": "https://github.com/...", "backend": "claude"}
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional


# ── tunables ──────────────────────────────────────────────────────────────────

# Files we always try to fetch first, in priority order
_PRIORITY_FILES = [
    "README.md", "README.rst", "README.txt", "README",
    "requirements.txt", "setup.py", "pyproject.toml", "setup.cfg",
    "package.json",
    "Dockerfile", "docker-compose.yml",
    ".env.example",
]

# Source extensions to sample
_SOURCE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".java", ".rs", ".rb"}

# Directories to always skip when walking
_SKIP_DIRS = {"node_modules", "__pycache__", ".git", "dist", "build", "vendor", ".venv", "venv"}

_MAX_FILE_CHARS   = 2_000   # chars per sampled source file
_MAX_README_CHARS = 4_000   # chars for README
_MAX_CONTEXT_CHARS = 14_000  # total chars sent to LLM


# ── helpers ───────────────────────────────────────────────────────────────────

def _fetch_url(url: str, headers: Optional[dict] = None, timeout: int = 15) -> Optional[str]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def _parse_github_url(url: str) -> tuple[str, str]:
    """Return (owner, repo) from any recognised GitHub URL format."""
    url = url.strip().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    for prefix in ("https://", "http://", "git@", "github.com:"):
        if url.startswith(prefix):
            url = url[len(prefix):]
    if url.startswith("github.com/"):
        url = url[len("github.com/"):]
    parts = url.split("/")
    if len(parts) < 2:
        raise ValueError(
            f"Cannot parse GitHub URL: {url!r}. Expected format: https://github.com/owner/repo"
        )
    return parts[0], parts[1]


def _should_skip(path: str) -> bool:
    return any(seg in path.split("/") for seg in _SKIP_DIRS)


# ── GitHub collector ──────────────────────────────────────────────────────────

def fetch_github_repo(
    url: str,
    github_token: Optional[str] = None,
) -> dict[str, str]:
    """
    Fetch key files from a public (or token-accessible) GitHub repository.
    Returns {relative_path: content_str}.
    """
    owner, repo = _parse_github_url(url)
    headers: dict[str, str] = {"Accept": "application/vnd.github.v3+json"}
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    api_base = f"https://api.github.com/repos/{owner}/{repo}"

    # ── default branch ────────────────────────────────────────────────────────
    default_branch = "main"
    repo_info_text = _fetch_url(api_base, headers=headers)
    if repo_info_text:
        try:
            default_branch = json.loads(repo_info_text).get("default_branch", "main")
        except Exception:
            pass

    # ── full file tree ────────────────────────────────────────────────────────
    tree_url  = f"{api_base}/git/trees/{default_branch}?recursive=1"
    tree_text = _fetch_url(tree_url, headers=headers)
    all_paths: list[str] = []
    if tree_text:
        try:
            all_paths = [
                item["path"]
                for item in json.loads(tree_text).get("tree", [])
                if item.get("type") == "blob" and not _should_skip(item["path"])
            ]
        except Exception:
            pass

    raw_base = f"https://raw.githubusercontent.com/{owner}/{repo}/{default_branch}"
    collected: dict[str, str] = {}
    total_chars = 0

    def _add(path: str, max_chars: int = _MAX_FILE_CHARS) -> None:
        nonlocal total_chars
        if total_chars >= _MAX_CONTEXT_CHARS or path in collected:
            return
        text = _fetch_url(f"{raw_base}/{path}")
        if text:
            snippet = text[:max_chars]
            collected[path] = snippet
            total_chars += len(snippet)

    # ── priority files ────────────────────────────────────────────────────────
    for fname in _PRIORITY_FILES:
        if fname in all_paths:
            max_c = _MAX_README_CHARS if fname.lower().startswith("readme") else _MAX_FILE_CHARS
            _add(fname, max_chars=max_c)

    # ── directory tree ────────────────────────────────────────────────────────
    if all_paths:
        collected["__directory_tree__"] = "\n".join(sorted(all_paths)[:300])

    # ── sample source files ───────────────────────────────────────────────────
    source_files = sorted(
        [p for p in all_paths if Path(p).suffix in _SOURCE_EXTS],
        key=lambda p: (p.count("/"), p),
    )
    for path in source_files[:10]:
        if total_chars < _MAX_CONTEXT_CHARS:
            _add(path)

    return collected


# ── local directory collector ─────────────────────────────────────────────────

def read_local_repo(path: str) -> dict[str, str]:
    """
    Read key files from a local directory.
    Returns {relative_path: content_str}.
    """
    root = Path(path).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Path does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    collected: dict[str, str] = {}
    total_chars = 0

    def _add(p: Path, max_chars: int = _MAX_FILE_CHARS) -> None:
        nonlocal total_chars
        if total_chars >= _MAX_CONTEXT_CHARS:
            return
        rel = str(p.relative_to(root))
        if rel in collected:
            return
        try:
            snippet = p.read_text(encoding="utf-8", errors="replace")[:max_chars]
            collected[rel] = snippet
            total_chars += len(snippet)
        except Exception:
            pass

    # ── priority files ────────────────────────────────────────────────────────
    for fname in _PRIORITY_FILES:
        p = root / fname
        if p.exists():
            max_c = _MAX_README_CHARS if fname.lower().startswith("readme") else _MAX_FILE_CHARS
            _add(p, max_chars=max_c)

    # ── directory tree ────────────────────────────────────────────────────────
    tree_lines: list[str] = []
    for item in sorted(root.rglob("*")):
        if item.is_file():
            rel = str(item.relative_to(root))
            if not any(seg in rel.split(os.sep) for seg in _SKIP_DIRS):
                tree_lines.append(rel)
                if len(tree_lines) >= 300:
                    break
    if tree_lines:
        collected["__directory_tree__"] = "\n".join(tree_lines)

    # ── sample source files ───────────────────────────────────────────────────
    source_files = sorted(
        [
            p for p in root.rglob("*")
            if p.is_file()
            and p.suffix in _SOURCE_EXTS
            and not any(seg in str(p.relative_to(root)).split(os.sep) for seg in _SKIP_DIRS)
        ],
        key=lambda p: (len(p.parts), p.name),
    )
    for p in source_files[:10]:
        if total_chars < _MAX_CONTEXT_CHARS:
            _add(p)

    return collected


# ── LLM call ──────────────────────────────────────────────────────────────────

_CATEGORIES = [
    "Humanitarian Aid", "Peacekeeping", "Child Protection", "Labor Rights",
    "Governance", "Language & Translation", "Healthcare", "Education", "Other",
]
_DEPLOY_ZONES = [
    "Active Conflict Zone", "Post-Conflict Zone", "Development Context",
    "UN Headquarters", "Field Office", "Global/Multi-Region",
]

_SYSTEM_PROMPT = """\
You are an AI safety analyst for UNICC. Analyse the provided content and return
a JSON object (and ONLY a JSON object — no markdown fences, no commentary) with
exactly these keys:

  system_description : string  (300-600 words, comprehensive factual description
                                 covering purpose, capabilities, architecture,
                                 data flows, PII handling, and any visible risk
                                 indicators or safety-relevant design choices)
  capabilities       : string  (one sentence or short comma-separated list of
                                 the system's key technical capabilities)
  data_sources       : string  (brief description of data inputs / APIs / databases
                                 the system consumes; empty string if not apparent)
  human_oversight    : string  (any human review or override mechanisms visible
                                 in the codebase; empty string if none apparent)
  category           : string  (pick the single best match from:
                                 Humanitarian Aid | Peacekeeping | Child Protection |
                                 Labor Rights | Governance | Language & Translation |
                                 Healthcare | Education | Other)
  deploy_zone        : string  (pick the single best match from:
                                 Active Conflict Zone | Post-Conflict Zone |
                                 Development Context | UN Headquarters |
                                 Field Office | Global/Multi-Region)

Base every field strictly on the provided content. Do not speculate.
Return valid JSON only.
"""

_USER_TEMPLATE = """\
Source: {source_label}

=== DIRECTORY TREE ===
{tree}

=== KEY FILES ===
{files_text}

Return the JSON object now.
"""

_TEXT_TEMPLATE = """\
Source: uploaded document / pasted text

=== CONTENT ===
{text}

Return the JSON object now.
"""

_EMPTY_RESULT: dict = {
    "system_description": "",
    "capabilities": "",
    "data_sources": "",
    "human_oversight": "",
    "category": "Other",
    "deploy_zone": "Global/Multi-Region",
}


def _parse_structured(raw: str) -> dict:
    """Extract the JSON object from the LLM response, tolerating minor noise."""
    raw = raw.strip()
    # Strip markdown code fences if the model added them
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(l for l in lines if not l.startswith("```")).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try to find the first {...} block
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start != -1 and end > start:
            try:
                data = json.loads(raw[start:end])
            except Exception:
                return {**_EMPTY_RESULT, "system_description": raw}
        else:
            return {**_EMPTY_RESULT, "system_description": raw}

    # Coerce category / deploy_zone to valid enum values
    cat = data.get("category", "Other")
    if cat not in _CATEGORIES:
        cat = "Other"
    zone = data.get("deploy_zone", "Global/Multi-Region")
    if zone not in _DEPLOY_ZONES:
        zone = "Global/Multi-Region"

    return {
        "system_description": str(data.get("system_description", "")),
        "capabilities":       str(data.get("capabilities", "")),
        "data_sources":       str(data.get("data_sources", "")),
        "human_oversight":    str(data.get("human_oversight", "")),
        "category":           cat,
        "deploy_zone":        zone,
    }


def _call_llm(
    user_message: str,
    backend: str,
    vllm_base_url: str,
    vllm_model: str,
    anthropic_api_key: Optional[str],
) -> str:
    if backend == "vllm":
        from council.slm_backends import VLLMChatClient
        client = VLLMChatClient(base_url=vllm_base_url, model=vllm_model)
        response = client.messages.create(
            model=vllm_model,
            max_tokens=1200,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text if response.content else ""
    else:
        import anthropic
        key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise EnvironmentError("ANTHROPIC_API_KEY is not set.")
        claude = anthropic.Anthropic(api_key=key)
        response = claude.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1200,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text if response.content else ""


def generate_system_description(
    files: dict[str, str],
    source_label: str = "unknown",
    backend: str = "vllm",
    vllm_base_url: str = "http://localhost:8000",
    vllm_model: str = "meta-llama/Meta-Llama-3-70B-Instruct",
    anthropic_api_key: Optional[str] = None,
) -> dict:
    """
    Call an LLM to turn collected repo files into a structured dict.
    Modifies `files` in-place (removes __directory_tree__ key).
    Returns a dict with keys: system_description, capabilities,
    data_sources, human_oversight, category, deploy_zone.
    """
    tree = files.pop("__directory_tree__", "")
    files_parts = [f"--- {path} ---\n{content}" for path, content in files.items()]
    files_text = "\n\n".join(files_parts)

    user_message = _USER_TEMPLATE.format(
        source_label=source_label,
        tree=tree[:3_000] if tree else "(not available)",
        files_text=files_text[:9_000] if files_text else "(not available)",
    )
    raw = _call_llm(user_message, backend, vllm_base_url, vllm_model, anthropic_api_key)
    return _parse_structured(raw)


def analyze_text(
    text: str,
    source_label: str = "pasted text",
    backend: str = "vllm",
    vllm_base_url: str = "http://localhost:8000",
    vllm_model: str = "meta-llama/Meta-Llama-3-70B-Instruct",
    anthropic_api_key: Optional[str] = None,
) -> dict:
    """
    Analyze raw text (pasted description or parsed PDF/Markdown) and return
    the same structured dict as generate_system_description.
    """
    user_message = _TEXT_TEMPLATE.format(text=text[:10_000])
    raw = _call_llm(user_message, backend, vllm_base_url, vllm_model, anthropic_api_key)
    return _parse_structured(raw)


# ── public entry point ────────────────────────────────────────────────────────

def analyze_repo(
    source: str,
    backend: str = "vllm",
    vllm_base_url: str = "http://localhost:8000",
    vllm_model: str = "meta-llama/Meta-Llama-3-70B-Instruct",
    github_token: Optional[str] = None,
    anthropic_api_key: Optional[str] = None,
) -> dict:
    """
    High-level entry point — returns a structured dict with keys:
    system_description, capabilities, data_sources, human_oversight,
    category, deploy_zone.

    Args:
        source:        GitHub URL (https://github.com/owner/repo) or local path.
        backend:       'claude' or 'vllm'.
        vllm_base_url: vLLM inference server URL (only used when backend='vllm').
        vllm_model:    Model name (only used when backend='vllm').
        github_token:  Optional GitHub PAT for private repos.
        anthropic_api_key: Optional; falls back to ANTHROPIC_API_KEY env var.
    """
    source = source.strip()
    is_github = source.startswith("http") or "github.com" in source

    if is_github:
        files = fetch_github_repo(source, github_token=github_token)
        label = source
    else:
        files = read_local_repo(source)
        label = Path(source).name

    if not files:
        raise ValueError(
            f"No files collected from: {source!r}. "
            "Check the URL/path is correct and the repository is accessible."
        )

    return generate_system_description(
        files,
        source_label=label,
        backend=backend,
        vllm_base_url=vllm_base_url,
        vllm_model=vllm_model,
        anthropic_api_key=anthropic_api_key,
    )
