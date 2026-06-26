"""
FactExtractionAgent — 从上传资料中提取公司业务事实
职责：只提取资料里明确写到的内容，不扩展、不推断、不补充。
输出写入 company_facts 和 business_dictionary，is_active=False，等待人工确认。
"""
import json
import logging
import os
import sys
from pathlib import Path

from services.llm import LLMRouter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from database import (
    save_company_fact, save_dictionary_term, list_company_facts,
)

logger = logging.getLogger(__name__)


# ── 文件内容读取工具 ───────────────────────────────────────────────

def _read_file_content(file_path: str) -> str:
    """读取文件内容，支持 .txt .md .html .py。docx / pdf 需要额外库。"""
    path = Path(file_path)
    suffix = path.suffix.lower()

    if not path.exists():
        return f"[文件不存在: {file_path}]"

    try:
        if suffix in (".txt", ".md", ".csv"):
            return path.read_text(encoding="utf-8", errors="ignore")

        elif suffix in (".html", ".htm"):
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(path.read_bytes(), "html.parser")
            # 移除 script / style
            for tag in soup(["script", "style"]):
                tag.decompose()
            return soup.get_text(separator="\n", strip=True)

        elif suffix == ".py":
            return path.read_text(encoding="utf-8", errors="ignore")

        elif suffix == ".docx":
            try:
                from docx import Document
                doc = Document(str(path))
                return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            except Exception as e:
                return f"[docx 读取失败: {e}]"

        elif suffix == ".pdf":
            try:
                import pdfplumber
                text_parts = []
                with pdfplumber.open(str(path)) as pdf:
                    for page in pdf.pages:
                        text_parts.append(page.extract_text() or "")
                return "\n".join(text_parts)
            except Exception as e:
                return f"[pdf 读取失败: {e}]"

        else:
            # 尝试 utf-8 文本读取
            try:
                return path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                return f"[不支持的文件格式: {suffix}]"

    except Exception as e:
        return f"[读取失败: {e}]"


# ── Agent 主类 ─────────────────────────────────────────────────────

CATEGORY_TO_FACT_TYPE = {
    "00_公司事实源":    "公司基础事实",
    "01_部门职责":      "部门事实",
    "02_产品体系":      "产品事实",
    "03_销售话术":      "销售事实",
    "04_客户异议":      "客户异议事实",
    "05_风控表达":      "风控事实",
    "06_学管交付":      "学管事实",
    "07_老师储备":      "老师资源事实",
    "08_订单咨询数据说明": "订单数据事实",
    "09_优秀内容样例":  "内容风格事实",
    "10_禁用表达":      "禁用表达事实",
    "11_组织命名规则":  "部门事实",
}

EXTRACTION_PROMPT = """\
你是一个业务事实提取助手，任务是从公司内部资料中提取**明确写到**的事实。

## 严格规则
1. **只提取资料里明确写到的内容**，不要推断、扩展、补充任何没写的内容。
2. 如果资料不完整，把缺失项放入 missing_information，不要自己补充。
3. 每条事实必须保留 source_section（来自资料哪个章节/段落）。
4. confidence 判断标准：
   - high：资料中有明确定义或数字
   - medium：资料中有描述但不够精确
   - low：资料中只是提到，没有详细说明
5. 禁止输出资料中没有的产品名、部门名、承诺语言。

## 资料来源
- 文件路径：{source_file}
- 资料分类：{category}
- 推断 fact_type：{fact_type}

## 资料内容
{content}

## 输出格式（纯 JSON，不要 markdown 代码块）
{{
  "facts": [
    {{
      "fact_type": "{fact_type}",
      "title": "简短标题（15字内）",
      "content": "事实内容（原文或高度忠实原文的摘录）",
      "source_section": "来自资料哪个章节或段落",
      "confidence": "high|medium|low"
    }}
  ],
  "dictionary_terms": [
    {{
      "term_type": "部门名称|产品名称|服务类型|客户类型|风控词|渠道名称",
      "standard_term": "标准词",
      "aliases": ["别名1", "别名2"],
      "forbidden_terms": ["禁止用词"],
      "description": "资料中的定义或描述"
    }}
  ],
  "missing_information": ["缺少什么信息"]
}}

只输出 JSON，不要其他任何文字。"""


class FactExtractionAgent:
    def __init__(self, config: dict = None):
        self.config = config or {}
        self._router = LLMRouter()

    def extract(self, file_path: str, category: str = None) -> dict:
        """
        从文件提取事实并写入数据库（is_active=False）。
        返回 {"facts_saved": N, "terms_saved": N, "missing": [...], "error": None}
        """
        path = Path(file_path)
        if not path.exists():
            return {"facts_saved": 0, "terms_saved": 0, "missing": [], "error": f"文件不存在: {file_path}"}

        # 自动推断分类
        if not category:
            for part in path.parts:
                if part in CATEGORY_TO_FACT_TYPE:
                    category = part
                    break
            if not category:
                category = "00_公司事实源"

        fact_type = CATEGORY_TO_FACT_TYPE.get(category, "公司基础事实")
        content = _read_file_content(file_path)

        if content.startswith("["):
            return {"facts_saved": 0, "terms_saved": 0, "missing": [], "error": content}

        # 截取前 12000 字符防止超 token（大文件分批）
        content_preview = content[:12000]
        if len(content) > 12000:
            content_preview += f"\n\n[...文件过长，已截取前12000字符，原文共{len(content)}字符]"

        prompt = EXTRACTION_PROMPT.format(
            source_file=file_path,
            category=category,
            fact_type=fact_type,
            content=content_preview,
        )

        logger.info(f"[FactExtractionAgent] extracting from {path.name} (category={category})")

        raw_json = ""
        try:
            resp = self._router.chat(prompt, max_tokens=8000, task_type="fact_extraction")
            if resp.success:
                raw_json = resp.text or ""
            else:
                logger.error(f"[FactExtractionAgent] LLM error: {resp.error}")
                return {"facts_saved": 0, "terms_saved": 0, "missing": [], "error": resp.error}
        except Exception as e:
            logger.error(f"[FactExtractionAgent] API error: {e}")
            return {"facts_saved": 0, "terms_saved": 0, "missing": [], "error": str(e)}

        # 解析 JSON
        try:
            # 去掉可能的 markdown 代码块
            cleaned = raw_json.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"[FactExtractionAgent] JSON parse error: {e}\nraw: {raw_json[:500]}")
            return {"facts_saved": 0, "terms_saved": 0, "missing": [], "error": f"JSON解析失败: {e}"}

        facts = data.get("facts", [])
        terms = data.get("dictionary_terms", [])
        missing = data.get("missing_information", [])

        facts_saved = 0
        for fact in facts:
            if not fact.get("title") or not fact.get("content"):
                continue
            save_company_fact({
                "fact_type":      fact.get("fact_type", fact_type),
                "title":          fact.get("title", ""),
                "content":        fact.get("content", ""),
                "source_file":    str(file_path),
                "source_section": fact.get("source_section", ""),
                "confidence":     fact.get("confidence", "medium"),
                "is_active":      False,
                "review_status":  "pending",
                "extracted_by":   "FactExtractionAgent",
            })
            facts_saved += 1

        terms_saved = 0
        for term in terms:
            if not term.get("standard_term"):
                continue
            save_dictionary_term({
                "term_type":       term.get("term_type", ""),
                "standard_term":   term.get("standard_term", ""),
                "aliases":         term.get("aliases", []),
                "forbidden_terms": term.get("forbidden_terms", []),
                "description":     term.get("description", ""),
                "source_file":     str(file_path),
                "is_active":       True,
            })
            terms_saved += 1

        logger.info(f"[FactExtractionAgent] done: {facts_saved} facts, {terms_saved} terms, {len(missing)} missing")
        return {
            "facts_saved":  facts_saved,
            "terms_saved":  terms_saved,
            "missing":      missing,
            "error":        None,
            "raw_facts":    facts,
            "raw_terms":    terms,
        }

    def extract_directory(self, directory: str, category: str = None) -> dict:
        """批量提取目录下所有支持文件"""
        dir_path = Path(directory)
        if not dir_path.is_dir():
            return {"error": f"目录不存在: {directory}"}

        results = []
        supported = {".txt", ".md", ".html", ".htm", ".docx", ".pdf", ".py"}
        for f in sorted(dir_path.iterdir()):
            if f.suffix.lower() in supported and not f.name.startswith("."):
                result = self.extract(str(f), category=category)
                result["file"] = f.name
                results.append(result)

        total_facts = sum(r.get("facts_saved", 0) for r in results)
        total_terms = sum(r.get("terms_saved", 0) for r in results)
        return {
            "files_processed": len(results),
            "total_facts": total_facts,
            "total_terms": total_terms,
            "results": results,
        }
