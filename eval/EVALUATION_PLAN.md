# Evaluation Plan

## Success Criteria

- Uploaded or entered JD can be parsed into schema-valid JSON.
- Parsed JSON can be reviewed/edited before saving.
- Job requests can be created, opened, closed, listed, viewed, updated, and deleted.
- Matching runs only for jobs with `status = open`.
- Match results are ranked by score and include clear missing skill explanations.
- Threshold customization affects labels predictably.

## Metrics

| Metric | Target | How To Measure |
|--------|--------|----------------|
| Parser validity | 90% of test JDs produce schema-valid JSON after validation/edit | Run parser on sample JDs and inspect validation results |
| Matching correctness | 100% on deterministic test cases | Compare output against expected labels and score ordering |
| Status rule correctness | 100% | Closed jobs must not run matching |
| Explanation relevance | Human rating >= 4/5 on sample outputs | Review whether missing skills and gaps match the data |
| Latency | API response acceptable for demo | Record response time for parse and match requests |

## Test Cases

| # | Input | Expected Behavior | Pass/Fail | Notes |
|---|-------|-------------------|-----------|-------|
| 1 | Backend Intern JD requiring Python 7, SQL 6, Docker 4 | Parser extracts title, metadata, and skills; matching ranks Python/SQL students high | TODO | Mock JD |
| 2 | Data Analyst Intern JD requiring SQL 8, Python 6, dashboarding 5 | Students with strong SQL rank highest; weak SQL appears as missing/weak | TODO | Mock JD |
| 3 | AI Engineer Intern JD requiring Python 8, ML 7, LLM 6 | Missing high-importance required ML/LLM prevents `strong_match` | TODO | Mock JD |
| 4 | Frontend Intern JD requiring JavaScript 7, React 7, CSS 5 | Backend-heavy students get partial/not match with clear gaps | TODO | Mock JD |
| 5 | Business Analyst Intern JD requiring communication 7, SQL 5, documentation 6 | Non-code skills are represented and matched consistently | TODO | Mock JD |
| 6 | Closed Backend Intern job | Matching endpoint refuses or skips matching because job is not open | TODO | Status rule |
| 7 | Same JD with thresholds changed to strong 0.9 / partial 0.7 | Match labels become stricter while score ordering stays the same | TODO | Config rule |
| 8 | Malformed Gemini output missing `skills` | Validator rejects output and requests edit/fix before saving | TODO | Validation rule |

## Failure Modes To Watch

- Hallucinated skills not present in the JD.
- Missing required metadata such as title or status.
- Invalid skill score ranges or importance values.
- Closed jobs being matched.
- Overconfident `strong_match` when high-importance required skills are missing.
- Skill aliases causing false gaps, such as `JS` vs `JavaScript`.
- Slow LLM parse response during demo.

## Evaluation Evidence

Add after implementation:

- API test output.
- Sample parsed job JSON.
- Sample ranked match result.
- Screenshots from Streamlit demo.
- Notes for failed cases and fixes.
