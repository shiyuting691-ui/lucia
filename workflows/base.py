"""
BaseWorkflow — 所有工作流的基类
提供统一的运行日志、错误处理、步骤追踪框架
"""
import logging
from datetime import datetime
from database import start_workflow_run, finish_workflow_run

logger = logging.getLogger(__name__)


class BaseWorkflow:
    name: str = "base_workflow"

    def __init__(self, config: dict):
        self.config = config
        self._steps: list = []
        self._records_created: int = 0

    def _add_step(self, step_name: str, status: str, records: int = 0, note: str = ""):
        self._steps.append({
            "step": step_name,
            "status": status,
            "records": records,
            "note": note,
            "ts": datetime.utcnow().isoformat(),
        })
        self._records_created += records
        logger.info(f"[{self.name}] step={step_name} status={status} records={records}")

    def _run_steps(self) -> dict:
        """子类实现：执行具体步骤，返回 summary dict"""
        raise NotImplementedError

    def run(self, trigger: str = "manual") -> dict:
        run_id = start_workflow_run(self.name, trigger=trigger)
        logger.info(f"[{self.name}] started run_id={run_id} trigger={trigger}")

        try:
            result = self._run_steps()
            overall = "success"
            # 如果有任何步骤失败但没有全局异常，标记为 partial_success
            if any(s["status"] == "error" for s in self._steps):
                overall = "partial_success"

            summary = result.get("summary", f"{self.name} 完成，共生成 {self._records_created} 条记录")
            finish_workflow_run(
                run_id=run_id,
                status=overall,
                steps=self._steps,
                records_count=self._records_created,
                summary=summary,
            )
            logger.info(f"[{self.name}] finished run_id={run_id} status={overall}")
            return {"run_id": run_id, "status": overall, "summary": summary, **result}

        except Exception as e:
            logger.error(f"[{self.name}] fatal error: {e}")
            finish_workflow_run(
                run_id=run_id,
                status="failed",
                steps=self._steps,
                records_count=self._records_created,
                error_message=str(e),
                summary=f"{self.name} 运行失败：{str(e)[:100]}",
            )
            return {"run_id": run_id, "status": "failed", "error": str(e)}
