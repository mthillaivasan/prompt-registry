from sqlalchemy.orm import Session

from app.models import ScoringDimension

SEED_DIMENSIONS = [
    # --- REGULATORY (mandatory, blocking_threshold=2, scoring_type=Blocking) ---
    {
        "framework": "REG",
        "code": "REG_D1",
        "name": "Human Oversight",
        "description": "EU AI Act Art 14 / FINMA",
        "scoring_type": "Blocking",
        "is_mandatory": True,
        "blocking_threshold": 2,
        "score_5_criteria": (
            "Explicitly requires human review, names oversight mechanism, "
            "defines what reviewer assesses, states override path."
        ),
        "weight": 1.0,
    },
    {
        "framework": "REG",
        "code": "REG_D2",
        "name": "Transparency",
        "description": "EU AI Act Art 13 / FCA Consumer Duty",
        "scoring_type": "Blocking",
        "is_mandatory": True,
        "blocking_threshold": 2,
        "score_5_criteria": (
            "Output declared AI-generated, advisory not authoritative, "
            "limitations stated, AI identity not suppressed."
        ),
        "weight": 1.0,
    },
    {
        "framework": "REG",
        "code": "REG_D3",
        "name": "Data Minimisation",
        "description": "nDSG Art 6 / GDPR Art 5",
        "scoring_type": "Blocking",
        "is_mandatory": True,
        "blocking_threshold": 2,
        "score_5_criteria": (
            "Purpose declared, only necessary data used, retention "
            "prohibition stated, legal basis declared if personal data."
        ),
        "weight": 1.0,
    },
    {
        "framework": "REG",
        "code": "REG_D4",
        "name": "Audit Trail",
        "description": "FINMA Circ 2023/1 / MAS TRM",
        "scoring_type": "Blocking",
        "is_mandatory": True,
        "blocking_threshold": 2,
        "score_5_criteria": (
            "Reasoning traceable, output storable as audit record, "
            "named human accountable before output used in regulated process."
        ),
        "weight": 1.0,
    },
    {
        "framework": "REG",
        "code": "REG_D5",
        "name": "Operational Resilience",
        "description": "FINMA Circ 2023/1 / FCA PS21/3",
        "scoring_type": "Blocking",
        "is_mandatory": True,
        "blocking_threshold": 2,
        "score_5_criteria": (
            "Failure modes defined, fallback declared, no single "
            "point of failure in critical process."
        ),
        "weight": 1.0,
    },
    {
        "framework": "REG",
        "code": "REG_D6",
        "name": "Outsourcing Controls",
        "description": "FINMA Circ 2018/3 / MAS Notice 655",
        "scoring_type": "Blocking",
        "is_mandatory": True,
        "blocking_threshold": 2,
        "score_5_criteria": (
            "Data residency declared, sub-processing restricted, "
            "audit rights documented for third-party deployments."
        ),
        "weight": 1.0,
    },
    # --- OWASP LLM Top 10 (advisory, scoring_type=Advisory) ---
    {
        "framework": "OWASP",
        "code": "OWASP_LLM01",
        "name": "Prompt Injection Prevention",
        "description": "LLM01:2025",
        "scoring_type": "Advisory",
        "is_mandatory": False,
        "blocking_threshold": None,
        "score_5_criteria": "",
        "weight": 1.0,
    },
    {
        "framework": "OWASP",
        "code": "OWASP_LLM02",
        "name": "Sensitive Info Disclosure",
        "description": "LLM02:2025",
        "scoring_type": "Advisory",
        "is_mandatory": False,
        "blocking_threshold": None,
        "score_5_criteria": "",
        "weight": 1.0,
    },
    {
        "framework": "OWASP",
        "code": "OWASP_LLM06",
        "name": "Excessive Agency",
        "description": "LLM06:2025",
        "scoring_type": "Advisory",
        "is_mandatory": False,
        "blocking_threshold": None,
        "score_5_criteria": "",
        "weight": 1.0,
    },
    {
        "framework": "OWASP",
        "code": "OWASP_LLM08",
        "name": "Overreliance",
        "description": "LLM08:2025",
        "scoring_type": "Advisory",
        "is_mandatory": False,
        "blocking_threshold": None,
        "score_5_criteria": "",
        "weight": 1.0,
    },
    {
        "framework": "OWASP",
        "code": "OWASP_LLM09",
        "name": "Misinformation",
        "description": "LLM09:2025",
        "scoring_type": "Advisory",
        "is_mandatory": False,
        "blocking_threshold": None,
        "score_5_criteria": "",
        "weight": 1.0,
    },
    # --- NIST AI RMF (advisory, scoring_type=Maturity) ---
    {
        "framework": "NIST",
        "code": "NIST_GOVERN_1",
        "name": "Governance Accountability",
        "description": "NIST AI RMF Govern 1.1",
        "scoring_type": "Maturity",
        "is_mandatory": False,
        "blocking_threshold": None,
        "score_5_criteria": "",
        "weight": 1.0,
    },
    {
        "framework": "NIST",
        "code": "NIST_MAP_1",
        "name": "Context Declaration",
        "description": "NIST AI RMF Map 1.1",
        "scoring_type": "Maturity",
        "is_mandatory": False,
        "blocking_threshold": None,
        "score_5_criteria": "",
        "weight": 1.0,
    },
    {
        "framework": "NIST",
        "code": "NIST_MEASURE_1",
        "name": "Quality Monitoring",
        "description": "NIST AI RMF Measure 2.5",
        "scoring_type": "Maturity",
        "is_mandatory": False,
        "blocking_threshold": None,
        "score_5_criteria": "",
        "weight": 1.0,
    },
    {
        "framework": "NIST",
        "code": "NIST_MANAGE_1",
        "name": "Review Trigger",
        "description": "NIST AI RMF Manage 1.3",
        "scoring_type": "Maturity",
        "is_mandatory": False,
        "blocking_threshold": None,
        "score_5_criteria": "",
        "weight": 1.0,
    },
    # --- ISO 42001 (advisory, scoring_type=Alignment) ---
    {
        "framework": "ISO",
        "code": "ISO42001_6_1",
        "name": "Risk Assessment",
        "description": "ISO 42001 Clause 6.1",
        "scoring_type": "Alignment",
        "is_mandatory": False,
        "blocking_threshold": None,
        "score_5_criteria": "",
        "weight": 1.0,
    },
    {
        "framework": "ISO",
        "code": "ISO42001_8_4",
        "name": "Data Quality",
        "description": "ISO 42001 Clause 8.4",
        "scoring_type": "Alignment",
        "is_mandatory": False,
        "blocking_threshold": None,
        "score_5_criteria": "",
        "weight": 1.0,
    },
]


def seed_dimensions(db: Session) -> None:
    """Insert seed dimensions if they don't already exist. Idempotent."""
    for dim_data in SEED_DIMENSIONS:
        existing = db.query(ScoringDimension).filter_by(code=dim_data["code"]).first()
        if existing:
            continue
        dim = ScoringDimension(
            framework=dim_data["framework"],
            code=dim_data["code"],
            name=dim_data["name"],
            description=dim_data["description"],
            scoring_type=dim_data["scoring_type"],
            is_mandatory=dim_data["is_mandatory"],
            blocking_threshold=dim_data["blocking_threshold"],
            score_5_criteria=dim_data["score_5_criteria"],
            weight=dim_data["weight"],
            active=True,
        )
        db.add(dim)
    db.commit()
