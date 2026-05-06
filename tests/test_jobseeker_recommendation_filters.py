import json
from datetime import date, timedelta

from django.test import Client, TestCase, override_settings

from api.models import Company, JobPosting


@override_settings(API_INTERNAL_TOKEN="test-internal-token")
class JobseekerRecommendationActiveFilterTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.company = Company.objects.create(name="Filter Test Co")

        today = date.today()
        self.future_job = JobPosting.objects.create(
            company=self.company,
            title="Backend Engineer Future",
            post_url="https://example.com/jobs/future",
            job_description="python django backend",
            qualifications="python",
            preferred_qualifications="django",
            status="open",
            is_active=True,
            deadline_at=today + timedelta(days=7),
        )
        self.past_job = JobPosting.objects.create(
            company=self.company,
            title="Backend Engineer Past",
            post_url="https://example.com/jobs/past",
            job_description="python django backend",
            qualifications="python",
            preferred_qualifications="django",
            status="open",
            is_active=True,
            deadline_at=today - timedelta(days=1),
        )
        self.null_deadline_job = JobPosting.objects.create(
            company=self.company,
            title="Backend Engineer No Deadline",
            post_url="https://example.com/jobs/no-deadline",
            job_description="python django backend",
            qualifications="python",
            preferred_qualifications="django",
            status="open",
            is_active=True,
            deadline_at=None,
        )
        self.inactive_job = JobPosting.objects.create(
            company=self.company,
            title="Backend Engineer Inactive",
            post_url="https://example.com/jobs/inactive",
            job_description="python django backend",
            qualifications="python",
            preferred_qualifications="django",
            status="closed",
            is_active=False,
            deadline_at=today + timedelta(days=10),
        )

    def test_jobs_endpoint_applies_recommendation_filter_when_requested(self):
        resp = self.client.get("/api/jobs", {"jobseeker_recommendation_active": "1", "page_size": 100})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        returned_ids = {item["id"] for item in body["results"]}

        self.assertIn(self.future_job.id, returned_ids)
        self.assertIn(self.null_deadline_job.id, returned_ids)
        self.assertNotIn(self.past_job.id, returned_ids)
        self.assertNotIn(self.inactive_job.id, returned_ids)

    def test_jobs_endpoint_active_1_defaults_to_recommendation_filter(self):
        resp = self.client.get("/api/jobs", {"active": "1", "page_size": 100})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        returned_ids = {item["id"] for item in body["results"]}

        self.assertIn(self.future_job.id, returned_ids)
        self.assertIn(self.null_deadline_job.id, returned_ids)
        self.assertNotIn(self.past_job.id, returned_ids)

    def test_matching_student_top_excludes_expired_jobs(self):
        payload = {
            "student": {
                "기술스택": ["python", "django"],
                "구인구분": "신입+경력",
                "근무지": "지역 무관",
                "복리후생": [],
                "필수조건": [],
            },
            "limit": 10,
        }
        resp = self.client.post(
            "/api/match/student-top",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_INTERNAL_TOKEN="test-internal-token",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        returned_ids = {item["job_id"] for item in body["results"]}

        self.assertIn(self.future_job.id, returned_ids)
        self.assertIn(self.null_deadline_job.id, returned_ids)
        self.assertNotIn(self.past_job.id, returned_ids)

    def test_matching_batch_excludes_expired_jobs(self):
        payload = {
            "students": [
                {
                    "name": "stu1",
                    "기술스택": ["python", "django"],
                    "구인구분": "신입+경력",
                    "근무지": "지역 무관",
                    "복리후생": [],
                    "필수조건": [],
                }
            ],
            "topk": 10,
        }
        resp = self.client.post(
            "/api/match/batch",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_INTERNAL_TOKEN="test-internal-token",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        student_top = body["student_top"]
        self.assertEqual(len(student_top), 1)

        returned_ids = {item["job_id"] for item in student_top[0]["top"]}
        self.assertIn(self.future_job.id, returned_ids)
        self.assertIn(self.null_deadline_job.id, returned_ids)
        self.assertNotIn(self.past_job.id, returned_ids)
