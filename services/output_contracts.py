"""Formal output contracts for conclusions and promotion recommendations."""
from __future__ import annotations

from typing import Any, Iterable

from services.guardrails import NO_DATA_MESSAGE, no_data_payload, normalize_role, validate_ai_output, validate_product


FORMAL_CONFIDENCE = {"high", "medium", "low"}


def has_real_data(*collections: Iterable[Any] | None) -> bool:
    return any(bool(items) for items in collections)


def no_data_result(reason: str = "") -> dict[str, Any]:
    return no_data_payload(reason or NO_DATA_MESSAGE)


def evidence_from_records(table: str, rows: list[dict] | None, *, id_key: str = "id", limit: int = 8) -> list[str]:
    evidence: list[str] = []
    for row in (rows or [])[:limit]:
        rid = row.get(id_key)
        if rid is not None:
            evidence.append(f"{table}.{id_key}={rid}")
    return evidence


def normalize_evidence(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if isinstance(value, tuple):
        return [str(v) for v in value if str(v).strip()]
    text = str(value).strip()
    return [text] if text else []


def validate_formal_output(
    payload: dict[str, Any] | None,
    *,
    require_product: bool = False,
    require_recommendation: bool = True,
) -> dict[str, Any]:
    payload = payload or {}
    normalized = {
        **payload,
        "evidence": normalize_evidence(
            payload.get("evidence")
            or payload.get("data_evidence")
            or payload.get("data_sources")
            or payload.get("data_basis")
        ),
        "confidence": payload.get("confidence") or payload.get("confidence_label") or payload.get("confidence_score"),
        "responsible_role": normalize_role(
            payload.get("responsible_role") or payload.get("department") or payload.get("role") or ""
        ),
    }
    guard = validate_ai_output(normalized, require_product=require_product)
    errors = list(guard.get("errors") or [])
    if require_recommendation and not (
        payload.get("recommendation")
        or payload.get("content")
        or payload.get("action")
        or payload.get("hook")
        or payload.get("hook_idea")
    ):
        errors.append("missing_recommendation")
    if guard.get("confidence") not in FORMAL_CONFIDENCE:
        errors.append("invalid_confidence")

    status = "valid" if not errors else ("no_data" if payload.get("no_data") else "invalid")
    return {
        **guard,
        "validation_status": status,
        "errors": sorted(set(errors)),
        "evidence": normalized["evidence"],
        "confidence": guard.get("confidence"),
        "responsible_role": normalized["responsible_role"],
    }


def validate_content_strategy_record(record: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    product_raw = record.get("product_id") or record.get("target_product") or record.get("product_name")
    product_check = validate_product(product_raw)
    evidence = normalize_evidence(record.get("data_evidence") or record.get("evidence"))
    product_id = product_check.get("canonical_product_id") or ""
    product_name = product_check.get("product_name") or ""
    safe = {
        **record,
        "product_id": product_id,
        "product_name": product_name,
        "school_name": record.get("school_name") or record.get("target_school") or "",
        "hook": record.get("hook") or record.get("hook_idea") or "",
        "data_evidence": "；".join(evidence),
        "confidence": record.get("confidence") or "low",
        "responsible_role": "推广/市场",
    }
    guard = validate_formal_output(
        {
            **safe,
            "product": product_id,
            "evidence": evidence,
            "recommendation": safe.get("hook") or safe.get("hook_idea") or safe.get("body_idea"),
        },
        require_product=True,
    )
    safe["status"] = safe.get("status") or "pending"
    if guard["validation_status"] != "valid":
        safe["status"] = "skipped"
        safe["missing_data"] = sorted(set((safe.get("missing_data") or []) + guard["errors"]))
    return safe, guard
