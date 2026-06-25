from __future__ import annotations

import os
import sys
from argparse import ArgumentParser
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import json

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

os.environ["LLM_PROVIDER"] = "gemini"
os.environ["LLM_PROVIDER_CHAIN"] = "gemini"

from app.ai.extraction.schemas import CVExtraction, JDExtraction, ProjectItem, SkillEvidence
from app.ai.interview.schemas import (
    ConversationTurn,
    EvaluationState,
    InterviewReport,
    InterviewConfig,
    InterviewRuntimeContext,
    MatchingResult,
)
from app.ai.interview.service import (
    build_coverage_state,
    generate_interview_report,
    generate_next_turn,
)


BAD_TECH_LEAD_TERMS = (
    "clear and specific communication",
    "technical problem solving",
    "critical thinking",
    "project ownership",
)
BAD_TECHNICAL_TERMS = (
    "vì sao em quan tâm",
    "mục tiêu nghề nghiệp",
    "clear and specific communication",
    "quyết định quan trọng nhất",
    "kết quả cụ thể nào cho thấy",
    "tình huống cụ thể em đã sử dụng",
)
TECHNICAL_SIGNALS = (
    "code",
    "query",
    "sql",
    "endpoint",
    "status code",
    "debug",
    "log",
    "docker",
    "container",
    "output",
    "edge case",
    "exception",
    "request",
    "response",
    "viết",
    "truy vấn",
    "lỗi",
    "kiểm tra",
    "đầu vào",
    "đầu ra",
)


@dataclass(frozen=True)
class Case:
    name: str
    mode: str
    answer_style: str
    max_questions: int


def main() -> int:
    parser = ArgumentParser(description="Run Gemini-backed interview regression cases.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional directory where each case transcript is saved as a JSON file.",
    )
    parser.add_argument(
        "--mode",
        choices=("tech_lead", "technical_check"),
        default=None,
        help="Optional interview mode filter.",
    )
    args = parser.parse_args()
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)

    cases = [
        Case("tech_lead_strong_candidate", "tech_lead", "strong", 12),
        Case("tech_lead_vague_candidate", "tech_lead", "vague", 12),
        Case("technical_check_strong_candidate", "technical_check", "technical_strong", 10),
        Case("technical_check_weak_candidate", "technical_check", "technical_weak", 10),
    ]
    if args.mode:
        cases = [case for case in cases if case.mode == args.mode]
    failures = []
    for case in cases:
        transcript, flags, turn_metadata, report, report_metadata, answer_evaluations = run_case(case)
        print(f"\n=== {case.name} ({case.mode}) ===")
        for index, turn in enumerate(transcript, start=1):
            print(f"Q{index}: {turn.question}")
            print(f"A{index}: {turn.answer}")
        if flags:
            print("FLAGS:")
            for flag in flags:
                print(f"- {flag}")
            failures.extend(f"{case.name}: {flag}" for flag in flags)
        else:
            print("FLAGS: none")
        if args.output_dir:
            _write_case_json(
                args.output_dir,
                case,
                transcript,
                flags,
                turn_metadata,
                report,
                report_metadata,
                answer_evaluations,
            )

    if failures:
        print("\nFAILED REGRESSION")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("\nPASSED REGRESSION")
    return 0


def run_case(
    case: Case,
) -> tuple[list[ConversationTurn], list[str], list[dict], InterviewReport | None, dict, list[dict]]:
    context = _context(case)
    transcript: list[ConversationTurn] = []
    flags: list[str] = []
    turn_metadata: list[dict] = []
    answer_evaluations: list[dict] = []
    previous_questions: set[str] = set()

    while True:
        result = generate_next_turn(context)
        flags.extend(_provider_flags(result.provider_metadata))
        if result.planner_output.previous_answer_evaluation:
            answer_evaluations.append(
                {
                    "sequence": len(transcript),
                    "question": transcript[-1].question if transcript else "",
                    "answer": transcript[-1].answer if transcript else "",
                    "evaluation": result.planner_output.previous_answer_evaluation.model_dump(mode="json"),
                }
            )
        question = result.question.strip()
        if not question:
            break

        normalized_question = question.casefold()
        if normalized_question in previous_questions:
            flags.append(f"repeated exact question: {question}")
        previous_questions.add(normalized_question)
        flags.extend(_question_flags(case, question))

        answer = _answer_for(case.answer_style, question)
        turn_metadata.append(
            {
                "sequence": len(transcript) + 1,
                "phase": result.planner_output.current_phase,
                "topic_key": result.planner_output.question_plan.topic_key,
                "question_type": result.planner_output.question_plan.question_type,
                "difficulty": result.planner_output.question_plan.difficulty,
                "provider_metadata": _safe_metadata(result.provider_metadata),
            }
        )
        transcript.append(
            ConversationTurn(
                question=question,
                answer=answer,
                phase=result.planner_output.current_phase,
                topic_key=result.planner_output.question_plan.topic_key,
            )
        )

        context = context.model_copy(
            update={
                "interview_config": context.interview_config.model_copy(
                    update={"current_phase": result.planner_output.current_phase}
                ),
                "history": transcript,
                "coverage_state": result.coverage_state,
                "evaluation_state": result.evaluation_state,
                "question_count": len(transcript),
                "current_topic": result.planner_output.question_plan.topic_key,
                "current_difficulty": result.planner_output.question_plan.difficulty,
                "follow_up_count": result.planner_output.follow_up_count,
                "latest_answer": answer,
            }
        )
        if len(transcript) >= case.max_questions:
            final = generate_next_turn(context)
            flags.extend(_provider_flags(final.provider_metadata))
            if final.planner_output.previous_answer_evaluation:
                answer_evaluations.append(
                    {
                        "sequence": len(transcript),
                        "question": transcript[-1].question if transcript else "",
                        "answer": transcript[-1].answer if transcript else "",
                        "evaluation": final.planner_output.previous_answer_evaluation.model_dump(mode="json"),
                    }
                )
            if final.question:
                flags.append("did not stop at max_questions")
            break

    flags.extend(_session_flags(case, transcript))
    report: InterviewReport | None = None
    report_metadata: dict = {}
    if transcript:
        try:
            report, report_metadata = generate_interview_report(
                context,
                answer_evaluations=answer_evaluations,
            )
            flags.extend(_report_flags(case, report))
            flags.extend(_provider_flags({"report": report_metadata}))
        except Exception as exc:
            flags.append(f"report generation failed: {exc}")
    return transcript, flags, turn_metadata, report, report_metadata, answer_evaluations


def _context(case: Case) -> InterviewRuntimeContext:
    config = InterviewConfig(
        interview_mode=case.mode,  # type: ignore[arg-type]
        language="vi",
        candidate_level="student",
        target_role="Backend AI Engineer Intern",
        current_phase="cv_verification" if case.mode == "technical_check" else "career",
        allowed_next_phases=(
            ["cv_verification", "problem_solving", "completed"]
            if case.mode == "technical_check"
            else ["cv_verification", "problem_solving", "behavioral", "candidate_questions", "completed"]
        ),
        min_questions=3,
        max_questions=case.max_questions,
        max_follow_ups_per_topic=2,
    )
    cv = CVExtraction(
        summary="Backend student with API, Docker, FastAPI and simple AI integration projects.",
        skills=[
            SkillEvidence(name="Python", evidence="Built API and text processing scripts"),
            SkillEvidence(name="FastAPI", evidence="Implemented login and CRUD endpoints"),
            SkillEvidence(name="Docker", evidence="Containerized a backend service"),
        ],
        projects=[
            ProjectItem(
                name="AI backend demo",
                description="FastAPI service with JWT auth, PostgreSQL, Docker, and a simple text AI endpoint.",
                technologies=["Python", "FastAPI", "Docker", "PostgreSQL", "JWT"],
            )
        ],
    )
    jd = JDExtraction(
        title="Backend AI Engineer Intern",
        required_skills=[
            SkillEvidence(name="Python"),
            SkillEvidence(name="FastAPI"),
            SkillEvidence(name="Docker"),
        ],
        nice_to_have_skills=[SkillEvidence(name="SQL")],
        responsibilities=[
            "Build backend APIs",
            "Integrate AI model calls",
            "Debug production-like issues",
        ],
        seniority="intern",
    )
    context = InterviewRuntimeContext(
        cv=cv,
        job_description=jd,
        matching_result=MatchingResult(
            matched_skills=["python", "fastapi", "docker"],
            missing_skills=["sql"],
            score=76,
        ),
        interview_config=config,
    )
    return context.model_copy(update={"coverage_state": build_coverage_state(context)})


def _answer_for(style: str, question: str) -> str:
    lower = question.casefold()
    if style == "vague":
        return "Em có làm qua trong đồ án và em thường debug bằng cách xem log rồi sửa dần."
    if style == "technical_weak":
        return "Em chưa chắc cú pháp, nhưng em sẽ thử chạy và xem lỗi trước."
    if style == "technical_strong":
        if "dockerfile" in lower:
            return (
                "Em dùng `FROM python:3.12-slim`, `WORKDIR /app`, copy requirements, "
                "`RUN pip install -r requirements.txt`, copy source, `EXPOSE 8000`, "
                "và `CMD [\"uvicorn\", \"app.main:app\", \"--host\", \"0.0.0.0\", \"--port\", \"8000\"]`."
            )
        if "db_url" in lower or "biến môi trường" in lower or "environment" in lower:
            return (
                "Em không hardcode `DB_URL` trong Dockerfile. Khi chạy container em truyền bằng "
                "`docker run -e DB_URL=postgresql://... -p 8000:8000 image`, hoặc dùng `--env-file .env` "
                "trong môi trường local/CI để tách secret khỏi image."
            )
        if "dependency injection" in lower or "token" in lower or "xác thực" in lower:
            return (
                "Em tạo dependency `get_current_user` đọc `Authorization: Bearer`, verify JWT bằng secret "
                "từ env, nếu token thiếu hoặc sai thì raise `HTTPException(status_code=401)`. Endpoint cần auth "
                "sẽ khai báo `current_user = Depends(get_current_user)`."
            )
        if "fastapi" in lower or "endpoint" in lower:
            return (
                "Em tạo Pydantic model gồm `email: EmailStr`, `password: str`, endpoint POST. "
                "Input thiếu field FastAPI trả 422, sai password trả 401, lỗi server mới là 500."
            )
        if "sql" in lower or "query" in lower:
            if "gmail" in lower:
                return "Em viết `SELECT name, email FROM users WHERE email LIKE '%@gmail.com';`."
            return (
                "Em dùng `GROUP BY user_id`, lọc `created_at >= now() - interval '30 days'`, "
                "và dùng `COALESCE(sum(total), 0)` nếu cần tránh NULL."
            )
        if "list comprehension" in lower or "số chẵn" in lower or "so chan" in lower:
            return "Em viết `[x * x for x in [1, 2, 3, 4, 5, 6] if x % 2 == 0]`, output là `[4, 16, 36]`."
        if "vòng lặp for" in lower or "for" in lower and "1 đến 10" in lower:
            return "Em viết `for x in range(1, 11):\\n    if x % 2 == 0:\\n        print(x)`."
        if "danh sách" in lower or "list" in lower:
            return "Em viết `numbers = [1, 2, 3, 4, 5]` rồi xử lý bằng vòng lặp hoặc list comprehension tùy yêu cầu."
        if "try-except" in lower or "chia" in lower:
            return (
                "Em viết `try: result = a / b` rồi `except ZeroDivisionError: return None` hoặc trả lỗi rõ ràng. "
                "Em cũng validate `b != 0` trước nếu đây là input từ request."
            )
        return (
            "Em sẽ reproduce bằng cURL, xem stack trace Uvicorn, kiểm tra request body, "
            "log trước/sau service và DB query, rồi thêm test case cho lỗi đó."
        )
    if "jwt" in lower:
        return (
            "Trong project login API, em tự làm phần JWT auth. Bug khó nhất là secret khác giữa local "
            "và server làm token verify fail. Em log config fingerprint lúc startup, kiểm tra env, "
            "đồng bộ secret và thêm fail-fast nếu thiếu biến môi trường."
        )
    if "docker" in lower:
        if "copy" in lower and "add" in lower:
            return (
                "Em dùng `COPY` cho source vì hành vi rõ ràng và chỉ copy file/thư mục local. "
                "`ADD` có thêm tự giải nén tar hoặc tải URL nên dễ gây side effect, em chỉ dùng khi thật sự cần."
            )
        if "0.0.0.0" in lower or "localhost" in lower or "127.0.0.1" in lower:
            return (
                "Trong container, bind `127.0.0.1` chỉ lắng nghe loopback bên trong container. "
                "Bind `0.0.0.0` giúp Uvicorn lắng nghe mọi interface, rồi port mapping `8000:8000` mới truy cập từ host được."
            )
        return (
            "Em containerize FastAPI service bằng Dockerfile, bind Uvicorn vào `0.0.0.0`, map port "
            "`8000:8000`, và debug lỗi không truy cập được bằng `docker ps`, `docker logs`, "
            "rồi `docker exec` curl nội bộ."
        )
    if "ai" in lower or "model" in lower:
        if "timeout" in lower or "fallback" in lower or "asyncio" in lower:
            return (
                "Em bọc call model bằng timeout, ví dụ `asyncio.wait_for(call_model(payload), timeout=10)`. "
                "Nếu timeout thì log latency/status, trả fallback message thân thiện và không retry vô hạn trong request."
            )
        return (
            "Với endpoint AI text, em tách service gọi model khỏi router, log latency và status, "
            "thêm timeout/fallback message, và không lưu prompt raw nếu có dữ liệu nhạy cảm."
        )
    if "sql" in lower or "join" in lower or "group by" in lower or "orders" in lower:
        return (
            "Em viết `SELECT u.name, SUM(o.amount) AS total_amount FROM users u "
            "JOIN orders o ON o.user_id = u.id GROUP BY u.id, u.name HAVING SUM(o.amount) > 1000000;`. "
            "Nếu query chậm em xem `EXPLAIN`, index trên `orders.user_id`, và số dòng sau JOIN."
        )
    if "list comprehension" in lower or "sá»‘ cháºµn" in lower or "so chan" in lower:
        return "Em viết `[x * x for x in numbers if x % 2 == 0]`; với `[1, 2, 3, 4]` thì output là `[4, 16]`."
    if "try-except" in lower or "connectionerror" in lower or "exception" in lower:
        return (
            "Em viết `try: data = fetch_data()` rồi `except ConnectionError as exc: "
            "logger.warning('fetch failed', exc_info=exc); return None`. Với API thật em sẽ trả lỗi rõ hoặc fallback."
        )
    return (
        "Em trực tiếp xây API CRUD và login, tách controller sang service để dễ test. Khi endpoint "
        "trả 500, em reproduce bằng cURL, so expected/actual, xem stack trace, thêm log ở service/DB, "
        "và sau khi sửa thì debug time giảm từ khoảng 30 phút xuống 10 phút."
    )


def _question_flags(case: Case, question: str) -> list[str]:
    lower = question.casefold()
    flags: list[str] = []
    if case.mode == "tech_lead":
        for term in BAD_TECH_LEAD_TERMS:
            if term in lower:
                flags.append(f"tech_lead exposed competency label: {term}")
    if case.mode == "technical_check":
        for term in BAD_TECHNICAL_TERMS:
            if term in lower:
                flags.append(f"technical_check asked non-technical prompt: {term}")
        if not any(signal in lower for signal in TECHNICAL_SIGNALS):
            flags.append("technical_check question lacks code/query/debug/output signal")
    return flags


def _provider_flags(metadata: dict) -> list[str]:
    flags: list[str] = []
    deterministic_guard_errors = (
        "This topic must stop after weak",
        "The follow-up limit",
        "An incomplete answer requires",
        "An incomplete answer must be clarified",
        "Technical check mode requires",
        "Generated question repeats",
        "Question contains multiple",
        "Tech lead question repeats a direct coding/query task",
        "Tech lead has reached the direct coding/query task limit",
        "follow_up_count must reset when switching topics",
    )
    for feature in ("planner", "question_generator", "report"):
        feature_meta = metadata.get(feature) or {}
        if feature_meta.get("fallback"):
            error = str(feature_meta.get("error", "unknown error"))
            if any(allowed in error for allowed in deterministic_guard_errors):
                continue
            flags.append(f"{feature} used provider/unknown fallback: {error}")
            continue
        provider = feature_meta.get("provider")
        if provider and provider != "gemini":
            flags.append(f"{feature} used provider {provider}, expected gemini")
    return flags


def _safe_metadata(metadata: dict) -> dict:
    safe = {}
    for feature, feature_meta in metadata.items():
        if not isinstance(feature_meta, dict):
            continue
        safe[feature] = {
            key: value
            for key, value in feature_meta.items()
            if key
            in {
                "provider",
                "model",
                "input_tokens",
                "output_tokens",
                "attempts",
                "fallback",
                "error",
                "backend_overrode_early_finish",
            }
        }
    return safe


def _write_case_json(
    output_dir: Path,
    case: Case,
    transcript: list[ConversationTurn],
    flags: list[str],
    turn_metadata: list[dict],
    report: InterviewReport | None,
    report_metadata: dict,
    answer_evaluations: list[dict],
) -> None:
    payload = {
        "case": case.name,
        "mode": case.mode,
        "answer_style": case.answer_style,
        "max_questions": case.max_questions,
        "generated_at": datetime.now(UTC).isoformat(),
        "flags": flags,
        "report": report.model_dump(mode="json") if report else None,
        "report_metadata": _safe_metadata({"report": report_metadata}).get("report", {}),
        "answer_evaluations": answer_evaluations,
        "turns": [
            {
                "sequence": index,
                "question": turn.question,
                "answer": turn.answer,
                "phase": turn.phase,
                "topic_key": turn.topic_key,
                **(turn_metadata[index - 1] if index - 1 < len(turn_metadata) else {}),
            }
            for index, turn in enumerate(transcript, start=1)
        ],
    }
    path = output_dir / f"{case.name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _report_flags(case: Case, report: InterviewReport) -> list[str]:
    flags: list[str] = []
    dimensions = {dimension.key: dimension for dimension in report.dimensions}
    total_weight = sum(dimension.weight for dimension in report.dimensions)
    if total_weight != 100:
        flags.append(f"report weights sum to {total_weight}, expected 100")
    if len(dimensions) != 5:
        flags.append("report does not contain 5 unique dimensions")
    expected_weights = (
        {
            "technical_knowledge": 30,
            "practical_experience": 20,
            "problem_solving": 20,
            "communication": 20,
            "critical_thinking": 10,
        }
        if case.mode == "tech_lead"
        else {
            "technical_knowledge": 30,
            "practical_experience": 25,
            "problem_solving": 25,
            "communication": 10,
            "critical_thinking": 10,
        }
    )
    for key, expected_weight in expected_weights.items():
        actual = dimensions.get(key)
        if actual is None:
            flags.append(f"report missing dimension: {key}")
        elif actual.weight != expected_weight:
            flags.append(
                f"report dimension {key} weight={actual.weight}, expected {expected_weight}"
            )
    weighted_score = round(
        sum(dimension.score * dimension.weight for dimension in report.dimensions) / 100
    )
    if report.overall_score != weighted_score:
        flags.append(
            f"report overall_score={report.overall_score}, expected weighted score {weighted_score}"
        )
    return flags


def _session_flags(case: Case, transcript: list[ConversationTurn]) -> list[str]:
    flags: list[str] = []
    if not transcript:
        flags.append("no questions produced")
        return flags
    if len(transcript) > case.max_questions:
        flags.append(f"exceeded max_questions={case.max_questions}")
    if case.answer_style in {"strong", "technical_strong"} and len(transcript) == case.max_questions:
        flags.append("strong candidate reached max instead of stopping early")
    if case.mode == "tech_lead":
        session_text = "\n".join(
            f"{turn.topic_key}\n{turn.question}\n{turn.answer}" for turn in transcript
        ).casefold()
        required_skills = {"fastapi", "docker"}
        for required_skill in required_skills:
            if required_skill not in session_text:
                flags.append(f"tech_lead missing required JD/CV verification skill: {required_skill}")
        if "python" not in session_text and "fastapi" not in session_text:
            flags.append("tech_lead missing required JD/CV verification skill: python")
        direct_task_terms = (
            "kiểm tra kỹ năng lập trình",
            "viết code",
            "viết một đoạn code",
            "viết đoạn code",
            "viết một đoạn mã",
            "viết đoạn mã",
            "viết một câu lệnh sql",
            "viết câu lệnh sql",
            "viết sql",
            "viết một truy vấn",
            "viết query",
            "viết truy vấn",
            "viết dockerfile",
            "lọc ra các số chẵn",
            "trả về một danh sách",
            "coding test",
            "programming skill test",
            "write code",
            "write a snippet",
            "write sql",
            "write a sql",
            "write query",
            "write a query",
            "write dockerfile",
        )
        direct_task_count = 0
        for turn in transcript:
            question_lower = turn.question.casefold()
            if any(term in question_lower for term in direct_task_terms):
                direct_task_count += 1
        if direct_task_count > 2:
            flags.append(f"tech_lead asked {direct_task_count} direct coding/query tasks, expected at most 2")
        topics = {turn.topic_key for turn in transcript}
        scenario_terms = ("giả sử", "suppose", "scenario", "tình huống", "flow", "thiết kế")
        if not any(topic.startswith("jd_scenario_") for topic in topics) and not any(
            term in session_text for term in scenario_terms
        ):
            flags.append("tech_lead missing JD-based work scenario")
    if case.mode == "technical_check" and len(transcript) < 5:
        flags.append("technical_check ended before collecting enough technical coverage")
    return flags


if __name__ == "__main__":
    sys.exit(main())
