"""CV and AI-intensive tool handlers (skill gap, interview sim, career advice, salary)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.permissions import Principal

# Curated career data — static; never AI-generated to avoid provider exposure.
_CAREER_DATA: dict[str, dict] = {
    "software engineer": {
        "overview": (
            "Software engineers design, build, and maintain software systems. Entry roles focus on "
            "frontend, backend, or mobile; senior roles include architecture and tech leadership."
        ),
        "key_skills": [
            "Python/Java/JavaScript",
            "Data Structures & Algorithms",
            "System Design",
            "Git/CI/CD",
            "SQL",
            "Cloud (AWS/GCP/Azure)",
        ],
        "certifications": [
            "AWS Certified Developer",
            "Google Associate Cloud Engineer",
            "Oracle Java Certification",
        ],
        "salary_vnd": {"junior": "15–25M/tháng", "mid": "25–50M/tháng", "senior": "50–120M/tháng"},
        "growth_path": (
            "Junior Dev → Mid Engineer → Senior Engineer → Tech Lead / Staff Engineer → "
            "Engineering Manager"
        ),
        "search_url": "/jobs?q=software+engineer",
    },
    "data scientist": {
        "overview": (
            "Data scientists extract insights from data using statistics, machine learning, and "
            "visualisation. They work in cross-functional teams alongside product and engineering."
        ),
        "key_skills": [
            "Python (pandas, scikit-learn, PyTorch)",
            "SQL",
            "Statistics & Probability",
            "Machine Learning",
            "Data Visualisation",
            "Experiment Design",
        ],
        "certifications": [
            "Google Data Analytics Certificate",
            "AWS Machine Learning Specialty",
            "Databricks Associate",
        ],
        "salary_vnd": {"junior": "18–30M/tháng", "mid": "30–60M/tháng", "senior": "60–130M/tháng"},
        "growth_path": (
            "Data Analyst → Data Scientist → Senior DS → Lead DS / ML Engineer → Head of Data"
        ),
        "search_url": "/jobs?q=data+scientist",
    },
    "product manager": {
        "overview": (
            "Product managers define the product vision, roadmap, and priorities. They work at the "
            "intersection of business, technology, and user experience."
        ),
        "key_skills": [
            "Product Strategy",
            "User Research",
            "Data Analysis",
            "Roadmapping",
            "Stakeholder Management",
            "SQL basics",
            "Agile/Scrum",
        ],
        "certifications": [
            "Product School CPO",
            "PSPO (Scrum.org)",
            "Google UX Design Certificate",
        ],
        "salary_vnd": {"junior": "20–35M/tháng", "mid": "35–70M/tháng", "senior": "70–150M/tháng"},
        "growth_path": "Associate PM → PM → Senior PM → Group PM → Director of Product / CPO",
        "search_url": "/jobs?q=product+manager",
    },
    "marketing manager": {
        "overview": (
            "Marketing managers plan and execute campaigns to drive brand awareness, leads, and "
            "revenue. Digital marketing roles also require analytical and technical skills."
        ),
        "key_skills": [
            "Digital Marketing",
            "SEO/SEM",
            "Content Strategy",
            "Social Media",
            "Data Analytics (GA4)",
            "CRM",
            "Budget Management",
        ],
        "certifications": [
            "Google Ads Certification",
            "Meta Blueprint",
            "HubSpot Content Marketing",
        ],
        "salary_vnd": {"junior": "12–20M/tháng", "mid": "20–40M/tháng", "senior": "40–90M/tháng"},
        "growth_path": (
            "Marketing Executive → Marketing Manager → Senior Manager → Marketing Director → CMO"
        ),
        "search_url": "/jobs?q=marketing+manager",
    },
    "finance analyst": {
        "overview": (
            "Finance analysts evaluate financial data to guide business decisions. They work in "
            "corporate finance, investment banking, consulting, or FP&A."
        ),
        "key_skills": [
            "Financial Modelling",
            "Excel/Google Sheets",
            "Accounting basics",
            "SQL",
            "Business Valuation",
            "PowerPoint",
            "Bloomberg/Reuters",
        ],
        "certifications": ["CFA (CFA Institute)", "ACCA", "CPA", "FRM"],
        "salary_vnd": {"junior": "15–25M/tháng", "mid": "25–55M/tháng", "senior": "55–120M/tháng"},
        "growth_path": "Finance Analyst → Senior Analyst → Manager → Director → CFO",
        "search_url": "/jobs?q=finance+analyst",
    },
}

# Curated salary ranges (VND million/month) — approximate market data 2024–2025.
_SALARY_DB: dict[str, dict] = {
    "software engineer": {
        "tiers": [
            {"years": "0–1", "min": 12, "max": 20},
            {"years": "1–3", "min": 20, "max": 40},
            {"years": "3–6", "min": 35, "max": 70},
            {"years": "6+", "min": 60, "max": 120},
        ],
        "currency": "triệu VND/tháng",
    },
    "data scientist": {
        "tiers": [
            {"years": "0–1", "min": 15, "max": 25},
            {"years": "1–3", "min": 25, "max": 50},
            {"years": "3–6", "min": 45, "max": 80},
            {"years": "6+", "min": 70, "max": 140},
        ],
        "currency": "triệu VND/tháng",
    },
    "product manager": {
        "tiers": [
            {"years": "0–2", "min": 18, "max": 30},
            {"years": "2–5", "min": 30, "max": 65},
            {"years": "5+", "min": 60, "max": 150},
        ],
        "currency": "triệu VND/tháng",
    },
    "marketing manager": {
        "tiers": [
            {"years": "0–2", "min": 10, "max": 18},
            {"years": "2–5", "min": 18, "max": 40},
            {"years": "5+", "min": 35, "max": 80},
        ],
        "currency": "triệu VND/tháng",
    },
    "finance analyst": {
        "tiers": [
            {"years": "0–2", "min": 12, "max": 22},
            {"years": "2–5", "min": 22, "max": 50},
            {"years": "5+", "min": 45, "max": 100},
        ],
        "currency": "triệu VND/tháng",
    },
    "ui ux designer": {
        "tiers": [
            {"years": "0–1", "min": 10, "max": 18},
            {"years": "1–3", "min": 18, "max": 35},
            {"years": "3+", "min": 30, "max": 70},
        ],
        "currency": "triệu VND/tháng",
    },
    "devops engineer": {
        "tiers": [
            {"years": "0–2", "min": 18, "max": 30},
            {"years": "2–5", "min": 30, "max": 60},
            {"years": "5+", "min": 55, "max": 110},
        ],
        "currency": "triệu VND/tháng",
    },
}


async def get_my_cvs(session: AsyncSession, principal: Principal) -> dict:
    from app.modules.documents.application import cv_service

    items, _next, _limit = await cv_service.list_cvs(
        session, principal=principal, cursor=None, limit=10
    )
    return {
        "ok": True,
        "cvs": [
            {
                "id": str(c.get("id", "")),
                "title": c.get("title", "Untitled CV"),
                "status": c.get("status", "draft"),
                "is_primary": c.get("is_primary", False),
                "url": f"/student/cv/{c.get('id', '')}",
            }
            for c in items[:8]
        ],
    }


async def get_skill_gap(session: AsyncSession, principal: Principal, args: dict) -> dict:
    import uuid as _uuid

    if not principal.is_authenticated:
        return {"ok": False, "error": "auth_required"}
    if getattr(principal, "persona", None) not in ("student", "alumni", None):
        return {"ok": False, "error": "student_only"}
    raw_job_id = (args.get("job_id") or "").strip()
    try:
        job_id = _uuid.UUID(raw_job_id)
    except ValueError:
        return {"ok": False, "error": "invalid_job_id"}
    raw_cv_id = (args.get("cv_id") or "").strip() or None
    try:
        from app.modules.documents.application import cv_service
        from app.modules.opportunities.application import job_service

        job_detail = await job_service.get_job(session, principal=principal, job_id=job_id)

        if raw_cv_id:
            cv_id = _uuid.UUID(raw_cv_id)
            cv_detail = await cv_service.get_cv(session, principal=principal, cv_id=cv_id)
        else:
            cvs, _, _ = await cv_service.list_cvs(
                session, principal=principal, cursor=None, limit=10
            )
            primary = next((c for c in cvs if c.get("is_primary")), cvs[0] if cvs else None)
            if primary is None:
                return {"ok": False, "error": "no_cv_found"}
            cv_id = _uuid.UUID(str(primary["id"]))
            cv_detail = await cv_service.get_cv(session, principal=principal, cv_id=cv_id)

        from app.ai.cv.job_fit import CvInput, evaluate

        cv_input = CvInput(
            cv_id=str(cv_id),
            title=cv_detail.get("title", ""),
            language=cv_detail.get("language_code", "vi"),
            sections=cv_detail.get("sections", []),
            last_updated_days=cv_detail.get("last_updated_days", 0),
        )
        outcome = evaluate(job_detail, [cv_input], stale_days=180)
        result = outcome.results[0] if outcome.results else None
        if result is None:
            return {"ok": False, "error": "scoring_failed"}
        return {
            "ok": True,
            "job_id": str(job_id),
            "job_title": job_detail.get("title", ""),
            "cv_id": str(cv_id),
            "cv_title": cv_input.title,
            "score": result.score,
            "bands": result.bands.as_dict(),
            "matched_skills": result.matched_skills[:15],
            "gaps": result.gaps[:15],
            "stale_cv": result.stale,
            "signal": outcome.signal,
            "url": f"/jobs/{job_id}",
        }
    except Exception:
        return {"ok": False, "error": "tool_failed"}


async def get_career_advice(session: AsyncSession, principal: Principal, args: dict) -> dict:
    if not principal.is_authenticated:
        return {"ok": False, "error": "auth_required"}
    role = (args.get("role") or "").strip()
    if not role:
        return {"ok": False, "error": "role_required"}
    current_role = (args.get("current_role") or "").strip() or None

    role_lower = role.lower()
    advice = None
    for key, data in _CAREER_DATA.items():
        if key in role_lower or role_lower in key:
            advice = data
            break

    if advice is None:
        return {
            "ok": True,
            "role": role,
            "overview": (
                f"The {role} career path is growing in Vietnam's job market. Search "
                "for open positions to see current skill requirements and salary ranges."
            ),
            "key_skills": [],
            "certifications": [],
            "salary_vnd": {},
            "growth_path": f"Search for {role} roles on the platform to explore growth paths.",
            "search_url": f"/jobs?q={role.replace(' ', '+')}",
            "current_role": current_role,
        }
    return {"ok": True, "role": role, "current_role": current_role, **advice}


async def get_salary_benchmark(session: AsyncSession, principal: Principal, args: dict) -> dict:
    if not principal.is_authenticated:
        return {"ok": False, "error": "auth_required"}
    role = (args.get("role") or "").strip()
    if not role:
        return {"ok": False, "error": "role_required"}
    city = (args.get("city") or "").strip().lower()
    exp_years = args.get("experience_years")

    role_lower = role.lower().replace("-", " ").replace("_", " ")
    data = None
    for key, val in _SALARY_DB.items():
        if key in role_lower or role_lower in key or any(w in role_lower for w in key.split()):
            data = val
            break

    if data is None:
        return {
            "ok": True,
            "role": role,
            "city": city or "Vietnam",
            "note": (
                f"Salary data for '{role}' is not yet in our benchmark database. Check "
                "active job listings for salary ranges."
            ),
            "search_url": f"/jobs?q={role.replace(' ', '+')}",
            "source": "market_estimate",
        }

    tiers = data["tiers"]
    selected_tier = None
    if exp_years is not None:
        try:
            exp = int(exp_years)
            for tier in tiers:
                yr_range = tier["years"]
                if "+" in yr_range:
                    min_yr = int(yr_range.replace("+", "").strip())
                    if exp >= min_yr:
                        selected_tier = tier
                else:
                    parts = yr_range.split("–")
                    if len(parts) == 2 and int(parts[0]) <= exp < int(parts[1]):
                        selected_tier = tier
                        break
        except (ValueError, TypeError):
            pass

    return {
        "ok": True,
        "role": role,
        "city": city or "Vietnam (Hanoi / HCMC)",
        "currency": data["currency"],
        "tiers": tiers,
        "recommended_tier": selected_tier,
        "disclaimer": (
            "Salary data is approximate market range for 2024–2025. Actual compensation depends on "
            "company, level, and negotiation."
        ),
        "search_url": f"/jobs?q={role.replace(' ', '+')}",
        "source": "market_estimate",
    }


async def start_interview_sim(session: AsyncSession, principal: Principal, args: dict) -> dict:
    if not principal.is_authenticated:
        return {"ok": False, "error": "auth_required"}
    from app.ai.safety.input_guard import sanitize_instruction

    job_id = args.get("job_id") or None
    role = (args.get("role") or "").strip()
    round_type = (args.get("round") or "screening").lower()

    job_title = role
    if job_id and not role:
        try:
            from app.modules.opportunities.application import job_service

            detail = await job_service.get_job(session, principal=principal, job_id=job_id)
            job_title = detail.get("title", "software engineer")
        except Exception:
            job_title = "software engineer"

    if not job_title:
        job_title = "general role"

    safe_role, _ = sanitize_instruction(job_title)
    safe_role = (safe_role or "general role")[:100]

    round_labels = {
        "screening": "initial HR screening",
        "technical": "technical interview",
        "behavioral": "behavioral (STAR-method) interview",
        "final": "final-round leadership interview",
    }
    round_label = round_labels.get(round_type, "screening interview")

    from app.ai.gateway import runtime_config
    from app.ai.gateway.factory import real_provider_active

    if not real_provider_active():
        return {
            "ok": True,
            "role": safe_role,
            "round": round_type,
            "question": (
                f"Tell me about yourself and why you are interested in this {safe_role} position."
            ),
            "tip": (
                "Use the Present-Past-Future structure: who you are now, your relevant experience, "
                "and why this role."
            ),
            "ai_available": False,
        }

    prompt = (
        f"You are an experienced interviewer conducting a {round_label} for a "
        f"{safe_role} position at a Vietnam-based company.\n"
        f"Generate ONE thoughtful interview question appropriate for this round.\n"
        f"Then provide a 1-sentence interviewer tip on what you're listening for.\n"
        f"Format:\nQuestion: <the question>\nTip: <what the interviewer is looking for>"
    )
    from app.ai.gateway.base import AIMessage
    from app.ai.gateway.task_runner import AiTaskRunner

    runner = AiTaskRunner(
        session,
        alias=runtime_config.current().chat_model_alias,
        task_type="interview_sim",
        user_id=principal.user_id,
    )
    try:
        resp = await runner.complete(
            [AIMessage(role="user", content=prompt)],
            temperature=0.7,
            max_tokens=200,
        )
        text = resp.text
        lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
        question = ""
        tip = ""
        for line in lines:
            if line.lower().startswith("question:"):
                question = line[len("question:") :].strip()
            elif line.lower().startswith("tip:"):
                tip = line[len("tip:") :].strip()
        if not question:
            question = lines[0] if lines else "Tell me about yourself."
        return {
            "ok": True,
            "role": safe_role,
            "round": round_type,
            "question": question,
            "tip": tip or "Listen for clarity, structure, and relevant examples.",
            "ai_available": True,
        }
    except Exception:
        return {
            "ok": True,
            "role": safe_role,
            "round": round_type,
            "question": (
                f"Tell me about yourself and why you are interested in this {safe_role} position."
            ),
            "tip": "Use the Present-Past-Future structure.",
            "ai_available": False,
        }
