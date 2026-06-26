"""Stopgap guardrails for formal pages and AI-generated outputs."""
from __future__ import annotations

from typing import Any

from services.business_constants import normalize_department
from services.product_catalog_service import ProductCatalogService

NO_DATA_MESSAGE = "暂无真实数据，无法判断。"
FORMAL_ROLES = ("管理层", "推广/市场", "销售/顾问/学管", "产品/后台", "交付/老师")
ROLE_ALIASES = {
    "销售": "销售/顾问/学管",
    "销售部": "销售/顾问/学管",
    "销售/顾问": "销售/顾问/学管",
    "销售顾问": "销售/顾问/学管",
    "顾问": "销售/顾问/学管",
    "学管": "销售/顾问/学管",
    "学管部": "销售/顾问/学管",
    "市场部": "推广/市场",
    "推广部": "推广/市场",
    "市场/推广": "推广/市场",
    "后台/产品": "产品/后台",
    "产品部": "产品/后台",
    "后台": "产品/后台",
    "老师": "交付/老师",
    "教研": "交付/老师",
    "交付部": "交付/老师",
}

CONFIDENCE_VALUES = ("high", "medium", "low", "no_data")


def normalize_role(role: str | None) -> str:
    value = (role or "").strip()
    value = ROLE_ALIASES.get(value, value)
    value = normalize_department(value)
    return value


def is_valid_role(role: str | None) -> bool:
    return normalize_role(role) in FORMAL_ROLES


def validate_product(raw_product: str | None) -> dict[str, Any]:
    mapped = ProductCatalogService.map_raw_product(raw_product or "")
    return {
        **mapped,
        "valid": bool(mapped.get("canonical_product_id")),
    }


def catalog_product_options() -> list[dict[str, str]]:
    return [
        {
            "id": p["canonical_product_id"],
            "name": p["product_name"],
            "short": p.get("product_short") or p["product_name"],
            "price_range": p.get("price_range") or "",
            "desc": p.get("desc") or "",
        }
        for p in ProductCatalogService.load_active_products()
    ]


def no_data_payload(reason: str, evidence: list[str] | None = None) -> dict[str, Any]:
    return {
        "no_data": True,
        "validation_status": "no_data",
        "reason": reason or NO_DATA_MESSAGE,
        "evidence": evidence or [],
        "confidence": "no_data",
        "message": NO_DATA_MESSAGE,
    }


def validate_ai_output(payload: dict[str, Any] | None, *, require_product: bool = False) -> dict[str, Any]:
    payload = payload or {}
    evidence = payload.get("evidence") or payload.get("data_evidence") or payload.get("data_basis")
    confidence = payload.get("confidence") or payload.get("confidence_label") or payload.get("confidence_score")
    role = payload.get("responsible_role") or payload.get("department") or payload.get("role")
    product = payload.get("product") or payload.get("product_id") or payload.get("related_product")

    errors: list[str] = []
    if not evidence:
        errors.append("missing_evidence")
    if confidence is None:
        errors.append("missing_confidence")
    if role and not is_valid_role(str(role)):
        errors.append("invalid_role")
    if not role:
        errors.append("missing_responsible_role")
    if require_product:
        product_check = validate_product(str(product or ""))
        if not product_check["valid"]:
            errors.append("invalid_product")

    if payload.get("no_data") is True:
        errors.append("no_data")

    status = "valid" if not errors else ("no_data" if "no_data" in errors else "invalid")
    return {
        "validation_status": status,
        "errors": errors,
        "evidence": evidence or [],
        "confidence": _normalize_confidence(confidence),
        "responsible_role": normalize_role(str(role or "")) if role else "",
    }


def _normalize_confidence(value: Any) -> str:
    if isinstance(value, (int, float)):
        if value >= 0.7:
            return "high"
        if value >= 0.4:
            return "medium"
        return "low"
    value = str(value or "").lower()
    if value in CONFIDENCE_VALUES:
        return value
    zh_map = {"高": "high", "中": "medium", "低": "low"}
    return zh_map.get(value, "low")
