"""
nlp_engine.py — NLP pipeline using spaCy + sklearn TF-IDF

spaCy usage:
  - English tokenizer + sentencizer pipeline
  - EntityRuler for rule-based SKILL entity tagging across 120+ skills
  - PERSON entity detection for candidate name extraction
  - Linguistic tokens for keyword density analysis

sklearn usage:
  - TfidfVectorizer (1,2)-ngrams + sublinear_tf + cosine_similarity
  - Weighted multi-signal scoring across 4 dimensions
"""

import re
from collections import defaultdict

import spacy
from spacy.lang.en import English

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ── Build spaCy pipeline ───────────────────────────────────────────────────────
nlp = English()
nlp.add_pipe("sentencizer")

SKILL_TAXONOMY = {
    "Programming Languages": [
        "python","java","javascript","typescript","c++","c#","go","golang",
        "rust","kotlin","swift","r","scala","bash","php","ruby","perl",
        "matlab","haskell","elixir","dart","julia","groovy",
    ],
    "ML / AI": [
        "machine learning","deep learning","nlp","natural language processing",
        "computer vision","scikit-learn","tensorflow","pytorch","keras",
        "hugging face","huggingface","transformers","bert","gpt","llm",
        "reinforcement learning","xgboost","lightgbm","pandas","numpy",
        "matplotlib","seaborn","plotly","feature engineering","neural network",
        "random forest","svm","regression","classification","clustering",
        "embedding","rag","langchain","opencv",
    ],
    "Cloud & DevOps": [
        "aws","azure","gcp","google cloud","docker","kubernetes","terraform",
        "ansible","jenkins","github actions","gitlab ci","ci/cd",
        "s3","ec2","lambda","rds","dynamodb","cloudformation",
        "cloud run","bigquery","helm","linux","sagemaker","ecs","fargate",
    ],
    "Data Engineering": [
        "apache spark","pyspark","hadoop","kafka","apache airflow","dbt",
        "etl","data pipeline","data warehouse","snowflake","redshift",
        "databricks","hive","presto","flink","nifi","dask",
    ],
    "Web & Frameworks": [
        "react","node.js","django","flask","fastapi","express","vue",
        "angular","spring boot","graphql","rest api","html","css",
        "tailwind","next.js","nuxt","svelte","rails","laravel",
    ],
    "Databases": [
        "postgresql","mysql","sqlite","mongodb","redis","elasticsearch",
        "cassandra","oracle","firebase","neo4j","influxdb","mariadb","supabase",
    ],
    "Tools & Practices": [
        "git","github","gitlab","jira","confluence","postman","swagger",
        "excel","tableau","power bi","figma","agile","scrum",
        "tdd","microservices","system design","pytest","unit testing",
    ],
}

_ALL_SKILLS_FLAT = {
    skill: cat
    for cat, skills in SKILL_TAXONOMY.items()
    for skill in skills
}

# Add EntityRuler to spaCy pipeline for skill detection
ruler = nlp.add_pipe("entity_ruler", last=True)
ruler.add_patterns([{"label": "SKILL", "pattern": s} for s in _ALL_SKILLS_FLAT])

EDUCATION_KEYWORDS = [
    "bachelor","master","phd","doctorate","b.tech","b.e","m.tech",
    "m.s","m.sc","b.sc","mba","bca","mca","engineering",
    "computer science","information technology","data science",
    "statistics","mathematics","university","college","institute",
    "iit","nit","bits","iisc","iim","georgia tech","mit","stanford",
]

DEGREE_LEVELS = {
    "phd":4,"doctorate":4,"ph.d":4,
    "master":3,"m.tech":3,"m.s":3,"m.sc":3,"mca":3,"mba":3,
    "bachelor":2,"b.tech":2,"b.e":2,"b.sc":2,"bca":2,
}

_DISPLAY_FIX = {
    "nlp":"NLP","llm":"LLM","rag":"RAG","aws":"AWS","gcp":"GCP",
    "sql":"SQL","api":"API","css":"CSS","html":"HTML","tdd":"TDD",
    "ci/cd":"CI/CD","svm":"SVM","gpt":"GPT","rds":"RDS",
}

def _display(skill):
    t = skill.title()
    for k,v in _DISPLAY_FIX.items():
        t = t.replace(k.title(), v)
    return t


def extract_name(text: str) -> str:
    """spaCy PERSON entity detection with heuristic fallback."""
    doc = nlp(text[:600])
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            name = ent.text.strip()
            if 2 <= len(name.split()) <= 4:
                return name
    skip = {"resume","cv","curriculum","vitae","profile","summary","objective","skills"}
    for line in [l.strip() for l in text.split("\n") if l.strip()][:8]:
        if any(c in line for c in ["@","http","|","+","github","linkedin"]):
            continue
        if re.search(r"\d{5,}", line):
            continue
        words = line.split()
        if 2 <= len(words) <= 4:
            if all(w[0].isupper() for w in words if w and w[0].isalpha()):
                if not any(w.lower() in skip for w in words):
                    return line
    return "Unknown Candidate"


def extract_contact(text: str) -> dict:
    email    = re.findall(r"[\w.+\-]+@[\w\-]+\.[a-zA-Z]{2,}", text)
    phone    = re.findall(r"(?:\+?\d{1,3}[\s\-]?)?(?:\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}|[6-9]\d{9})", text)
    github   = re.findall(r"github\.com/([\w\-]+)", text, re.I)
    linkedin = re.findall(r"linkedin\.com/in/([\w\-]+)", text, re.I)
    return {
        "email":    email[0]                          if email    else None,
        "phone":    phone[0].strip()                  if phone    else None,
        "github":   f"github.com/{github[0]}"         if github   else None,
        "linkedin": f"linkedin.com/in/{linkedin[0]}"  if linkedin else None,
    }


def extract_skills(text: str) -> dict:
    """spaCy EntityRuler primary pass + regex secondary pass for robustness."""
    tl = text.lower()
    found: dict = defaultdict(list)

    # Primary: spaCy EntityRuler (linguistic tokenization-aware)
    doc = nlp(tl[:60000])
    for ent in doc.ents:
        if ent.label_ == "SKILL":
            skill = ent.text.strip()
            if skill in _ALL_SKILLS_FLAT:
                cat = _ALL_SKILLS_FLAT[skill]
                d = _display(skill)
                if d not in found[cat]:
                    found[cat].append(d)

    # Secondary: regex whole-word pass (catches multi-word skills spaCy may split)
    for skill, cat in _ALL_SKILLS_FLAT.items():
        if re.search(r"\b" + re.escape(skill) + r"\b", tl):
            d = _display(skill)
            if d not in found[cat]:
                found[cat].append(d)

    return dict(found)


def extract_education(text: str) -> list:
    edu = []
    for line in text.split("\n"):
        ll = line.lower().strip()
        if any(kw in ll for kw in EDUCATION_KEYWORDS) and 10 < len(line.strip()) < 250:
            edu.append(line.strip())
    return list(dict.fromkeys(edu))[:6]


def get_highest_degree(education: list) -> int:
    level = 0
    for edu in education:
        el = edu.lower()
        for deg, lvl in DEGREE_LEVELS.items():
            if deg in el:
                level = max(level, lvl)
    return level


def extract_experience_years(text: str) -> int:
    tl = text.lower()
    for pat in [
        r"(\d+)\+?\s*years?\s+(?:of\s+)?(?:work\s+)?experience",
        r"experience\s+of\s+(\d+)\+?\s*years?",
        r"(\d+)\+?\s*years?\s+(?:working|in\s+industry|in\s+data|in\s+software)",
        r"over\s+(\d+)\s*years?",
        r"more\s+than\s+(\d+)\s*years?",
        r"(\d+)\s*years?\s+of\s+(?:professional|industry|relevant)",
    ]:
        m = re.search(pat, tl)
        if m:
            return min(int(m.group(1)), 30)
    titles = re.findall(
        r"\b(engineer|developer|scientist|analyst|architect|lead|manager|intern|researcher)\b", tl
    )
    return max(0, len(titles) - 1)


def extract_all(text: str) -> dict:
    skills = extract_skills(text)
    flat   = [s for cat in skills.values() for s in cat]
    edu    = extract_education(text)
    return {
        "name":             extract_name(text),
        "contact":          extract_contact(text),
        "skills":           skills,
        "all_skills_flat":  flat,
        "total_skills":     len(flat),
        "education":        edu,
        "highest_degree":   get_highest_degree(edu),
        "experience_years": extract_experience_years(text),
    }


def extract_jd_required_skills(jd_text: str) -> list:
    """Extract skills that the JD explicitly requires — used for gap analysis."""
    tl = jd_text.lower()
    required = []
    for skill in _ALL_SKILLS_FLAT:
        if re.search(r"\b" + re.escape(skill) + r"\b", tl):
            required.append(_display(skill))
    return required


def compute_gap_analysis(resume_info: dict, jd_text: str) -> dict:
    """
    Unique Feature 1: Gap Analysis
    Shows exactly which required skills the candidate has vs is missing.
    """
    required = extract_jd_required_skills(jd_text)
    candidate_skills_lower = {s.lower() for s in resume_info.get("all_skills_flat", [])}
    matched  = [s for s in required if s.lower() in candidate_skills_lower]
    missing  = [s for s in required if s.lower() not in candidate_skills_lower]
    match_pct = round(len(matched)/len(required)*100, 1) if required else 0.0
    return {
        "required_skills": required,
        "matched_skills":  matched,
        "missing_skills":  missing,
        "match_percentage": match_pct,
        "total_required":  len(required),
        "total_matched":   len(matched),
        "total_missing":   len(missing),
    }


def extract_matched_keywords(resume_text: str, jd_text: str) -> list:
    """
    Unique Feature 4: Keyword Highlighting
    Returns JD keywords found in the resume (for frontend highlighting).
    Uses spaCy tokenization to get meaningful content words from JD.
    """
    doc = nlp(jd_text.lower())
    stop_words = {"the","a","an","in","of","and","or","for","to","with","at",
                  "by","from","is","are","was","were","be","have","has","will",
                  "can","should","must","we","our","you","your","i","me","they"}
    jd_keywords = {
        token.text for token in doc
        if token.text.isalpha() and len(token.text) > 3
        and token.text not in stop_words
    }
    resume_lower = resume_text.lower()
    return sorted([kw for kw in jd_keywords if kw in resume_lower])


# ── Scoring Engine ─────────────────────────────────────────────────────────────

def compute_tfidf_similarity(resume_text: str, jd_text: str, all_texts: list) -> float:
    corpus = list(dict.fromkeys(all_texts + [jd_text]))
    if resume_text not in corpus:
        corpus.append(resume_text)
    try:
        vec   = TfidfVectorizer(ngram_range=(1,2), max_features=8000,
                                stop_words="english", sublinear_tf=True, min_df=1)
        tfidf = vec.fit_transform(corpus)
        ji    = corpus.index(jd_text)
        ri    = corpus.index(resume_text)
        return float(cosine_similarity(tfidf[ri], tfidf[ji])[0][0])
    except Exception:
        return 0.0


def skill_overlap_score(info: dict, jd_text: str) -> float:
    jl = jd_text.lower()
    resume_skills = [s.lower() for s in info.get("all_skills_flat", [])]
    matched = sum(1 for s in resume_skills if re.search(r"\b"+re.escape(s)+r"\b", jl))
    jd_skill_count = max(1, sum(1 for s in _ALL_SKILLS_FLAT
                                if re.search(r"\b"+re.escape(s)+r"\b", jl)))
    return min(matched / jd_skill_count, 1.0)


def experience_fit_score(info: dict, jd_text: str) -> float:
    years = info.get("experience_years", 0)
    m = re.search(r"(\d+)\+?\s*years?", jd_text.lower())
    required = int(m.group(1)) if m else 1
    if years >= required: return 1.0
    if years == 0:        return 0.1
    return (years / max(required, 1)) ** 0.7


def education_fit_score(info: dict, jd_text: str) -> float:
    degree = info.get("highest_degree", 0)
    jl = jd_text.lower()
    required = 1
    if any(k in jl for k in ["phd","doctorate"]): required = 4
    elif any(k in jl for k in ["master","m.tech","m.s.","postgraduate"]): required = 3
    elif any(k in jl for k in ["bachelor","b.tech","undergraduate"]): required = 2
    if degree >= required: return 1.0
    if degree == 0:        return 0.2
    return degree / required


def compute_final_score(resume_text: str, jd_text: str, all_resume_texts: list) -> dict:
    info      = extract_all(resume_text)
    tfidf_sim = compute_tfidf_similarity(resume_text, jd_text, all_resume_texts)
    skill_sim = skill_overlap_score(info, jd_text)
    exp_sim   = experience_fit_score(info, jd_text)
    edu_sim   = education_fit_score(info, jd_text)
    final = (tfidf_sim*0.40 + skill_sim*0.35 + exp_sim*0.15 + edu_sim*0.10) * 100
    gap   = compute_gap_analysis(info, jd_text)
    kw    = extract_matched_keywords(resume_text, jd_text)
    return {
        **info,
        "score": round(final, 2),
        "score_breakdown": {
            "tfidf_similarity": round(tfidf_sim*100, 2),
            "skill_match":      round(skill_sim*100, 2),
            "experience_fit":   round(exp_sim  *100, 2),
            "education_fit":    round(edu_sim  *100, 2),
        },
        "gap_analysis":       gap,
        "matched_keywords":   kw[:30],
    }


def rank_resumes(resume_texts: list, filenames: list, jd_text: str) -> list:
    results = []
    for text, fname in zip(resume_texts, filenames):
        scored = compute_final_score(text, jd_text, resume_texts)
        scored["filename"] = fname
        results.append(scored)
    results.sort(key=lambda x: x["score"], reverse=True)
    for i, r in enumerate(results):
        r["rank"] = i + 1
        s = r["score"]
        r["verdict"] = ("Strong Match" if s>=75 else "Good Match" if s>=55
                        else "Partial Match" if s>=35 else "Weak Match")
    return results
