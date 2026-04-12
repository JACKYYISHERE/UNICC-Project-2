"""
build_rag_expert2.py
Expert 2 RAG Knowledge Base - Ingestion Script

读取 Ai_ACTS_ALL/ 下的 31 个 markdown 文件，自适应分块后存入 ChromaDB。

分块策略（根据实际文件结构）：
  GDPR P0 article 文件  -> ## Article N 级别（条款级，最精确）
  EU AI Act 文件        -> ## Page N 级别，但内嵌检测 ### Article N 提取标签
  NIST / OWASP 等       -> ## Page N 级别（PDF页码转换）

Collection：expert2_legal_compliance
Storage：   ./chroma_db_expert2/

运行方式：
    pip install chromadb sentence-transformers
    python build_rag_expert2.py
"""

import re
import hashlib
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

# ─── CONFIG ──────────────────────────────────────────────────────────────────

CHROMA_DIR      = "./chroma_db_expert2"
COLLECTION_NAME = "expert2_legal_compliance"
EMBED_MODEL     = "sentence-transformers/all-MiniLM-L6-v2"
AI_ACTS_DIR     = "Ai_ACTS_ALL"

# ─── SOURCE FILE REGISTRY ─────────────────────────────────────────────────────
# 格式：filename -> (priority, jurisdiction, relevance_tags)
# priority: P0 = 核心强制引用，P1 = 补充参考

SOURCE_REGISTRY = {
    # EU AI Act
    "EU_AI_Act_Chapter_I_Articles_1-4_General.md":      ("P0", "EU_AI_Act",   "ai_governance, definitions"),
    "EU_AI_Act_Chapter_II_Article_5_Prohibited.md":     ("P0", "EU_AI_Act",   "ai_governance, prohibited_practices, unacceptable_risk"),
    "EU_AI_Act_Chapter_III_Articles_6-51.md":           ("P0", "EU_AI_Act",   "ai_governance, high_risk, transparency, human_oversight, accountability"),
    "EU_AI_Act_Chapter_V_Articles_51-55_GPAI.md":       ("P0", "EU_AI_Act",   "ai_governance, gpai, general_purpose_ai"),
    "EU_AI_Act_Article_52_Transparency.md":             ("P0", "EU_AI_Act",   "ai_governance, transparency"),
    "EU_AI_Act_Annex_III_High-Risk_List.md":            ("P0", "EU_AI_Act",   "ai_governance, high_risk, risk_classification"),
    "EU_AI_Act_Annex_IV_Technical_Documentation.md":    ("P0", "EU_AI_Act",   "ai_governance, accountability, technical_documentation"),
    "EU_AI_Act_Recitals_1-182.md":                      ("P1", "EU_AI_Act",   "ai_governance"),
    # GDPR P0 - core articles (article-level structure)
    "P0_Article_4_Definitions.md":                      ("P0", "GDPR",        "data_protection, definitions"),
    "P0_Article_5_Principles_relating_to_process.md":   ("P0", "GDPR",        "data_protection, data_principles"),
    "P0_Article_6_Lawfulness_of_processing.md":         ("P0", "GDPR",        "data_protection, lawfulness, consent"),
    "P0_Article_9_Processing_of_special_categori.md":   ("P0", "GDPR",        "data_protection, special_categories, sensitive_data"),
    "P0_Article_22_Automated_individual_decision-.md":  ("P0", "GDPR",        "data_protection, automated_decision, profiling"),
    "P0_Article_25_Data_protection_by_design_and_.md":  ("P0", "GDPR",        "data_protection, privacy_by_design"),
    "P0_Article_35_Data_protection_impact_assessm.md":  ("P0", "GDPR",        "data_protection, dpia, risk_assessment"),
    "P0_Chapter_II_Principles.md":                      ("P0", "GDPR",        "data_protection, data_principles"),
    "P0_Chapter_III_Data_Subject_Rights.md":            ("P0", "GDPR",        "data_protection, data_subject_rights"),
    "P0_Chapter_IV_Controller_Processor.md":            ("P0", "GDPR",        "data_protection, accountability"),
    # GDPR P1 - supplementary chapters
    "P1_Article_13_Information_to_be_provided_-_t.md":  ("P1", "GDPR",        "data_protection, transparency"),
    "P1_Article_14_Information_to_be_provided_-_t.md":  ("P1", "GDPR",        "data_protection, transparency"),
    "P1_Article_89_Safeguards_for_processing_for_.md":  ("P1", "GDPR",        "data_protection"),
    "P1_Chapter_VI_Supervisory_Authorities.md":         ("P1", "GDPR",        "data_protection, accountability"),
    "P1_Chapter_VIII_Remedies_Penalties.md":            ("P1", "GDPR",        "data_protection, enforcement"),
    # GDPR P2 - general provisions & recitals
    "P2_Chapter_I_General_Provisions.md":               ("P1", "GDPR",        "data_protection, definitions"),
    "P2_Recital_71_Automated_Decision_Making.md":       ("P0", "GDPR",        "data_protection, automated_decision, profiling"),
    "P2_Recitals_1-173.md":                             ("P1", "GDPR",        "data_protection"),
    # International frameworks
    "NIST_AI_RMF.md":                                   ("P0", "NIST",        "ai_governance, risk_management, accountability"),
    "NIST_Adversarial_ML_Taxonomy.md":                  ("P1", "NIST",        "ai_governance, security_robustness"),
    "OWASP_LLM_Top_10_2025.md":                        ("P1", "OWASP",       "ai_governance, security_robustness"),
    "UNESCO_AI_Ethics.md":                              ("P0", "UNESCO",       "ai_governance, bias_fairness, human_oversight"),
    "UN_Human_Rights_Digital_Tech_Guidance.md":         ("P0", "UN",          "ai_governance, bias_fairness, human_rights"),
}

# ─── ARTICLE TAG EXTRACTION ───────────────────────────────────────────────────

_ARTICLE_KEYWORDS = {
    r"prohibit":                    ["prohibited_practices", "unacceptable_risk"],
    r"high.risk":                   ["high_risk", "risk_classification"],
    r"automated.*decision|profil":  ["automated_decision", "profiling"],
    r"consent":                     ["consent", "lawful_basis"],
    r"special categor":             ["special_categories", "sensitive_data"],
    r"privacy.by.design|data.minim":["privacy_by_design", "data_minimization"],
    r"impact.assessment|DPIA":      ["dpia", "risk_assessment"],
    r"transparency|explainab":      ["transparency", "explainability"],
    r"human.oversight|human.review":["human_oversight"],
    r"accuracy|robust":             ["accuracy", "robustness"],
    r"non.discriminat|bias|fairness":["bias_fairness"],
    r"accountab|responsib":         ["accountability"],
    r"data.governance|data.quality":["data_governance"],
    r"Article\s+(\d+)":             [],   # handled separately
}


def _extract_content_tags(text: str) -> list[str]:
    """从正文提取语义标签（关键词映射 + Article 编号）。"""
    tags = []
    tl = text.lower()
    for pattern, tag_list in _ARTICLE_KEYWORDS.items():
        if pattern == r"Article\s+(\d+)":
            for m in re.finditer(r"Article\s+(\d+)", text):
                tags.append(f"Art.{m.group(1)}")
        elif re.search(pattern, tl):
            tags.extend(tag_list)
    return list(dict.fromkeys(tags))


# ─── SECTION NORMALIZATION ───────────────────────────────────────────────────

def normalize_section(header: str, body: str, jurisdiction: str, filename: str = "") -> str:
    """
    把 section 名标准化为语义化格式。

    规则（按优先级）：
    1. header 本身已是 Article N 格式 -> 直接用（GDPR 专文件走这条）
    2. body 里有独立标题行 '^Article N' -> 用（真正的条款开头）
       注意：不用"第一个出现的 Article N"，那可能是交叉引用
    3. NIST 格式：GOVERN/MAP/MEASURE/MANAGE + 数字 -> 用具体编号
    4. NIST/UNESCO/UN/OWASP：用 body 第一行作为标识
    5. EU AI Act / GDPR 按页切割的大文件：保留 Page N，
       但加上来自文件名提取的条款范围作为上下文前缀
    6. 兜底：保留原 header
    """
    # 1. header 本身已经是 Article N 格式
    if re.match(r"^Article\s+\d+[a-z]?$", header.strip(), re.IGNORECASE):
        return header.strip()

    # 2. body 里有独立标题行（Article N 单独成行，是真正的条款开头）
    article_title = re.search(r"(?m)^Article\s+(\d+[a-z]?)\s*$", body)
    if article_title:
        return f"Article {article_title.group(1)}"

    # 3. NIST 函数编号（GOVERN 1.1 / MAP 2.3 等）
    nist_match = re.search(r"\b(GOVERN|MAP|MEASURE|MANAGE)\s+[\d.]+", body)
    if nist_match:
        return nist_match.group(0)

    # 4. NIST / UNESCO / UN / OWASP：用 body 第一行
    if jurisdiction in ("NIST", "UNESCO", "UN", "OWASP"):
        first_line = body.split("\n")[0].strip()[:50]
        return first_line if first_line else header

    # 5. 页码型 header（Page N）但来自 EU AI Act / GDPR 大文件
    #    加文件名里的条款范围或章节名作为前缀，保持准确性
    if re.match(r"^Page\s+\d+$", header.strip(), re.IGNORECASE):
        # 从文件名提取条款范围，如 "Articles_6-51" -> "Art.6-51"
        art_range = re.search(r"Article[s]?[_-](\d+[-–]\d+)", filename, re.IGNORECASE)
        if art_range:
            return f"Art.{art_range.group(1)} / {header.strip()}"
        # 从文件名提取单个条款，如 "Article_22" -> "Art.22"
        single_art = re.search(r"Article[_-](\d+)", filename, re.IGNORECASE)
        if single_art:
            return f"Article {single_art.group(1)}"
        # 从文件名提取章节编号，如 "Chapter_II" -> "Ch.II"
        chapter = re.search(r"Chapter[_-]([IVX]+)", filename, re.IGNORECASE)
        if chapter:
            return f"Ch.{chapter.group(1)} / {header.strip()}"
        # 从文件名提取 Recitals，如 "Recitals_1-173" -> "Recitals"
        if re.search(r"Recital", filename, re.IGNORECASE):
            return f"Recitals / {header.strip()}"
        return header.strip()

    # 6. 兜底：保留原 header
    return header


# ─── CHUNKING ────────────────────────────────────────────────────────────────

def chunk_file(filepath: Path, priority: str, jurisdiction: str, relevance: str) -> list[dict]:
    """
    自适应分块策略：
    - 如果文件有 ### Article N 级别 header -> 优先按 ### 切割（精确到条款）
    - 否则退化到 ## 级别切割（Page N 级，加文件名前缀保持诚实）
    """
    text = filepath.read_text(encoding="utf-8")
    filename = filepath.name

    global_tags = [t.strip() for t in relevance.split(",") if t.strip()]

    # 判断文件是否有条款级别的 ### Article N header
    has_article_headers = bool(
        re.search(r"(?m)^### (?:Article|CHAPTER|GOVERN|MAP|MEASURE|MANAGE)\s+", text)
    )

    if has_article_headers:
        # 按 ### 切割，精确到条款
        parts = re.split(r"(?m)^(### .+)$", text)
        level = "###"
    else:
        # 退化到 ## 切割（Page N 级）
        parts = re.split(r"(?m)^(## .+)$", text)
        level = "##"

    chunks = []
    for i in range(1, len(parts) - 1, 2):
        header_raw = parts[i]
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        header_clean = header_raw.lstrip("# ").strip()

        # 跳过无实质内容的块（< 80 字符正文）
        if len(body) < 80:
            continue

        # ### 级别：跳过 CHAPTER 章节标题块（只是章节名，无实质内容）
        if level == "###" and re.match(r"^CHAPTER\s+", header_clean, re.IGNORECASE):
            continue

        # ## 级别：跳过纯页眉/页脚块
        if level == "##" and _is_metadata_chunk(header_clean, body):
            continue

        # 标准化 section 名
        if level == "###":
            # ### Article N 直接提取
            art_match = re.match(r"^Article\s+(\d+[a-z]?)\b", header_clean, re.IGNORECASE)
            if art_match:
                norm_section = f"Article {art_match.group(1)}"
            else:
                # GOVERN 1.1 / MAP 2.3 等
                nist_match = re.match(r"(GOVERN|MAP|MEASURE|MANAGE)\s+[\d.]+", header_clean)
                norm_section = nist_match.group(0) if nist_match else header_clean[:60]
        else:
            norm_section = normalize_section(header_clean, body, jurisdiction, filename)

        # 构建 chunk 内容
        enriched = (
            f"[Source: {filename} | Section: {norm_section} | "
            f"Jurisdiction: {jurisdiction}]\n\n"
            f"{norm_section}\n\n{body}"
        ).strip()

        inline_tags = _extract_content_tags(body)
        combined = list(dict.fromkeys(global_tags + inline_tags))

        chunks.append({
            "source":       filename,
            "section":      norm_section,
            "content":      enriched,
            "priority":     priority,
            "jurisdiction": jurisdiction,
            "relevance":    relevance,
            "tags":         combined,
        })

    return chunks


def _is_metadata_chunk(header: str, body: str) -> bool:
    """判断是否是没有实质内容的页码/页眉块。"""
    # EU AI Act / GDPR PDF 转换产物：Page N 块里只有页眉
    page_only_patterns = [
        r"^Page \d+$",
        r"^\d+$",
    ]
    for p in page_only_patterns:
        if re.match(p, header.strip()):
            # body 里实质内容很少（主要是 "EN OJ L..." 之类页眉）
            real_lines = [line for line in body.split("\n") if len(line.strip()) > 30]
            if len(real_lines) < 3:
                return True
    return False


def make_chunk_id(source: str, section: str, index: int) -> str:
    """加入 index 防止同文件内重名 section 碰撞。"""
    key = f"{source}::{section}::{index}"
    return hashlib.md5(key.encode()).hexdigest()


# ─── MAIN ────────────────────────────────────────────────────────────────────

def build() -> None:
    print("=" * 60)
    print("Expert 2 RAG - Building Legal Compliance Knowledge Base")
    print("=" * 60)

    base = Path(__file__).parent
    acts_dir = base / AI_ACTS_DIR

    if not acts_dir.exists():
        raise FileNotFoundError(f"Knowledge base directory not found: {acts_dir}")

    all_chunks: list[dict] = []
    missing = []
    skipped = []

    for filename, (priority, jurisdiction, relevance) in SOURCE_REGISTRY.items():
        fp = acts_dir / filename
        if not fp.exists():
            missing.append(filename)
            print(f"  ⚠ MISSING:  {filename}")
            continue

        chunks = chunk_file(fp, priority, jurisdiction, relevance)
        if not chunks:
            skipped.append(filename)
            print(f"  ⚠ NO CHUNKS: {filename} (check file structure)")
            continue

        print(f"  [{priority}][{jurisdiction:<12}] {filename}: {len(chunks)} chunks")
        all_chunks.extend(chunks)

    print(f"\nTotal: {len(all_chunks)} chunks  |  Missing: {len(missing)}  |  Skipped: {len(skipped)}")

    if not all_chunks:
        print("ERROR: No chunks generated. Aborting.")
        return

    # ── ChromaDB ──────────────────────────────────────────────────────────────
    chroma_path = str(base / CHROMA_DIR)
    client = chromadb.PersistentClient(path=chroma_path)

    try:
        client.delete_collection(COLLECTION_NAME)
        print(f"\nDropped existing '{COLLECTION_NAME}'")
    except Exception:
        pass

    embed_fn = SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
    collection = client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"},
    )

    # ── 批量写入（每批 200） ──────────────────────────────────────────────────
    batch_size = 200
    for batch_start in range(0, len(all_chunks), batch_size):
        batch = all_chunks[batch_start : batch_start + batch_size]
        collection.add(
            ids=[
                make_chunk_id(c["source"], c["section"], batch_start + j)
                for j, c in enumerate(batch)
            ],
            documents=[c["content"] for c in batch],
            metadatas=[
                {
                    "source":       c["source"],
                    "section":      c["section"],
                    "priority":     c["priority"],
                    "jurisdiction": c["jurisdiction"],
                    "relevance":    c["relevance"],
                    "tags":         ", ".join(c["tags"]),
                    # 布尔过滤字段（ChromaDB 只支持 $eq，不支持 $contains）
                    "is_p0":                   c["priority"] == "P0",
                    "is_eu_ai_act":            c["jurisdiction"] == "EU_AI_Act",
                    "is_gdpr":                 c["jurisdiction"] == "GDPR",
                    "is_data_protection":      "data_protection" in c["relevance"],
                    "is_ai_governance":        "ai_governance" in c["relevance"],
                    "is_high_risk":            "high_risk" in c["tags"],
                    "is_automated_decision":   "automated_decision" in c["tags"],
                }
                for c in batch
            ],
        )
        print(f"  Ingested batch {batch_start // batch_size + 1}: {len(batch)} chunks")

    print(f"\n[OK] {len(all_chunks)} chunks -> '{COLLECTION_NAME}'")
    print(f"  Storage: {chroma_path}")

    # ── 简要统计 ──────────────────────────────────────────────────────────────
    from collections import Counter
    by_jur = Counter(c["jurisdiction"] for c in all_chunks)
    by_pri = Counter(c["priority"] for c in all_chunks)
    print("\nBreakdown by jurisdiction:")
    for k, v in sorted(by_jur.items()):
        print(f"    {k:<15} {v:>4} chunks")
    print("Breakdown by priority:")
    for k, v in sorted(by_pri.items()):
        print(f"    {k:<6} {v:>4} chunks")
    print("\nDone. Run test_rag_expert2.py to verify.")


if __name__ == "__main__":
    build()
