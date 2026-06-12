"""业务术语检查脚本

扫描指定文本/文件/目录，检查是否出现 business_dictionary 中的禁用词
和 business_constants 中的全局禁止承诺用语。

用法：
    python scripts/check_business_terms.py "要检查的一段文本"
    python scripts/check_business_terms.py outputs/某文件.md
    python scripts/check_business_terms.py outputs/          # 扫描整个目录

退出码：0 = 通过，1 = 发现禁用词（可用于 CI / cron 检查）。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import get_forbidden_terms  # noqa: E402
from services.business_constants import GLOBAL_FORBIDDEN_PHRASES, DEPARTMENT_ALIASES  # noqa: E402

TEXT_SUFFIXES = {".md", ".txt", ".html", ".csv", ".json"}


def collect_forbidden() -> dict[str, str]:
    """返回 {禁用词: 提示信息}"""
    forbidden: dict[str, str] = {}
    for phrase in GLOBAL_FORBIDDEN_PHRASES:
        forbidden[phrase] = "全局禁止承诺用语"
    for alias, standard in DEPARTMENT_ALIASES.items():
        forbidden[alias] = f"部门叫法错误，应为「{standard}」"
    try:
        for term in get_forbidden_terms():
            forbidden.setdefault(term, "业务词典禁用词")
    except Exception as e:
        print(f"⚠️  无法读取业务词典（{e}），仅使用内置规则检查")
    return forbidden


def check_text(text: str, forbidden: dict[str, str], source: str = "<输入文本>") -> list[str]:
    hits = []
    for line_no, line in enumerate(text.splitlines(), 1):
        for term, note in forbidden.items():
            if term in line:
                hits.append(f"  ❌ {source}:{line_no}  「{term}」 — {note}")
    return hits


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    target = sys.argv[1]
    forbidden = collect_forbidden()
    path = Path(target)
    all_hits: list[str] = []

    if path.is_dir():
        for f in sorted(path.rglob("*")):
            if f.suffix in TEXT_SUFFIXES and f.is_file():
                all_hits += check_text(f.read_text(errors="ignore"), forbidden, str(f))
    elif path.is_file():
        all_hits += check_text(path.read_text(errors="ignore"), forbidden, str(path))
    else:
        all_hits += check_text(target, forbidden)

    if all_hits:
        print(f"发现 {len(all_hits)} 处禁用表达：")
        print("\n".join(all_hits))
        sys.exit(1)
    print("✅ 未发现禁用表达")


if __name__ == "__main__":
    main()
