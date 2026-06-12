"""
AgentRunner — Agent 调用统一封装（V8）

职责：registry 检查 → enabled/status 检查 → GBA 强制前置 →
执行 → 捕获错误 → 记录 tokens/cost/duration → 写入 agent_runs

统一返回：
{
  "agent_name": "", "status": "success/failed/skipped/blocked",
  "output": {}, "error_message": "", "run_id": "", "duration_seconds": 0
}
错误不静默吞掉：写入 error_message 并 logger.error。
"""
import logging
import time
import uuid
from datetime import datetime

from agents.agent_registry import load_registry, GROUNDING_REQUIRED, is_callable
from database import save_agent_run

logger = logging.getLogger(__name__)

# claude-sonnet-4-6 定价（USD / 1M tokens）
_PRICE_IN, _PRICE_OUT = 3.0, 15.0


class AgentRunner:

    def __init__(self, workflow_name: str = "", run_id: str = None):
        self.workflow_name = workflow_name
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.registry = load_registry()

    def run(self, agent_name: str, fn, input_summary: str = "", gba_context: dict = None):
        """
        fn: 无参可调用（lambda 包住实际 agent 调用），返回 agent 原始输出
        gba_context: 若该 agent 需要 grounding，传入已获取的 GBA context；
                     不传则由 runner 自动获取。can_generate=False → blocked。
        """
        info = self.registry.get(agent_name, {})
        layer = info.get("layer", "")
        started = datetime.utcnow()
        t0 = time.time()

        def _record(status, output_summary="", error=None, tokens=0):
            save_agent_run({
                "workflow_name": self.workflow_name, "agent_name": agent_name,
                "agent_layer": layer, "run_id": self.run_id, "status": status,
                "input_summary": input_summary, "output_summary": output_summary,
                "error_message": error, "tokens_used": tokens,
                "cost_estimate": round(tokens / 1e6 * (_PRICE_IN + _PRICE_OUT) / 2, 4),
                "duration_seconds": round(time.time() - t0, 2),
                "started_at": started, "finished_at": datetime.utcnow(),
            })

        def _result(status, output=None, error=""):
            return {"agent_name": agent_name, "status": status,
                    "output": output if output is not None else {},
                    "error_message": error or "", "run_id": self.run_id,
                    "duration_seconds": round(time.time() - t0, 2)}

        # 1. registry / enabled / deprecated 检查
        ok, reason = is_callable(agent_name)
        if not ok:
            logger.info(f"[AgentRunner] skip {agent_name}: {reason}")
            _record("skipped", error=reason)
            return _result("skipped", error=reason)

        # 2. GBA 强制前置
        if agent_name in GROUNDING_REQUIRED:
            try:
                if gba_context is None:
                    from agents.grounded_business_agent import GroundedBusinessAgent
                    gba_context = GroundedBusinessAgent().get_context("monthly_strategy")
                if not gba_context.get("can_generate"):
                    missing = "; ".join(str(m) for m in gba_context.get("missing_information", []))[:300]
                    msg = f"GroundedBusinessAgent 阻止生成：公司事实不足。{missing}"
                    logger.warning(f"[AgentRunner] blocked {agent_name}: {msg}")
                    _record("blocked", error=msg)
                    return _result("blocked", error=msg)
            except Exception as e:
                logger.error(f"[AgentRunner] GBA 检查失败 {agent_name}: {e}")
                _record("failed", error=f"GBA检查异常: {e}")
                return _result("failed", error=str(e))

        # 3. 执行
        try:
            output = fn()
            tokens = 0
            if isinstance(output, dict):
                tokens = output.get("tokens_used", 0) or 0
            summary = str(output)[:500] if output is not None else ""
            _record("success", output_summary=summary, tokens=tokens)
            return _result("success", output=output)
        except Exception as e:
            logger.error(f"[AgentRunner] {agent_name} 运行失败: {e}", exc_info=True)
            _record("failed", error=str(e)[:1000])
            return _result("failed", error=str(e))
