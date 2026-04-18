"""Guardrail resolution — tier-2 trigger evaluation and guardrail selection.

Shared by compliance and generation routers.
"""

from sqlalchemy.orm import Session

from app.models import ScoringDimension


def check_tier2_trigger(
    dim,
    deployment_target: str,
    input_type: str,
    risk_tier: str,
    prompt_text: str,
) -> str | None:
    """Evaluate whether a tier-2 dimension's condition is met. Returns reason or None."""
    code = dim.code
    dt = (deployment_target or "").lower()
    it = (input_type or "").lower()
    rt = (risk_tier or "").lower()
    pt = (prompt_text or "").lower()

    if code == "REG_D2":
        if "agent" in dt or "external" in dt or "copilot" in dt:
            return "Deployment target involves agents or external visibility"
        return None
    if code == "REG_D3":
        if "personal" in it or "personal" in pt or "client data" in pt:
            return "Personal or client data referenced"
        return None
    if code == "REG_D5":
        if rt == "high" or "critical" in pt:
            return "High risk tier or critical process mentioned"
        return None
    if code == "REG_D6":
        if dt and "internal" not in dt and "claude" not in dt:
            return "Deployment target is not Internal or Claude"
        return None
    if code == "OWASP_LLM01":
        if "free text" in it or "form" in it or "user" in it:
            return "Input includes user-supplied or free-text content"
        return None
    if code == "OWASP_LLM06":
        if "agent" in dt or "automation" in dt:
            return "Deployment target involves agents or automation"
        return None
    return None


def resolve_guardrails(body, db: Session) -> list:
    """Determine which dimensions to include in the generated prompt."""
    dims = (
        db.query(ScoringDimension)
        .filter(ScoringDimension.is_active == True)  # noqa: E712
        .order_by(ScoringDimension.sort_order)
        .all()
    )

    if body.selected_guardrails:
        codes = set(body.selected_guardrails)
        return [d for d in dims if d.code in codes]

    # Auto-detect: tier1 always + triggered tier2 + all tier3
    selected = []
    for d in dims:
        if d.tier == 1:
            selected.append(d)
        elif d.tier == 2:
            reason = check_tier2_trigger(d, body.deployment_target, body.input_type, "", body.brief_text)
            if reason:
                selected.append(d)
        else:
            selected.append(d)
    return selected
