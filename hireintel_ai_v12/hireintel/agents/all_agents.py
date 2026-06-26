"""
HireIntel AI — All 12 Agents
FIX 3: Uses llama-3.3-70b-versatile (llama3-70b-8192 decommissioned)
"""
import json, re
from config import get_groq_client, GROQ_MODEL


def _chat(system: str, user: str, temp: float = 0.2) -> str:
    client = get_groq_client()
    resp = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=temp,
        max_tokens=4096,
    )
    return resp.choices[0].message.content.strip()


def _parse(raw: str):
    raw = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
    try:
        return json.loads(raw)
    except Exception:
        for sc, ec in [('{', '}'), ('[', ']')]:
            s, e = raw.find(sc), raw.rfind(ec)
            if s != -1 and e != -1:
                try:
                    return json.loads(raw[s:e+1])
                except Exception:
                    pass
    return {"error": "parse_failed", "raw": raw[:300]}


# 1. JD ANALYZER
def analyze_jd(jd_text: str) -> dict:
    system = """You are the JD Analyzer Agent. Analyze the job description.
Return ONLY valid JSON with keys:
role_title, primary_skills (list max 6), secondary_skills (list max 6),
must_have (list), nice_to_have (list), experience_years (string),
domain (string), key_responsibilities (list max 5),
evaluation_criteria (list), jd_summary (string 2-3 sentences).
Return ONLY JSON."""
    raw = _chat(system, f"Analyze this JD:\n\n{jd_text[:4000]}", temp=0.1)
    return _parse(raw)


# 2. SKILL MATCHER
def match_candidate(candidate_text: str, jd_analysis: dict,
                    candidate_name: str = "Candidate", rag_score: float = 0.0) -> dict:
    system = """You are the Skill Matcher Agent. Evaluate candidate vs JD.
Return ONLY valid JSON with keys:
candidate_name, overall_fit_score (0-100 integer),
primary_skill_match (0-100), secondary_skill_match (0-100),
experience_match (0-100), must_have_met (list), must_have_missing (list),
skill_gaps (list), strengths (list max 4),
recommendation (one of: Strongly Recommend/Recommend/Borderline/Do Not Recommend),
shortlist (boolean), match_reason (2 sentences),
candidate_email (string, extract from resume or empty),
years_experience (string).
Return ONLY JSON."""
    user = f"""Candidate: {candidate_name}
RAG Score: {rag_score}%
Role: {jd_analysis.get('role_title','N/A')}
Primary Skills: {', '.join(jd_analysis.get('primary_skills',[]))}
Secondary Skills: {', '.join(jd_analysis.get('secondary_skills',[]))}
Must Have: {', '.join(jd_analysis.get('must_have',[]))}
Experience: {jd_analysis.get('experience_years','N/A')}
Resume:
{candidate_text[:3000]}"""
    raw = _chat(system, user, temp=0.1)
    result = _parse(raw)
    if isinstance(result, dict):
        result["candidate_name"] = candidate_name
        result["rag_score"] = rag_score
    return result


# 3. RUBRIC AGENT
def generate_rubric(jd_analysis: dict) -> dict:
    system = """You are the Rubric Agent. Create a role-specific evaluation rubric.
Return ONLY valid JSON with keys:
role_title, rubric_dimensions (list of objects each with:
  dimension, weight_percent, score_5_desc, score_3_desc, score_1_desc),
minimum_pass_score (integer 0-100),
auto_reject_criteria (list), auto_select_criteria (list).
Weights must sum to 100. Return ONLY JSON."""
    user = f"""Role: {jd_analysis.get('role_title','N/A')}
Domain: {jd_analysis.get('domain','IT')}
Primary Skills: {', '.join(jd_analysis.get('primary_skills',[]))}
Must Have: {', '.join(jd_analysis.get('must_have',[]))}
Experience: {jd_analysis.get('experience_years','N/A')}"""
    raw = _chat(system, user, temp=0.2)
    return _parse(raw)


# 4. QUESTION GENERATOR
def generate_questions(jd_analysis: dict, candidate_match: dict,
                       n_conceptual: int = 4, n_coding: int = 3,
                       n_scenario: int = 3, n_resume: int = 3,
                       resume_text: str = "") -> dict:
    system = f"""You are the Question Generator Agent in HireIntel AI.
Generate targeted interview questions in 4 categories. Return ONLY valid JSON with keys:
role (string),
conceptual_questions (list of {n_conceptual} objects: question, skill_tested,
  difficulty (Easy/Medium/Hard), expected_hints (2-3 bullet points of what a good answer covers)),
coding_questions (list of {n_coding} objects: question, skill_tested,
  difficulty, expected_hints, time_minutes (integer)),
scenario_questions (list of {n_scenario} objects: question, skill_tested,
  difficulty, expected_hints),
resume_based_questions (list of {n_resume} objects: question, skill_tested,
  difficulty, expected_hints, resume_reference (the specific resume detail this is based on)),
evaluation_tips (list of 4 strings — one tip per category).
For resume_based_questions: questions must be DIRECTLY based on the candidate's resume —
their past projects, tools used, roles held, achievements mentioned.
Return ONLY JSON."""
    user = f"""Role: {jd_analysis.get('role_title','N/A')}
Domain: {jd_analysis.get('domain','IT')}
Primary Skills Required: {', '.join(jd_analysis.get('primary_skills',[]))}
Skill Gaps to probe: {', '.join(candidate_match.get('skill_gaps',[])) or 'None'}
Candidate Strengths: {', '.join(candidate_match.get('strengths',[])) or 'General'}
Fit Score: {candidate_match.get('overall_fit_score',0)}%
Experience Required: {jd_analysis.get('experience_years','N/A')}

Candidate Resume (for resume-based questions):
{resume_text[:2000] if resume_text else 'Not available — generate general resume questions'}"""
    raw = _chat(system, user, temp=0.5)
    return _parse(raw)


# 5. CANDIDATE EVALUATOR
def evaluate_response(question: str, category: str, answer: str,
                      rubric_dimension: str = "") -> dict:
    system = """You are the Candidate Evaluator Agent.
Evaluate the interview response. Return ONLY valid JSON with keys:
score (integer 1-5), score_label (Poor/Weak/Adequate/Strong/Exceptional),
what_was_good (string), what_was_missing (string),
follow_up_question (string), red_flags (list, can be empty).
Return ONLY JSON."""
    user = f"""Category: {category}
Question: {question}
Rubric Dimension: {rubric_dimension}
Answer: {answer}"""
    raw = _chat(system, user, temp=0.2)
    return _parse(raw)


# 6. REAL-TIME ASSIST
def realtime_assist(question: str, partial_answer: str, jd_context: dict) -> dict:
    system = """You are the Real-Time Assist Agent. Give the interviewer instant guidance.
Return ONLY valid JSON with keys:
suggestion (string 1-2 sentences),
key_points_to_cover (list of 3 strings),
scoring_hint (string),
alert (string, can be empty).
Return ONLY JSON."""
    user = f"""Role: {jd_context.get('role_title','N/A')}
Question: {question}
Answer so far: {partial_answer or '(still answering)'}
Key Skills: {', '.join(jd_context.get('primary_skills',[]))}"""
    raw = _chat(system, user, temp=0.3)
    return _parse(raw)


# 7. COMMUNICATION AGENT
def assess_communication(all_answers: list, candidate_name: str = "Candidate") -> dict:
    system = """You are the Communication Agent. Evaluate communication quality.
Return ONLY valid JSON with keys:
candidate_name, clarity_score (1-5), structure_score (1-5),
confidence_score (1-5), technical_vocabulary_score (1-5),
overall_communication_score (integer 0-100),
communication_strengths (list), communication_gaps (list),
communication_summary (string 2 sentences).
Return ONLY JSON."""
    answers_text = "\n\n".join(
        f"Q{i+1}: {a.get('question','')}\nA: {a.get('answer','')}"
        for i, a in enumerate(all_answers)
    )
    raw = _chat(system, f"Candidate: {candidate_name}\n\n{answers_text[:4000]}", temp=0.2)
    return _parse(raw)


# 8. FEEDBACK ANALYZER
def analyze_feedback(evaluations: list, candidate_name: str = "Candidate",
                     rubric: dict = None) -> dict:
    system = """You are the Feedback Analyzer Agent. Synthesize all scores into a final assessment.
Return ONLY valid JSON with keys:
candidate_name, final_score (integer 0-100),
verdict (one of: Strong Hire/Hire/Hold for Review/Reject),
overall_summary (string 3-4 sentences),
top_strengths (list of 3), key_concerns (list),
risk_level (Low/Medium/High),
requires_human_review (boolean, true if score 55-70 or red flags exist),
human_review_reason (string, empty if not needed).
Return ONLY JSON."""
    user = f"""Candidate: {candidate_name}
Evaluations: {json.dumps(evaluations, indent=2)[:3000]}
Pass Threshold: {rubric.get('minimum_pass_score', 60) if rubric else 60}"""
    raw = _chat(system, user, temp=0.2)
    return _parse(raw)


# 9. TREND ANALYSIS
def analyze_trends(all_results: list) -> dict:
    if not all_results:
        return {"message": "No data yet."}
    system = """You are the Trend Analysis Agent. Analyze hiring data and surface insights.
Return ONLY valid JSON with keys:
total_processed (integer), avg_fit_score (float), shortlist_rate (string),
top_demanded_skills (list), common_skill_gaps (list),
insights (list of 4 strings), prediction (string),
recommended_actions (list of 3 strings).
Return ONLY JSON."""
    summary = [{"name": r.get("candidate_name","?"), "score": r.get("overall_fit_score",0),
                "shortlist": r.get("shortlist",False), "gaps": r.get("skill_gaps",[])}
               for r in all_results[:50]]
    raw = _chat(system, f"Results:\n{json.dumps(summary, indent=2)[:4000]}", temp=0.3)
    return _parse(raw)


# 10. KNOWLEDGE MANAGEMENT — find alt JD match
def find_alternative_jd_match(candidate_text: str, past_jd_matches: list,
                               candidate_name: str = "Candidate") -> dict:
    if not past_jd_matches:
        return {"alternative_found": False}
    system = """You are the Knowledge Management Agent.
Check if a candidate suits any past JD. Return ONLY valid JSON with keys:
alternative_found (boolean), best_match_role (string),
match_score (integer 0-100), match_reason (string 2 sentences),
recommended_action (string).
Return ONLY JSON."""
    matches_text = "\n".join(
        f"JD: {m.get('metadata',{}).get('title','?')} | Score: {m.get('score',0)}%"
        for m in past_jd_matches[:5]
    )
    raw = _chat(system,
                f"Candidate: {candidate_name}\nResume: {candidate_text[:1500]}\n\nPast JDs:\n{matches_text}",
                temp=0.2)
    return _parse(raw)


# 11. COLLABORATION AGENT
def generate_team_sync_summary(recent_results: list, best_practices: list = None) -> dict:
    system = """You are the Collaboration Facilitator Agent. Generate a team sync summary.
Return ONLY valid JSON with keys:
sync_title (string), key_highlights (list of 4),
new_best_practices (list of 3), evaluator_alignment_tips (list of 3),
action_items (list), next_sync_agenda (list).
Return ONLY JSON."""
    summary = [{"name": r.get("candidate_name","?"), "score": r.get("overall_fit_score",0),
                "verdict": r.get("recommendation","")} for r in recent_results[:20]]
    bp = "\n".join(best_practices or ["None yet"])
    raw = _chat(system,
                f"Recent evals:\n{json.dumps(summary)}\n\nBest practices:\n{bp}",
                temp=0.4)
    return _parse(raw)


# 12. MANAGER AGENT — final decision
def manager_final_decision(feedback_analysis: dict, communication_assessment: dict,
                            rubric_result: dict, human_approved=None) -> dict:
    system = """You are the Manager Agent. Produce the final hiring decision.
Return ONLY valid JSON with keys:
final_decision (HIRE/HOLD/REJECT),
decision_confidence (High/Medium/Low),
decision_reason (string 3-4 sentences),
composite_score (integer 0-100),
next_steps (list),
offer_priority (High/Medium/Low),
rejection_feedback_to_send (string, empty if HIRE).
Return ONLY JSON."""
    user = f"""Feedback: {json.dumps(feedback_analysis)}
Communication: {json.dumps(communication_assessment)}
Rubric Result: {json.dumps(rubric_result)}
Human Approved: {human_approved if human_approved is not None else 'Pending'}"""
    raw = _chat(system, user, temp=0.1)
    return _parse(raw)

# EXCEL QUESTION ENRICHMENT — adds expected_hints via AI for Excel-sourced questions
def enrich_excel_questions(questions: list, jd_analysis: dict) -> list:
    """
    Takes raw questions from Excel (which have no expected_hints) and uses AI
    to add expected_hints, improve categorization, and set difficulty.
    Processes in one batch call to save API quota.
    """
    if not questions:
        return questions
    system = """You are the Question Generator Agent enriching interview questions.
For each question provided, return ONLY valid JSON array where each object has:
question (original, unchanged),
category (Conceptual/Coding/Scenario — re-categorize accurately),
difficulty (Easy/Medium/Hard),
skill_tested (string),
expected_hints (string — 2-3 bullet points of what a strong answer should cover).
Return ONLY a JSON array, no explanation."""
    q_list = [{"index": i, "question": q.get("question",""),
                "category": q.get("category","Conceptual")}
              for i, q in enumerate(questions)]
    role = jd_analysis.get("role_title","")
    skills = ", ".join(jd_analysis.get("primary_skills",[]))
    user = f"""Role: {role}
Skills: {skills}
Questions to enrich:
{json.dumps(q_list, indent=2)[:3000]}"""
    raw = _chat(system, user, temp=0.3)
    enriched = _parse(raw)
    if not isinstance(enriched, list):
        return questions
    # merge back
    result = list(questions)
    for item in enriched:
        idx = item.get("index")
        if idx is not None and idx < len(result):
            result[idx] = {
                **result[idx],
                "category":      item.get("category",  result[idx].get("category","Conceptual")),
                "difficulty":    item.get("difficulty", result[idx].get("difficulty","Medium")),
                "skill_tested":  item.get("skill_tested", result[idx].get("skill_tested","")),
                "expected_hints":item.get("expected_hints",""),
            }
    return result


# TRANSCRIPT PROCESSING — extract per-question answers from a full meeting transcript
def extract_answers_from_transcript(transcript_text: str, questions: list,
                                     candidate_name: str = "Candidate") -> dict:
    """
    Given a full meeting transcript and the list of interview questions,
    uses AI to find and extract the candidate's answer for each question.
    Returns: { q_index: extracted_answer_text }
    """
    q_list = [
        {"index": i, "category": q.get("category",""),
         "question": q.get("question","")}
        for i, q in enumerate(questions)
    ]
    system = """You are an expert interview analyst.
You are given a full meeting transcript from an interview and a list of interview questions.
For each question, find the section of the transcript where the candidate answered it
and extract their answer as clearly as possible.
If a question was not asked or the answer is not found, return an empty string.

Return ONLY a valid JSON object where:
- keys are the question index as a string (e.g. "0", "1", "2")
- values are the extracted candidate answer text (string)
Do not include any explanation. Return ONLY the JSON object."""

    user = f"""Candidate Name: {candidate_name}

Interview Questions:
{json.dumps(q_list, indent=2)[:2000]}

Full Meeting Transcript:
{transcript_text[:6000]}"""

    raw = _chat(system, user, temp=0.1)
    result = _parse(raw)
    if not isinstance(result, dict):
        return {}
    # normalise keys to int-keyed dict
    return {int(k): v for k, v in result.items() if str(k).isdigit()}


def parse_vtt_transcript(vtt_text: str) -> str:
    """Convert WebVTT (.vtt) format to plain readable text."""
    import re
    lines = vtt_text.splitlines()
    out = []
    for line in lines:
        line = line.strip()
        # skip WEBVTT header, timestamps, numeric cue IDs, blank lines
        if not line:
            continue
        if line == "WEBVTT":
            continue
        if re.match(r"^\d+$", line):
            continue
        if re.match(r"^\d{2}:\d{2}[:\d.,]+ --> ", line):
            continue
        # strip HTML tags like <c> or <v Speaker>
        line = re.sub(r"<[^>]+>", "", line).strip()
        if line:
            out.append(line)
    return "\n".join(out)


# FULL TRANSCRIPT EVALUATION — evaluates ALL questions from transcript in one shot
def evaluate_full_transcript(transcript_text: str, questions: list,
                              jd_analysis: dict,
                              candidate_name: str = "Candidate") -> dict:
    """
    Takes the full meeting transcript and all interview questions.
    In ONE AI call:
      - Extracts what the candidate said for each question
      - Scores each answer 1-5
      - Gives overall feedback, strengths, concerns
      - Returns structured evaluation ready for Feedback & Decision page
    Returns:
      {
        "per_question": [ {q_index, question, category, answer_extracted,
                           score, score_label, what_was_good, what_was_missing,
                           follow_up_question} ],
        "overall_communication_score": int 0-100,
        "communication_strengths": list,
        "communication_gaps": list,
        "overall_summary": str,
        "top_strengths": list,
        "key_concerns": list,
        "final_score": int 0-100,
        "verdict": str,
        "requires_human_review": bool,
        "human_review_reason": str,
      }
    """
    q_list = [{"index": i, "category": q.get("category",""),
                "question": q.get("question",""),
                "skill_tested": q.get("skill_tested","")}
               for i, q in enumerate(questions)]

    system = """You are HireIntel AI — an expert interview analyst and evaluator.
You will receive a full meeting transcript and a list of interview questions.

Your job in ONE response:
1. For each question, find the candidate's answer in the transcript
2. Score it 1-5 (1=Poor, 2=Weak, 3=Adequate, 4=Strong, 5=Exceptional)
3. Note what was good and what was missing
4. Assess overall communication quality
5. Give a final hiring verdict

Return ONLY valid JSON with this exact structure:
{
  "per_question": [
    {
      "q_index": 0,
      "question": "original question text",
      "category": "Conceptual/Coding/Scenario/Resume",
      "answer_extracted": "what candidate said, summarised",
      "score": 4,
      "score_label": "Strong",
      "what_was_good": "string",
      "what_was_missing": "string",
      "follow_up_question": "string"
    }
  ],
  "overall_communication_score": 78,
  "clarity_score": 4,
  "structure_score": 3,
  "confidence_score": 4,
  "communication_strengths": ["list"],
  "communication_gaps": ["list"],
  "communication_summary": "2 sentences",
  "overall_summary": "3-4 sentence summary of the candidate",
  "top_strengths": ["strength 1", "strength 2", "strength 3"],
  "key_concerns": ["concern 1", "concern 2"],
  "final_score": 72,
  "verdict": "Hire",
  "requires_human_review": false,
  "human_review_reason": ""
}

verdict must be one of: Strong Hire / Hire / Hold for Review / Reject
If answer not found in transcript for a question, set answer_extracted to empty string and score to 0.
Return ONLY JSON."""

    user = f"""Candidate: {candidate_name}
Role: {jd_analysis.get('role_title','N/A') if jd_analysis else 'N/A'}
Primary Skills Required: {', '.join(jd_analysis.get('primary_skills',[]) if jd_analysis else [])}

Interview Questions ({len(q_list)} total):
{json.dumps(q_list, indent=2)[:2000]}

Full Meeting Transcript:
{transcript_text[:7000]}"""

    raw = _chat(system, user, temp=0.1)
    result = _parse(raw)
    if not isinstance(result, dict):
        return {"error": "parse_failed", "raw": raw[:300]}
    return result


# INTERVIEW COACH — real-time guidance PER QUESTION while interviewer is asking it
def get_interview_coach_guidance(question: str, category: str,
                                  jd_analysis: dict,
                                  candidate_profile: dict,
                                  question_index: int = 0) -> dict:
    """
    Called BEFORE or DURING asking a question.
    Gives the interviewer:
    - What a great answer looks like (key points)
    - What a weak answer looks like (red flags)
    - 2-3 smart follow-up questions to dig deeper
    - What skill this question is really testing
    - Scoring guide: what earns 5 vs 3 vs 1
    Returns JSON dict.
    """
    system = """You are an expert interview coach sitting next to the interviewer.
For the given interview question, give real-time guidance to help the interviewer
assess the candidate's answer effectively.
Return ONLY valid JSON with:
{
  "what_to_listen_for": ["list of 3-4 key points a strong answer will include"],
  "red_flags": ["list of 2-3 things that indicate weak understanding"],
  "follow_up_questions": ["2-3 smart probing follow-ups to dig deeper"],
  "score_5_looks_like": "what an exceptional answer sounds like in 1 sentence",
  "score_3_looks_like": "what an adequate answer sounds like in 1 sentence",
  "score_1_looks_like": "what a poor answer sounds like in 1 sentence",
  "interviewer_tip": "one practical tip for the interviewer right now",
  "time_suggestion": "how long to let the candidate speak before prompting"
}
Return ONLY JSON."""

    user = f"""Role: {jd_analysis.get('role_title','N/A') if jd_analysis else 'N/A'}
Category: {category}
Question: {question}
Candidate Fit Score: {candidate_profile.get('overall_fit_score',0)}%
Candidate Skill Gaps: {', '.join(candidate_profile.get('skill_gaps',[]) or [])}
Candidate Strengths: {', '.join(candidate_profile.get('strengths',[]) or [])}"""

    raw = _chat(system, user, temp=0.3)
    return _parse(raw)


# FAKE RESUME DETECTOR — screens for suspicious patterns and authenticity risks
def detect_fake_resume(resume_text: str, candidate_name: str = "Candidate",
                       jd_analysis: dict = None) -> dict:
    """
    Analyses resume for red flags indicating it may be fabricated or inflated.
    Returns structured risk assessment.
    """
    system = """You are an expert HR fraud analyst and resume authenticator.
Analyse the resume for signs of fabrication, inflation, or inconsistency.
Return ONLY valid JSON with:
{
  "risk_level": "Low / Medium / High / Critical",
  "risk_score": integer 0-100 (100 = definitely fake),
  "authenticity_verdict": "Likely Genuine / Suspicious / Likely Fabricated",
  "red_flags": [
    {"flag": "description of the red flag", "severity": "Low/Medium/High"}
  ],
  "positive_signals": ["list of things that appear genuine"],
  "inconsistencies": ["list of timeline or skill inconsistencies"],
  "skill_inflation_indicators": ["skills claimed but unlikely given experience"],
  "recommendations": ["what to verify in the interview"],
  "summary": "2-3 sentence overall assessment"
}
Common red flags to check:
- Skills claimed don't match years of experience
- Employment gaps with no explanation
- Companies that don't exist or are unverifiable
- Exact same project descriptions repeated
- Too many buzzwords with no specifics
- Dates that don't add up (overlapping jobs, impossible timelines)
- Education claims that seem inflated
- Generic descriptions with no measurable outcomes
- Skills listed but no projects using them
Return ONLY JSON."""
    user = f"""Candidate: {candidate_name}
Role Applied For: {jd_analysis.get('role_title','N/A') if jd_analysis else 'N/A'}
Required Experience: {jd_analysis.get('experience_years','N/A') if jd_analysis else 'N/A'}
Required Skills: {', '.join(jd_analysis.get('primary_skills',[]) if jd_analysis else [])}

Resume Text:
{resume_text[:5000]}"""
    raw = _chat(system, user, temp=0.1)
    return _parse(raw)
