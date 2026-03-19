"""
tests/test_api.py — Full test suite with authentication
32 tests covering auth, jobs, resumes, NLP, analytics
"""
import sys, os, gc, time, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
os.environ["DATABASE_URL"] = "sqlite:///./test_screener.db"

from fastapi.testclient import TestClient

from main import app

# ── Fixtures ───────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture(scope="module")
def auth_headers(client):
    """Register a test user and return auth headers."""
    client.post("/api/auth/register", json={
        "name": "Test User", "email": "test@screener.com", "password": "testpass123"
    })
    r = client.post("/api/auth/login", json={
        "email": "test@screener.com", "password": "testpass123"
    })
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture(scope="module")
def job(client, auth_headers):
    r = client.post("/api/jobs", json={
        "title": "Data Engineer", "company": "TestCorp",
        "description": "Python, SQL, Apache Spark, ETL, AWS S3, Airflow, PostgreSQL, Docker, Git. Bachelor or Master in CS. 1+ years experience.",
        "min_experience": 1
    }, headers=auth_headers)
    assert r.status_code == 200
    return r.json()

@pytest.fixture(scope="module")
def uploaded(client, auth_headers, job):
    resume = (
        "Arjun Mehta\narjun@test.com | github.com/arjun | linkedin.com/in/arjun\n"
        "Master of Technology Computer Science IIT Bombay 2024\n"
        "Data Engineer Infosys 2022-2024 - 2 years experience\n"
        "Python, SQL, Apache Spark, PySpark, Airflow, AWS S3, PostgreSQL, Docker, Git, ETL\n"
    ).encode("utf-8")
    r = client.post(f"/api/jobs/{job['id']}/upload",
        files=[("files", ("arjun.txt", resume, "text/plain"))],
        headers=auth_headers)
    assert r.status_code == 200
    return r.json()


# ── Auth Tests ─────────────────────────────────────────────────────────────────
class TestAuth:
    def test_register_success(self, client):
        r = client.post("/api/auth/register", json={
            "name": "New User", "email": "new@test.com", "password": "pass123"
        })
        assert r.status_code == 200
        assert "access_token" in r.json()
        assert r.json()["user"]["email"] == "new@test.com"

    def test_register_duplicate_email(self, client):
        client.post("/api/auth/register", json={"name":"A","email":"dup@test.com","password":"p"})
        r = client.post("/api/auth/register", json={"name":"B","email":"dup@test.com","password":"p"})
        assert r.status_code == 400

    def test_login_success(self, client, auth_headers):
        r = client.post("/api/auth/login", json={"email":"test@screener.com","password":"testpass123"})
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_login_wrong_password(self, client):
        r = client.post("/api/auth/login", json={"email":"test@screener.com","password":"wrong"})
        assert r.status_code == 401

    def test_me_endpoint(self, client, auth_headers):
        r = client.get("/api/auth/me", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["email"] == "test@screener.com"

    def test_unauthenticated_jobs_rejected(self, client):
        r = client.get("/api/jobs")
        assert r.status_code == 401

    def test_invalid_token_rejected(self, client):
        r = client.get("/api/jobs", headers={"Authorization": "Bearer badtoken"})
        assert r.status_code == 401


# ── Health ─────────────────────────────────────────────────────────────────────
class TestHealth:
    def test_health_ok(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["version"] == "2.0.0"


# ── Jobs ───────────────────────────────────────────────────────────────────────
class TestJobs:
    def test_create_job(self, job):
        assert job["id"] > 0
        assert job["title"] == "Data Engineer"
        assert job["is_active"] is True

    def test_list_jobs(self, client, auth_headers, job):
        r = client.get("/api/jobs", headers=auth_headers)
        assert r.status_code == 200
        assert any(j["id"] == job["id"] for j in r.json())

    def test_jobs_are_user_scoped(self, client, job):
        """User 2 should NOT see User 1's jobs."""
        client.post("/api/auth/register", json={"name":"User2","email":"user2@test.com","password":"pass"})
        r2 = client.post("/api/auth/login", json={"email":"user2@test.com","password":"pass"})
        headers2 = {"Authorization": f"Bearer {r2.json()['access_token']}"}
        jobs2 = client.get("/api/jobs", headers=headers2).json()
        assert not any(j["id"] == job["id"] for j in jobs2)

    def test_create_job_missing_title(self, client, auth_headers):
        r = client.post("/api/jobs", json={"description":"test"}, headers=auth_headers)
        assert r.status_code == 422

    def test_create_job_missing_description(self, client, auth_headers):
        r = client.post("/api/jobs", json={"title":"test"}, headers=auth_headers)
        assert r.status_code == 422


# ── Upload ─────────────────────────────────────────────────────────────────────
class TestUpload:
    def test_upload_success(self, uploaded):
        assert uploaded["total"] >= 1
        assert uploaded["new"] >= 1

    def test_upload_nonexistent_job(self, client, auth_headers):
        r = client.post("/api/jobs/99999/upload",
            files=[("files", ("t.txt", b"hello", "text/plain"))],
            headers=auth_headers)
        assert r.status_code == 404

    def test_upload_empty_content(self, client, auth_headers, job):
        r = client.post(f"/api/jobs/{job['id']}/upload",
            files=[("files", ("e.txt", b"   ", "text/plain"))],
            headers=auth_headers)
        assert r.status_code == 400

    def test_cannot_upload_to_other_users_job(self, client, job):
        client.post("/api/auth/register", json={"name":"X","email":"x@test.com","password":"pass"})
        rx = client.post("/api/auth/login", json={"email":"x@test.com","password":"pass"})
        hx = {"Authorization": f"Bearer {rx.json()['access_token']}"}
        r = client.post(f"/api/jobs/{job['id']}/upload",
            files=[("files", ("t.txt", b"Python SQL", "text/plain"))], headers=hx)
        assert r.status_code == 404


# ── Rankings ───────────────────────────────────────────────────────────────────
class TestRankings:
    def test_get_resumes_returns_list(self, client, auth_headers, job, uploaded):
        r = client.get(f"/api/jobs/{job['id']}/resumes", headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_resume_has_required_fields(self, client, auth_headers, job, uploaded):
        r = client.get(f"/api/jobs/{job['id']}/resumes", headers=auth_headers)
        res = r.json()[0]
        for field in ["id","rank","candidate_name","score","verdict","skills",
                      "education","experience_years","score_breakdown","gap_analysis"]:
            assert field in res, f"Missing field: {field}"

    def test_score_in_range(self, client, auth_headers, job, uploaded):
        r = client.get(f"/api/jobs/{job['id']}/resumes", headers=auth_headers)
        for res in r.json():
            assert 0 <= res["score"] <= 100

    def test_score_breakdown_correct(self, client, auth_headers, job, uploaded):
        r = client.get(f"/api/jobs/{job['id']}/resumes", headers=auth_headers)
        for res in r.json():
            bd = res["score_breakdown"]
            reconstructed = (bd["tfidf_similarity"]*0.40 + bd["skill_match"]*0.35 +
                             bd["experience_fit"]*0.15 + bd["education_fit"]*0.10)
            assert abs(reconstructed - res["score"]) < 1.0

    def test_verdicts_valid(self, client, auth_headers, job, uploaded):
        r = client.get(f"/api/jobs/{job['id']}/resumes", headers=auth_headers)
        valid = {"Strong Match","Good Match","Partial Match","Weak Match"}
        for res in r.json():
            assert res["verdict"] in valid

    def test_ranks_sequential(self, client, auth_headers, job, uploaded):
        r = client.get(f"/api/jobs/{job['id']}/resumes", headers=auth_headers)
        ranks = [res["rank"] for res in r.json()]
        assert ranks == list(range(1, len(ranks)+1))

    def test_sorted_by_score_desc(self, client, auth_headers, job, uploaded):
        r = client.get(f"/api/jobs/{job['id']}/resumes", headers=auth_headers)
        scores = [res["score"] for res in r.json()]
        assert scores == sorted(scores, reverse=True)

    def test_gap_analysis_present(self, client, auth_headers, job, uploaded):
        r = client.get(f"/api/jobs/{job['id']}/resumes", headers=auth_headers)
        for res in r.json():
            gap = res.get("gap_analysis", {})
            assert "matched_skills" in gap
            assert "missing_skills" in gap

    def test_delete_rerranks(self, client, auth_headers, job):
        r1 = b"Alice Smith alice@t.com Python SQL Docker PostgreSQL AWS 3 years experience Master CS"
        r2 = b"Bob Jones bob@t.com JavaScript React 1 year experience Bachelor"
        client.post(f"/api/jobs/{job['id']}/upload",
            files=[("files",("a.txt",r1,"text/plain")),("files",("b.txt",r2,"text/plain"))],
            headers=auth_headers)
        resumes = client.get(f"/api/jobs/{job['id']}/resumes", headers=auth_headers).json()
        last_id = resumes[-1]["id"]
        client.delete(f"/api/jobs/{job['id']}/resumes/{last_id}", headers=auth_headers)
        after = client.get(f"/api/jobs/{job['id']}/resumes", headers=auth_headers).json()
        assert len(after) == len(resumes) - 1
        assert [r["rank"] for r in after] == list(range(1, len(after)+1))


# ── Analytics ──────────────────────────────────────────────────────────────────
class TestAnalytics:
    def test_overview_structure(self, client, auth_headers, uploaded):
        r = client.get("/api/analytics/overview", headers=auth_headers)
        assert r.status_code == 200
        for key in ["total_jobs","total_resumes","total_sessions","avg_score_across_all","recent_activity"]:
            assert key in r.json()

    def test_skills_list(self, client, auth_headers, uploaded):
        r = client.get("/api/analytics/skills", headers=auth_headers)
        assert r.status_code == 200
        skills = r.json()["top_skills"]
        if skills:
            assert "skill" in skills[0] and "count" in skills[0]

    def test_score_distribution(self, client, auth_headers, uploaded):
        r = client.get("/api/analytics/score-distribution", headers=auth_headers)
        assert r.status_code == 200
        dist = r.json()["distribution"]
        assert set(dist.keys()) == {"0-20","21-40","41-60","61-80","81-100"}


# ── Storage & Taxonomy ─────────────────────────────────────────────────────────
class TestStorage:
    def test_storage_status(self, client, auth_headers):
        r = client.get("/api/storage/status", headers=auth_headers)
        assert r.status_code == 200
        assert "s3_configured" in r.json()

    def test_skill_taxonomy(self, client):
        r = client.get("/api/skill-taxonomy")
        assert r.status_code == 200
        assert "Programming Languages" in r.json()
        assert len(r.json()["Programming Languages"]) > 5


# ── NLP Unit Tests ─────────────────────────────────────────────────────────────
class TestNLPEngine:
    def test_extract_name(self):
        from nlp_engine import extract_name
        assert extract_name("Arjun Mehta\narjun@gmail.com\nEngineer") == "Arjun Mehta"

    def test_extract_email(self):
        from nlp_engine import extract_contact
        assert extract_contact("John\njohn@example.com")["email"] == "john@example.com"

    def test_extract_github(self):
        from nlp_engine import extract_contact
        assert "johndoe" in extract_contact("github.com/johndoe")["github"]

    def test_extract_skills_python(self):
        from nlp_engine import extract_skills
        skills = extract_skills("Python, TensorFlow, PostgreSQL, Docker, AWS S3")
        flat = [s.lower() for cat in skills.values() for s in cat]
        assert "python" in flat
        assert "tensorflow" in flat

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
        score = compute_tfidf_similarity(
            "Python machine learning scikit-learn pandas",
            "Python data science scikit-learn pandas",
            ["Python machine learning", "Python data science"]
        )
        assert 0.0 <= score <= 1.0

    def test_higher_match_scores_higher(self):
        from nlp_engine import rank_resumes
        perfect = "Python SQL Apache Spark ETL AWS S3 Airflow PostgreSQL Docker 3 years experience Master CS"
        weak    = "JavaScript React HTML CSS 1 year experience"
        ranked  = rank_resumes([perfect, weak], ["perfect.txt","weak.txt"],
                               "Python SQL Spark ETL AWS S3 PostgreSQL Docker 2+ years Master CS")
        assert ranked[0]["filename"] == "perfect.txt"
        assert ranked[0]["score"] > ranked[1]["score"]


# ── Cleanup ────────────────────────────────────────────────────────────────────
def teardown_module(module):
    try:
        import database; database.engine.dispose()
    except Exception:
        pass
    gc.collect()
    for _ in range(5):
        try:
            if os.path.exists("test_screener.db"):
                os.remove("test_screener.db")
            break
        except PermissionError:
            time.sleep(0.3)