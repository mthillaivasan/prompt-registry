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
    ValidateTopicRequest,
    ValidateTopicResponse,
)
from services.guardrails import resolve_guardrails
from services.pricing import DEFAULT_OUTPUT_TOKENS_ESTIMATE, count_tokens, estimate_cost_usd
from services.topic_rubrics import (
    UnknownTopicError,
    build_validate_topic_system_prompt,
    get_rubric,
    has_rubric_set,
)
from services.variable_resolver import VariableResolver

router = APIRouter(prefix="/prompts", tags=["generation"])


# ── Validate brief description via Claude ────────────────────────────────────

_VALIDATE_BRIEF_SYSTEM = """\
You are a strict quality gate reviewing an AI prompt brief for a regulated financial services firm. Classify the brief into three tiers based on whether a prompt engineer could build a correct, unambiguous prompt from it.

THREE MANDATORY ELEMENTS — all three must be present for Tier 1:

1. SPECIFIC DATA OR CONTENT — not "key data", "information", or "documents". Must name what specifically is being extracted, summarised, or assessed. Acceptable: "subscription cut-off times", "FINMA obligations", "risk ratings", "counterparty names and settlement dates". Unacceptable: "key data", "relevant information", "important details".

2. CLEAR OUTPUT — not just "structured assessment" or "useful output". Must indicate what the output contains or how it is structured. Acceptable: "a table of cut-off times by share class", "a one-page summary of obligations with action flags", "a JSON object with named fields". Unacceptable: "useful data", "structured output", "summary".

3. CLEAR NEXT STEP — who uses the output and what they do with it. Acceptable: "for operations staff to manually key into Simcorp", "for the CRO to brief the board", "for the compliance team to assess against FINMA requirements". Unacceptable: "useful for manual input", "for the team", "for core systems".

If the brief has broken grammar, is a sentence fragment, or appears hasty, return Tier 3 and ask the user to rephrase clearly.

=== TIER 1 ===
All three elements present and specific.
Return: {"tier": 1}

=== TIER 2 ===
Two of three elements present. One element is weak but inferable.
Return: {"tier": 2, "suggestion": "...", "suggested_addition": "..."}

TIER 2 RULES:
- The suggestion must reference actual words or phrases from the brief
- The suggestion must propose a specific addition, not a general improvement
- One sentence maximum
- Must address a gap that would materially improve the generated prompt
- If the brief uses a vague term for a system, platform, or process, propose naming it specifically
- Do not offer generic prompt-engineering advice

=== TIER 3 ===
One or more elements missing, or vague. Generic language used.
Return: {"tier": 3, "question": "...", "options": [6 items], "free_text_placeholder": "Or describe..."}

TIER 3 QUESTION RULES — read carefully:

The question must target a DOMAIN DETAIL that would materially change the STRUCTURE or LOGIC of the generated prompt. It must not ask for operational context that the prompt would simply pass through.

The test: if you knew the answer, would a prompt engineer structure the prompt differently, add branching logic, add normalisation, add a new section, or alter what the model is asked to do? If yes, ask. If the answer just fills a blank (a date, a threshold, a name, a time), do NOT ask.

The question must be grounded in the specific workflow described in the brief — not drawn from a generic prompt-engineering checklist.

OPTIONS RULES:
- Exactly 6 options
- Orthogonal — no option may be a subset, rewording, or special case of another
- Each option is a complete phrase the user could pick as their answer, not a category label
- Multi-select is supported: generate options that plausibly co-occur in real workflows so users can pick combinations where appropriate
- Each option must be grounded in the specific brief — do not paraphrase generic prompt-engineering concerns

DO NOT re-ask anything covered in the PRIOR COACHING block of the user message.

If PRIOR COACHING has resolved all gaps that would materially change the structure or logic of the generated prompt, return Tier 1 even if the three MANDATORY ELEMENTS are not all strictly satisfied. Coaching completeness overrides the rubric once structure-changing gaps are closed.

CLASSIFICATION REFERENCE:
Example that MUST be Tier 3: "This is a prompt will take key data from a funds prospectus document that will be useful for manual input into the core systems" — "key data" is not specific, "useful for manual input" does not describe the output, "core systems" is not specific.

Example that is Tier 1: "Extract subscription cut-off times and minimum investment amounts from fund prospectus documents into a table by share class for operations staff to key into Simcorp Dimension before 14:00 CET"

Return ONLY valid JSON. No preamble, no markdown fences."""


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
    # Keep only real Tier-3 Q&A pairs. Frontend also pushes markers for
    # accept/skip/abandon events ({"question": "validation"|"track", ...});
    # those are workflow telemetry, not coaching content.
    relevant = [
        e for e in body.conversation_history
        if not e.skipped and e.question and e.question not in ("validation", "track")
    ]
    if relevant:
        history_block = "\n\n".join(f"Q: {e.question}\nA: {e.answer}" for e in relevant)
    else:
        history_block = "None."
    user_message = (
        f"BRIEF DRAFT:\n{body.description}\n\n"
        f"PRIOR COACHING IN THIS SESSION:\n{history_block}"
    )

    try:
        client = anthropic.Anthropic()
        print(f"[Validation] Input: {body.description[:80]}; prior_Qs: {len(relevant)}")
        response = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            max_tokens=512,
            system=_VALIDATE_BRIEF_SYSTEM,
            messages=[{"role": "user", "content": user_message}],
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
Do not add information not in the brief.

Additionally, produce a short title (5-8 words) that summarises what this \
prompt does. The title should be specific enough to tell a reader what the \
prompt is for.

Return your response as JSON only — no preamble, no markdown fences:
{"restructured": "<the restructured brief text>", "title": "<the short title>"}"""


@router.post("/briefs/restructure", response_model=RestructureBriefResponse)
def restructure_brief(
    body: RestructureBriefRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            max_tokens=384,
            system=_RESTRUCTURE_PROMPT,
            messages=[{"role": "user", "content": f"Brief answers:\n{body.brief_text}"}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1])
    except Exception as e:
        print(f"WARNING: Brief restructuring failed: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Brief restructuring unavailable: {e}",
        )

    try:
        parsed = json.loads(raw)
        restructured = parsed["restructured"].strip()
        title = parsed.get("title")
        if title is not None:
            title = title.strip() or None
    except (json.JSONDecodeError, KeyError, AttributeError, TypeError) as e:
        print(f"WARNING: Brief restructuring JSON parse failed: {e}; falling back to raw text, no title")
        restructured = raw
        title = None

    return RestructureBriefResponse(restructured=restructured, title=title)


# ── Per-topic validation for the Step 1 topic checklist ──────────────────────

# Model choice: Haiku. Pre-build test showed 92% state-agreement with Sonnet
# and zero red↔green disagreements on 12 paired calls. Sonnet stays for the
# whole-brief restructure call above (quality matters more there, runs once).
# See docs/HAIKU_VS_SONNET_RESULTS.md.
_VALIDATE_TOPIC_MODEL = "claude-haiku-4-5-20251001"


@router.post("/briefs/validate-topic", response_model=ValidateTopicResponse)
def validate_topic(
    body: ValidateTopicRequest,
    current_user: User = Depends(get_current_user),
):
    if not has_rubric_set(body.prompt_type):
        raise HTTPException(
            status_code=501,
            detail=f"Topic list not yet available for prompt_type {body.prompt_type!r}",
        )
    try:
        get_rubric(body.prompt_type, body.topic_id)
    except UnknownTopicError:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown topic_id {body.topic_id!r} for prompt_type {body.prompt_type!r}",
        )

    # Filter conversation_history to the focal topic only. Excludes skipped
    # entries, empty questions, and the validation/track workflow markers.
    relevant = [
        e for e in body.conversation_history
        if e.topic_id == body.topic_id
        and not e.skipped
        and e.question
        and e.question not in ("validation", "track")
    ]
    answer_block = body.topic_answer or "(no answer yet)"
    if body.sibling_answers:
        sibling_block = "\n".join(f"- {k}: {v}" for k, v in body.sibling_answers.items())
    else:
        sibling_block = "None."
    if relevant:
        history_block = "\n\n".join(f"Q: {e.question}\nA: {e.answer}" for e in relevant)
    else:
        history_block = "None."
    user_message = (
        f"FOCAL TOPIC ANSWER:\n{answer_block}\n\n"
        f"SIBLING ANSWERS FOR CONTEXT ONLY:\n{sibling_block}\n\n"
        f"PRIOR COACHING ON THIS TOPIC:\n{history_block}"
    )
    system_prompt = build_validate_topic_system_prompt(
        body.prompt_type, body.topic_id, reference_examples=body.reference_examples,
    )

    try:
        client = anthropic.Anthropic()
        print(f"[ValidateTopic] topic={body.topic_id} prior_Qs={len(relevant)} answer_len={len(body.topic_answer)}")
        response = client.messages.create(
            model=_VALIDATE_TOPIC_MODEL,
            max_tokens=384,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1])
    except Exception as e:
        print(f"WARNING: Topic validation failed: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Topic validation unavailable: {e}",
        )

    try:
        parsed = json.loads(raw)
        state = parsed.get("state")
        if state not in ("red", "amber", "green"):
            raise ValueError(f"invalid state in response: {state!r}")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"WARNING: Topic validation response malformed: {e}; raw={raw[:200]}")
        raise HTTPException(
            status_code=502,
            detail=f"Topic validation unavailable: response parse error",
        )

    return ValidateTopicResponse(
        state=state,
        suggestion=parsed.get("suggestion"),
        suggested_addition=parsed.get("suggested_addition"),
        question=parsed.get("question"),
        options=parsed.get("options"),
        free_text_placeholder=parsed.get("free_text_placeholder"),
    )


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
    # Three-category filter: only prompt_content dims render into the generated
    # prompt. wrapper_metadata and registry_policy are captured in the DB but
    # excluded from the prompt body. NULL content_type treated as prompt_content
    # for backward compat during the migration window.
    prompt_content_dims = [
        d for d in selected_dims
        if not d.content_type or d.content_type == "prompt_content"
    ]
    guardrail_block = "\n".join(
        d.instructional_text if d.instructional_text
        else f"- {d.code} ({d.name}): {d.description}"
        for d in prompt_content_dims
    )
    system_prompt = _GENERATE_SYSTEM_PROMPT_TEMPLATE.replace("{guardrail_block}", guardrail_block)

    # Assemble components from template if available, otherwise from selections.
    # Passing db enables path #2 content_type filtering on REGULATORY_COMPONENTS.
    assembled = assemble_template(body.prompt_type, body.constraints, db=db)

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


# ── Token count + cost estimate — Drop 1 ─────────────────────────────────────
# Lightweight endpoint for the generator screen to surface tokens and cost
# after a Generate click and on subsequent textarea edits (debounced).
# See services/pricing.py for the counter + rate constants.

from pydantic import BaseModel as _BaseModel


class _CountTokensRequest(_BaseModel):
    text: str = ""


class _CountTokensResponse(_BaseModel):
    token_count: int
    estimated_cost_usd: float
    output_tokens_estimate: int


@router.post("/count-tokens", response_model=_CountTokensResponse)
def count_tokens_endpoint(
    body: _CountTokensRequest,
    current_user: User = Depends(get_current_user),
):
    tokens = count_tokens(body.text)
    return _CountTokensResponse(
        token_count=tokens,
        estimated_cost_usd=estimate_cost_usd(tokens),
        output_tokens_estimate=DEFAULT_OUTPUT_TOKENS_ESTIMATE,
    )
