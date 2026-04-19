"""Brief validation, scoring, restructuring, and prompt generation endpoints.

Mounted under the /prompts prefix so existing endpoint paths are preserved.
"""

import json
import os
from datetime import datetime

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import AuditLog, User
from app.schemas import (
    BriefScoreRequest,
    BriefScoreResponse,
    GenerateRequest,
    GenerateResponse,
    RestructureBriefRequest,
    RestructureBriefResponse,
    ValidateBriefRequest,
    ValidateBriefResponse,
)
from services.guardrails import resolve_guardrails
from services.variable_resolver import VariableResolver

router = APIRouter(prefix="/prompts", tags=["generation"])


# ── Validate brief description via Claude ────────────────────────────────────

_VALIDATE_BRIEF_PROMPT = """\
You are a strict quality gate reviewing an AI prompt brief for a \
regulated financial services firm. Classify into three tiers.

The user has provided this description:
"{user_input}"

THREE MANDATORY ELEMENTS — all three must be present for Tier 1:

1. SPECIFIC DATA OR CONTENT — not "key data", "information", or \
"documents". Must name what specifically is being extracted, summarised, \
or assessed. Acceptable: "subscription cut-off times", "FINMA obligations", \
"risk ratings", "counterparty names and settlement dates". \
Unacceptable: "key data", "relevant information", "important details".

2. CLEAR OUTPUT — not just "structured assessment" or "useful output". \
Must indicate what the output contains or how it is structured. \
Acceptable: "a table of cut-off times by share class", "a one-page \
summary of obligations with action flags", "a JSON object with named \
fields". Unacceptable: "useful data", "structured output", "summary".

3. CLEAR NEXT STEP — who uses the output and what they do with it. \
Acceptable: "for operations staff to manually key into Simcorp", \
"for the CRO to brief the board", "for the compliance team to assess \
against FINMA requirements". \
Unacceptable: "useful for manual input", "for the team", "for core systems".

ALSO REJECT if the input has broken grammar, is a sentence fragment, \
or appears hasty — ask the user to rephrase clearly.

TIER 1 — All three elements present and specific. \
Return JSON: {{"tier": 1}}

TIER 2 — Two of three elements present. One element is weak but \
inferable. Return JSON: \
{{"tier": 2, "suggestion": "one sentence", \
"suggested_addition": "the specific phrase to add"}}

TIER 2 SUGGESTION RULES — strictly follow these:
- Must reference actual words or phrases from the user's input
- Must suggest a specific addition, not a general improvement
- One sentence maximum
- Must address a gap that would materially improve the generated prompt
- If the user uses informal or vague terms for a system, platform, or \
process (e.g. "cool banking application", "the system", "our tool"), \
suggest naming it specifically with examples from the domain \
(e.g. Simcorp, Temenos, Charles River, Bloomberg AIM)

BAD suggestion: "The output structure is clear but needs to specify \
which staff will use this data"
GOOD suggestion: "The target system is described as a banking \
application — do you know its name? Naming it specifically (e.g. \
Simcorp, Temenos, Charles River) will make the prompt more precise."
GOOD suggestion: "Consider naming the team who loads data into \
[system name from input] — this helps the prompt handle errors \
and edge cases specific to that handoff"

TIER 3 — One or more elements missing or vague. Generic language used. \
Return JSON: \
{{"tier": 3, "question": "one targeted question about the weakest missing element", \
"options": ["option1", "option2", "option3", "option4", "option5", "option6"], \
"free_text_placeholder": "Or describe..."}}

Options must be domain-specific choices relevant to the question.

Example that MUST be Tier 3: "This is a prompt will take key data from \
a funds prospectus document that will be useful for manual input into \
the core systems" — "key data" is not specific, "useful for manual input" \
does not describe the output, "core systems" is not specific.

Example that is Tier 1: "Extract subscription cut-off times and minimum \
investment amounts from fund prospectus documents into a table by share \
class for operations staff to key into Simcorp Dimension before 14:00 CET"

Return ONLY valid JSON. No preamble."""


_DEDUP_PROMPT = """\
You are deciding whether to ask a follow-up question in a brief building session.

Full conversation so far:
{conversation_history}

Proposed follow-up question:
{proposed_question}

Has the conversation already answered this question or made it irrelevant? Reply with YES or NO only.

If YES — do not ask the question.
If NO — ask the question."""


def _is_question_redundant(client, question: str, history: list[str]) -> bool:
    if not history:
        return False
    conversation = "\n".join(history)
    prompt = _DEDUP_PROMPT.replace("{conversation_history}", conversation).replace("{proposed_question}", question)
    try:
        response = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            max_tokens=8,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip().upper().startswith("YES")
    except Exception:
        return False


@router.post("/validate-brief", response_model=ValidateBriefResponse)
def validate_brief(
    body: ValidateBriefRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prompt_text = _VALIDATE_BRIEF_PROMPT.replace("{user_input}", body.description)
    try:
        client = anthropic.Anthropic()
        print(f"[Validation] Input: {body.description[:80]}")
        response = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            max_tokens=512,
            messages=[{"role": "user", "content": prompt_text}],
        )
        raw = response.content[0].text.strip()
        print(f"[Validation] Claude raw: {raw[:200]}")
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1])
        parsed = json.loads(raw)
        tier = parsed.get("tier", 1)
        print(f"[Validation] Tier: {tier}")
        if tier == 1:
            return ValidateBriefResponse(tier=1, accepted=True)
        elif tier == 2:
            return ValidateBriefResponse(
                tier=2, accepted=True,
                suggestion=parsed.get("suggestion"),
                suggested_addition=parsed.get("suggested_addition"),
            )
        else:
            return ValidateBriefResponse(
                tier=3, accepted=False,
                question=parsed.get("question"),
                options=parsed.get("options"),
                free_text_placeholder=parsed.get("free_text_placeholder"),
            )
    except Exception as e:
        print(f"WARNING: Brief validation failed: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Brief validation unavailable: {e}",
        )


# ── Brief question relevance check ───────────────────────────────────────────

_RELEVANCE_PROMPT = """\
You are deciding whether to ask a follow-up question. Given the conversation \
history, has this question already been answered or made irrelevant by a \
previous answer?

If the user said "manually loaded" or "no platform" or similar — platform \
questions are irrelevant. If the user already specified the data type, do \
not ask again. If the user already named the audience, do not ask who \
receives the output.

Reply with exactly: RELEVANT or SKIP"""


@router.post("/briefs/check-relevance")
def check_relevance(
    body: dict,
    current_user: User = Depends(get_current_user),
):
    history = body.get("conversation_history", [])
    question = body.get("proposed_question", "")
    if not history or not question:
        return {"result": "RELEVANT"}
    try:
        client = anthropic.Anthropic()
        conversation = "\n".join(
            f"Q: {e.get('question', '')}\nA: {e.get('answer', 'skipped')}" if isinstance(e, dict) else str(e)
            for e in history
        )
        response = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            max_tokens=8,
            system=_RELEVANCE_PROMPT,
            messages=[{"role": "user", "content": f"Conversation:\n{conversation}\n\nProposed question:\n{question}"}],
        )
        result = response.content[0].text.strip().upper()
        return {"result": "SKIP" if "SKIP" in result else "RELEVANT"}
    except Exception:
        return {"result": "RELEVANT"}


# ── Brief quality score ──────────────────────────────────────────────────────

@router.post("/briefs/score", response_model=BriefScoreResponse)
def score_brief(
    body: BriefScoreRequest,
    current_user: User = Depends(get_current_user),
):
    specificity = 0
    if body.purpose and len(body.purpose) >= 20:
        specificity += 8
    if body.input_type:
        specificity += 9
    if body.output_type:
        specificity += 8

    context = 0
    if body.audience:
        context += 13
    if body.deployment_target:
        context += 12

    constraints_score = 0
    if body.constraints:
        constraints_score = min(25, len(body.constraints) * 5)

    completeness = 0
    filled = sum(1 for v in [body.purpose, body.input_type, body.output_type, body.audience] if v)
    completeness = min(25, filled * 6)
    if body.purpose and len(body.purpose) >= 50:
        completeness = min(25, completeness + 3)

    # Skip penalties
    skip_penalties = {2: 8, 3: 8, 4: 10, 5: 4}
    skip_deduction = sum(skip_penalties.get(s, 0) for s in body.skipped_steps)

    total = max(0, min(100, specificity + context + constraints_score + completeness - skip_deduction))

    if total >= 80:
        label = "Gold standard brief"
    elif total >= 60:
        label = "Strong"
    elif total >= 40:
        label = "Reasonable"
    else:
        label = "Weak"

    dims = {"Specificity": specificity, "Context": context, "Constraints": constraints_score, "Completeness": completeness}
    weakest = min(dims, key=dims.get)

    tips = {
        "Specificity": "Name the specific document type or data source the AI will process",
        "Context": "Specify who will use the output and where it will be deployed",
        "Constraints": "Select constraints that apply to this use case",
        "Completeness": "Complete the remaining steps for a stronger brief",
    }

    return BriefScoreResponse(
        score=total,
        label=label,
        weakest_dimension=weakest,
        improvement_tip=tips[weakest],
        dimensions=dims,
    )


# ── Brief restructuring ─────────────────────────────────────────────────────

_RESTRUCTURE_PROMPT = """\
You are a senior AI consultant. Rewrite the following brief answers as a \
single coherent paragraph that a prompt generator can use directly. \
Write in third person describing what the AI system should do. Be specific \
and include all constraints and guardrails mentioned. Maximum 100 words. \
Do not add information not in the brief."""


@router.post("/briefs/restructure", response_model=RestructureBriefResponse)
def restructure_brief(
    body: RestructureBriefRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            max_tokens=256,
            system=_RESTRUCTURE_PROMPT,
            messages=[{"role": "user", "content": f"Brief answers:\n{body.brief_text}"}],
        )
        return RestructureBriefResponse(restructured=response.content[0].text.strip())
    except Exception as e:
        return RestructureBriefResponse(restructured=body.brief_text)


# ── Generate prompt text via Claude ──────────────────────────────────────────

_GENERATE_SYSTEM_PROMPT_TEMPLATE = """\
You are an expert prompt engineer for regulated financial services. \
Generate a production-ready system prompt based on the brief below. \
The prompt must include guardrail instructions for EACH of the \
following dimensions — and ONLY these dimensions. Do not add \
guardrails for dimensions not listed.

REQUIRED GUARDRAIL DIMENSIONS:
{guardrail_block}

Write the prompt in second person addressing the AI model. \
End with a section titled TONE AND BEHAVIOUR RULES containing all guardrails.
Return only the prompt text — no explanation, no preamble."""


@router.post("/generate", response_model=GenerateResponse)
def generate_prompt_text(
    body: GenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from services.injection_scanner import scan as injection_scan

    if body.brief_text:
        scan_result = injection_scan("brief_text", body.brief_text, db)
        if scan_result["result"] == "critical":
            db.add(AuditLog(
                user_id=current_user.user_id,
                action="InjectionDetected",
                entity_type="Prompt",
                entity_id="generate",
                detail=json.dumps({"scan_result": scan_result}),
            ))
            db.commit()
            raise HTTPException(
                status_code=400,
                detail=f"Injection detected in brief text: {scan_result['message']}",
            )

    from services.prompt_components import assemble_template, get_input_handler_text, get_output_handler_text, get_regulatory_text, get_behaviour_text

    selected_dims = resolve_guardrails(body, db)
    guardrail_block = "\n".join(
        f"- {d.code} ({d.name}): {d.description}" for d in selected_dims
    )
    system_prompt = _GENERATE_SYSTEM_PROMPT_TEMPLATE.replace("{guardrail_block}", guardrail_block)

    # Assemble components from template if available, otherwise from selections
    assembled = assemble_template(body.prompt_type, body.constraints)

    brief_parts = [f"Title: {body.title}", f"Prompt type: {body.prompt_type}"]
    if body.deployment_target:
        brief_parts.append(f"Deployment target: {body.deployment_target}")
    if body.input_type:
        brief_parts.append(f"Input type: {body.input_type}")
    if body.output_type:
        brief_parts.append(f"Output type: {body.output_type}")
    if body.brief_text:
        brief_parts.append(f"Additional brief:\n{body.brief_text}")

    brief_parts.append(f"\nINPUT HANDLER COMPONENT TO INCLUDE VERBATIM:\n{assembled['input']}")
    brief_parts.append(f"\nOUTPUT HANDLER COMPONENT TO INCLUDE VERBATIM:\n{assembled['output']}")
    if assembled["regulatory"]:
        brief_parts.append(f"\nREGULATORY GUARDRAIL COMPONENTS TO INCLUDE VERBATIM:\n{assembled['regulatory']}")
    if assembled["behaviour"]:
        brief_parts.append(f"\nBEHAVIOUR GUARDRAIL COMPONENTS TO INCLUDE VERBATIM:\n{assembled['behaviour']}")
    if assembled.get("example"):
        brief_parts.append(f"\n{assembled['example']}")

    user_message = "BRIEF:\n" + "\n".join(brief_parts) + "\n\nGenerate the prompt now. Include all component blocks verbatim. If an output example is provided, follow its exact structure."

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        generated = response.content[0].text.strip()
        if generated.startswith("```"):
            lines = generated.split("\n")
            generated = "\n".join(lines[1:-1])

        generated = VariableResolver().resolve(
            generated,
            generation_date=datetime.utcnow().strftime("%Y-%m-%d"),
            author=current_user.name or current_user.email,
        )

        db.add(AuditLog(
            user_id=current_user.user_id,
            action="PromptGenerated",
            entity_type="Prompt",
            entity_id="generate",
            detail=json.dumps({
                "title": body.title,
                "prompt_type": body.prompt_type,
                "selected_guardrails": [d.code for d in selected_dims],
                "generated_length": len(generated),
            }),
        ))
        db.commit()

        return GenerateResponse(prompt_text=generated)
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=502, detail="Anthropic API key is invalid or missing")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Claude API error: {str(e)}")
