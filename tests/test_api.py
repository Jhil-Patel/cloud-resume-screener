"""
tests/test_api.py — Automated test suite for Cloud Resume Screener API
Run with: pytest tests/ -v
"""
import sys, os, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from fastapi.testclient import TestClient

# Use in-memory SQLite for tests
os.environ["DATABASE_URL"] = "sqlite:///./test_screener.db"

from main import app

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture(scope="module")
def job(client):
    r = client.post("/api/jobs", json={
        "title": "Data Engineer",
        "company": "TestCorp",
        "description": (
            "Python, SQL, Apache Spark, ETL pipelines, AWS S3, Airflow, "
            "PostgreSQL, Docker, Git. Bachelor or Master in CS. 1+ years experience."
        ),
        "min_experience": 1
    })
    assert r.status_code == 200
    return r.json()

@pytest.fixture(scope="module")
def uploaded(client, job):
    resume_text = (
        "Arjun Mehta\n"
        "arjun@test.com | github.com/arjun | linkedin.com/in/arjun\n"
        "Master of Technology Computer Science IIT Bombay 2024\n"
        "Data Engineer Infosys 2022-2024 - 2 years experience\n"
        "Python, SQL, Apache Spark, PySpark, Airflow, AWS S3, PostgreSQL, Docker, Git, ETL, Kafka\n"
    ).encode("utf-8")
    r = client.post(
        f"/api/jobs/{job['id']}/upload",
        files=[("files", ("arjun.txt", resume_text, "text/plain"))]
    )
    assert r.status_code == 200
    return r.json()


# ── Health ─────────────────────────────────────────────────────────────────
class TestHealth:
    def test_health_ok(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["version"] == "2.0.0"
        assert "timestamp" in data


# ── Jobs CRUD ──────────────────────────────────────────────────────────────
class TestJobs:
    def test_create_job(self, job):
        assert job["id"] > 0
        assert job["title"] == "Data Engineer"
        assert job["company"] == "TestCorp"
        assert job["is_active"] is True

    def test_list_jobs(self, client, job):
        r = client.get("/api/jobs")
        assert r.status_code == 200
        jobs = r.json()
        assert isinstance(jobs, list)
        assert any(j["id"] == job["id"] for j in jobs)

    def test_job_has_resume_count(self, client, job):
        r = client.get("/api/jobs")
        j = next(x for x in r.json() if x["id"] == job["id"])
        assert "resume_count" in j

    def test_create_job_missing_title(self, client):
        r = client.post("/api/jobs", json={"description": "test"})
        assert r.status_code == 422  # Validation error

    def test_create_job_missing_description(self, client):
        r = client.post("/api/jobs", json={"title": "test"})
        assert r.status_code == 422


# ── Upload & NLP ───────────────────────────────────────────────────────────
class TestUpload:
    def test_upload_success(self, uploaded):
        assert uploaded["total"] >= 1
        assert uploaded["new"] >= 1

    def test_upload_nonexistent_job(self, client):
        r = client.post(
            "/api/jobs/99999/upload",
            files=[("files", ("test.txt", b"hello", "text/plain"))]
        )
        assert r.status_code == 404

    def test_upload_empty_content(self, client, job):
        r = client.post(
            f"/api/jobs/{job['id']}/upload",
            files=[("files", ("empty.txt", b"   \n   ", "text/plain"))]
        )
        assert r.status_code == 400


# ── Rankings ───────────────────────────────────────────────────────────────
class TestRankings:
    def test_get_resumes_returns_list(self, client, job, uploaded):
        r = client.get(f"/api/jobs/{job['id']}/resumes")
        assert r.status_code == 200
        resumes = r.json()
        assert isinstance(resumes, list)
        assert len(resumes) >= 1

    def test_resume_has_required_fields(self, client, job, uploaded):
        r = client.get(f"/api/jobs/{job['id']}/resumes")
        res = r.json()[0]
        for field in ["id", "rank", "candidate_name", "score", "verdict",
                      "skills", "education", "experience_years", "score_breakdown"]:
            assert field in res, f"Missing field: {field}"

    def test_score_in_range(self, client, job, uploaded):
        r = client.get(f"/api/jobs/{job['id']}/resumes")
        for res in r.json():
            assert 0 <= res["score"] <= 100

    def test_score_breakdown_sums_to_approx_score(self, client, job, uploaded):
        r = client.get(f"/api/jobs/{job['id']}/resumes")
        for res in r.json():
            bd = res["score_breakdown"]
            reconstructed = (
                bd["tfidf_similarity"] * 0.40 +
                bd["skill_match"]      * 0.35 +
                bd["experience_fit"]   * 0.15 +
                bd["education_fit"]    * 0.10
            )
            assert abs(reconstructed - res["score"]) < 1.0, \
                f"Score breakdown mismatch: {reconstructed} vs {res['score']}"

    def test_verdicts_are_valid(self, client, job, uploaded):
        r = client.get(f"/api/jobs/{job['id']}/resumes")
        valid = {"Strong Match", "Good Match", "Partial Match", "Weak Match"}
        for res in r.json():
            assert res["verdict"] in valid

    def test_ranks_are_sequential(self, client, job, uploaded):
        r = client.get(f"/api/jobs/{job['id']}/resumes")
        ranks = [res["rank"] for res in r.json()]
        assert ranks == list(range(1, len(ranks) + 1))

    def test_results_sorted_by_score_desc(self, client, job, uploaded):
        r = client.get(f"/api/jobs/{job['id']}/resumes")
        scores = [res["score"] for res in r.json()]
        assert scores == sorted(scores, reverse=True)

    def test_nonexistent_job_resumes(self, client):
        r = client.get("/api/jobs/99999/resumes")
        assert r.status_code == 200
        assert r.json() == []

    def test_delete_resume_rerranks(self, client, job):
        # Upload two resumes
        r1 = b"Alice Smith alice@test.com Python SQL Docker PostgreSQL AWS 3 years experience Master Computer Science"
        r2 = b"Bob Jones bob@test.com JavaScript React Node.js 1 year experience Bachelor Engineering"
        client.post(f"/api/jobs/{job['id']}/upload",
                    files=[("files", ("alice.txt", r1, "text/plain")),
                           ("files", ("bob.txt", r2, "text/plain"))])

        resumes = client.get(f"/api/jobs/{job['id']}/resumes").json()
        last_id = resumes[-1]["id"]

        r = client.delete(f"/api/jobs/{job['id']}/resumes/{last_id}")
        assert r.status_code == 200

        resumes_after = client.get(f"/api/jobs/{job['id']}/resumes").json()
        assert len(resumes_after) == len(resumes) - 1
        ranks_after = [res["rank"] for res in resumes_after]
        assert ranks_after == list(range(1, len(resumes_after) + 1))


# ── Analytics ──────────────────────────────────────────────────────────────
class TestAnalytics:
    def test_overview_structure(self, client, uploaded):
        r = client.get("/api/analytics/overview")
        assert r.status_code == 200
        data = r.json()
        for key in ["total_jobs", "total_resumes", "total_sessions",
                    "avg_score_across_all", "recent_activity"]:
            assert key in data

    def test_overview_counts_positive(self, client, uploaded):
        r = client.get("/api/analytics/overview")
        data = r.json()
        assert data["total_jobs"] >= 1
        assert data["total_resumes"] >= 1

    def test_skills_returns_top_list(self, client, uploaded):
        r = client.get("/api/analytics/skills")
        assert r.status_code == 200
        skills = r.json()["top_skills"]
        assert isinstance(skills, list)
        if skills:
            assert "skill" in skills[0]
            assert "count" in skills[0]

    def test_score_distribution_structure(self, client, uploaded):
        r = client.get("/api/analytics/score-distribution")
        assert r.status_code == 200
        dist = r.json()["distribution"]
        expected_keys = {"0-20", "21-40", "41-60", "61-80", "81-100"}
        assert set(dist.keys()) == expected_keys
        assert all(isinstance(v, int) for v in dist.values())
        assert sum(dist.values()) >= 1


# ── Storage ────────────────────────────────────────────────────────────────
class TestStorage:
    def test_storage_status(self, client):
        r = client.get("/api/storage/status")
        assert r.status_code == 200
        data = r.json()
        assert "s3_configured" in data
        assert "storage_mode" in data
        assert data["s3_configured"] in [True, False]

    def test_skill_taxonomy(self, client):
        r = client.get("/api/skill-taxonomy")
        assert r.status_code == 200
        taxonomy = r.json()
        assert "Programming Languages" in taxonomy
        assert "ML / AI" in taxonomy
        assert "Cloud & DevOps" in taxonomy
        assert len(taxonomy["Programming Languages"]) > 5


# ── NLP Engine Unit Tests ──────────────────────────────────────────────────
class TestNLPEngine:
    def test_extract_name(self):
        from nlp_engine import extract_name
        text = "Arjun Mehta\narjun@gmail.com\nSoftware Engineer"
        assert extract_name(text) == "Arjun Mehta"

    def test_extract_email(self):
        from nlp_engine import extract_contact
        text = "John Doe\njohn.doe@example.com | +91-9876543210"
        contact = extract_contact(text)
        assert contact["email"] == "john.doe@example.com"

    def test_extract_github(self):
        from nlp_engine import extract_contact
        text = "github.com/johndoe | linkedin.com/in/johndoe"
        contact = extract_contact(text)
        assert "johndoe" in contact["github"]

    def test_extract_skills_python(self):
        from nlp_engine import extract_skills
        text = "Experienced in Python, TensorFlow, PostgreSQL, Docker, AWS S3"
        skills = extract_skills(text)
        all_skills = [s.lower() for cat in skills.values() for s in cat]
        assert "python" in all_skills
        assert "tensorflow" in all_skills
        assert "postgresql" in all_skills

    def test_extract_experience_explicit(self):
        from nlp_engine import extract_experience_years
        assert extract_experience_years("5 years of experience in data engineering") == 5
        assert extract_experience_years("3+ years working in ML") == 3

    def test_education_degree_level(self):
        from nlp_engine import get_highest_degree
        assert get_highest_degree(["Master of Technology Computer Science IIT"]) == 3
        assert get_highest_degree(["Bachelor of Engineering NIT"]) == 2
        assert get_highest_degree(["PhD in Computer Science"]) == 4
        assert get_highest_degree([]) == 0

    def test_tfidf_score_range(self):
        from nlp_engine import compute_tfidf_similarity
        resume = "Python machine learning data science scikit-learn pandas numpy"
        jd = "Looking for Python data science experience with scikit-learn and pandas"
        score = compute_tfidf_similarity(resume, jd, [resume, jd])
        assert 0.0 <= score <= 1.0

    def test_higher_match_scores_higher(self):
        from nlp_engine import rank_resumes
        perfect = "Python SQL Apache Spark ETL AWS S3 Airflow PostgreSQL Docker Git 3 years experience Master Computer Science Data Engineering"
        weak = "JavaScript React HTML CSS frontend developer 1 year experience"
        jd = "Python SQL Apache Spark ETL AWS S3 PostgreSQL Docker 2+ years Master CS"
        ranked = rank_resumes([perfect, weak], ["perfect.txt", "weak.txt"], jd)
        assert ranked[0]["filename"] == "perfect.txt"
        assert ranked[0]["score"] > ranked[1]["score"]


# ── Cleanup ────────────────────────────────────────────────────────────────
def teardown_module(module):
    """
    Windows holds an exclusive lock on SQLite files while connections are open.
    Dispose the SQLAlchemy engine to release all pooled connections first,
    then retry deletion a few times (Windows releases locks slightly async).
    """
    try:
        import database
        database.engine.dispose()
    except Exception:
        pass

    import gc, time
    gc.collect()

    for _ in range(5):
        try:
            if os.path.exists("test_screener.db"):
                os.remove("test_screener.db")
            break
        except PermissionError:
            time.sleep(0.3)
