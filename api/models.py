from django.db import models

# inspectdb로 자동 생성된 모델을 Django 관례에 맞게 수정한 최종 버전입니다.

class Company(models.Model):
    # Django는 관례적으로 클래스 이름을 단수형(Company)으로 사용합니다.
    # id 필드는 Django가 자동으로 생성하므로, 명시적으로 정의할 필요가 없습니다.
    name = models.CharField(unique=True, max_length=255, verbose_name="회사명")
    homepage_url = models.URLField(max_length=2083, blank=True, null=True, verbose_name="홈페이지 URL")
    recruits_url = models.URLField(max_length=2083, blank=True, null=True, verbose_name="채용 페이지 URL")
    recruits_url_status = models.CharField(max_length=20, blank=True, null=True, verbose_name="채용 URL 상태")
    recruits_url_score = models.IntegerField(blank=True, null=True, verbose_name="채용 URL 신뢰도 점수")
    logo_url = models.URLField(max_length=2083, blank=True, null=True, verbose_name="회사 로고 URL")
    industry = models.CharField(max_length=100, blank=True, null=True, verbose_name="산업 분야")
    address = models.CharField(max_length=255, blank=True, null=True, verbose_name="회사 주소")
    # auto_now_add=True: 객체가 처음 생성될 때만 현재 시간 저장
    # auto_now=True: 객체가 저장될 때마다 현재 시간으로 업데이트
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="생성일")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="수정일")

    def __str__(self):
        # 관리자 페이지 등에서 객체를 문자열로 표현할 때 사용됩니다.
        return self.name

    class Meta:
        # managed = False 라인을 반드시 제거하거나 True로 변경해야 Django가 이 테이블을 관리할 수 있습니다.
        db_table = 'companies' # 실제 DB 테이블 이름을 명시적으로 지정
        verbose_name = "회사"
        verbose_name_plural = "회사 목록"


class JobPosting(models.Model):
    # 클래스 이름을 단수형(JobPosting)으로 변경
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='job_postings', verbose_name="회사")
    title = models.CharField(max_length=255, verbose_name="공고 제목")
    post_url = models.URLField(unique=True, max_length=2083, verbose_name="공고 URL")
    job_description = models.TextField(blank=True, null=True, verbose_name="주요 업무")
    qualifications = models.TextField(blank=True, null=True, verbose_name="자격 요건")
    preferred_qualifications = models.TextField(blank=True, null=True, verbose_name="우대 사항")
    hiring_process = models.TextField(blank=True, null=True, verbose_name="채용 절차")
    benefits = models.TextField(blank=True, null=True, verbose_name="혜택 및 복지")
    hiring_message = models.TextField(blank=True, null=True, verbose_name='채용 메시지')
    location = models.CharField(max_length=255, blank=True, null=True, verbose_name="근무지")
    employment_type = models.CharField(max_length=50, blank=True, null=True, verbose_name="고용 형태")
    salary = models.CharField(max_length=255, blank=True, null=True, verbose_name="급여")
    work_hours = models.CharField(max_length=100, blank=True, null=True, verbose_name='근무 시간')
    posted_at = models.DateField(blank=True, null=True, verbose_name="게시일")
    deadline_at = models.DateField(blank=True, null=True, verbose_name="마감일")
    status = models.CharField(max_length=20, verbose_name="공고 상태")
    crawled_at = models.DateTimeField(auto_now=True, verbose_name="수집일")


    def __str__(self):
        return f"[{self.company.name}] {self.title}"

    class Meta:
        # managed = False 라인 제거
        db_table = 'job_postings'
        verbose_name = "채용 공고"
        verbose_name_plural = "채용 공고 목록"

