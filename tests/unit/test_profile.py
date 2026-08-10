import json

from jobos.profile.keyword_extractor import extract_target_keywords
from jobos.profile.optimizer import analyze_profile

JOB_DESCRIPTIONS = [
    "Looking for a Python developer with AWS experience.",
    "Need someone strong in FastAPI and system design.",
]


def _llm_json(payload: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(payload)}}]}


async def test_analyze_profile_returns_score(mocker):
    """Test profile analysis returns 0-100 score."""
    mocker.patch(
        "jobos.profile.optimizer.acompletion",
        return_value=_llm_json(
            {
                "score": 62,
                "suggestions": [{"section": "summary", "suggestion": "Add measurable outcomes."}],
                "headline_options": ["Backend Engineer | Python, AWS"],
            }
        ),
    )

    result = await analyze_profile(
        {"headline": "Software Engineer", "summary": "Building scalable systems.", "experience": []}
    )

    assert 0 <= result["score"] <= 100
    assert isinstance(result["suggestions"], list)
    assert result["score"] != 85.5, "must not be the old hardcoded score"


async def test_keyword_gaps_come_from_real_job_descriptions(mocker):
    mocker.patch(
        "jobos.profile.optimizer.acompletion",
        return_value=_llm_json({"score": 50, "suggestions": [], "headline_options": []}),
    )

    result = await analyze_profile(
        {"headline": "Java Developer", "summary": "Spring Boot services."},
        target_job_descriptions=JOB_DESCRIPTIONS,
    )

    # 'python'/'aws' appear in only one of two JDs (0.5) so they qualify;
    # nothing absent from the JDs may be reported as a gap.
    assert "python" in result["keyword_gaps"]
    assert "kubernetes" not in result["keyword_gaps"]


async def test_analysis_falls_back_to_structural_score_when_model_fails(mocker):
    """A model outage must yield a real completeness score, not a fake one."""
    mocker.patch("jobos.profile.optimizer.acompletion", side_effect=RuntimeError("down"))

    result = await analyze_profile({"headline": "", "summary": "", "experience": [], "skills": []})

    assert result["score"] == 0.0
    sections = {s["section"] for s in result["suggestions"]}
    assert sections == {"headline", "summary", "experience", "skills"}


async def test_structural_fallback_rewards_a_complete_profile(mocker):
    mocker.patch("jobos.profile.optimizer.acompletion", side_effect=RuntimeError("down"))

    result = await analyze_profile(
        {
            "headline": "Backend Engineer",
            "summary": "x" * 250,
            "experience": [{"company": "Acme"}],
            "skills": ["python"],
        }
    )

    assert result["score"] == 100.0
    assert result["suggestions"] == []


def test_extract_target_keywords():
    """Test keyword extraction from job descriptions."""
    keywords = extract_target_keywords(JOB_DESCRIPTIONS)

    assert isinstance(keywords, dict) and keywords
    assert "python" in keywords
    assert "aws" in keywords
    for score in keywords.values():
        assert isinstance(score, float)


def test_keyword_scores_reflect_document_frequency():
    """A term in every description must outrank one in a single description."""
    keywords = extract_target_keywords(
        ["python and aws", "python and fastapi", "python services"]
    )

    assert keywords["python"] == 1.0
    assert keywords["aws"] < keywords["python"]


def test_multi_word_skills_survive_tokenization():
    keywords = extract_target_keywords(["Strong system design skills required."])

    assert "system design" in keywords
    # The phrase must not also pollute the results as bare unigrams.
    assert "system" not in keywords


def test_boilerplate_words_are_not_keywords():
    keywords = extract_target_keywords(["We are looking for a candidate with strong experience."])

    for filler in ("looking", "candidate", "experience", "strong"):
        assert filler not in keywords


def test_no_descriptions_yields_no_keywords():
    assert extract_target_keywords([]) == {}
