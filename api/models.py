from django.db import models

# inspectdb로 자동 생성된 모델을 Django 관례에 맞게 수정한 최종 버전입니다.

class Company(models.Model):
    # Django는 관례적으로 클래스 이름을 단수형(Company)으로 사용합니다.
    # id 필드는 Django가 자동으로 생성하므로, 명시적으로 정의할 필요가 없습니다.

    PAGE_TYPE_CHOICES = [
        ("listing", "Listing (board-style jobs page)"),
        ("one_page", "One-page jobs section"),
        ("main", "Main page has jobs"),
        ("external", "External job site"),
    ]
    POST_TYPE_CHOICES = [
        ("text", "Text-based postings"),
        ("image", "Image-based postings"),
        ("external_link", "Links to external job site"),
    ]

    name = models.CharField(unique=True, max_length=255, verbose_name="회사명")
    homepage_url = models.URLField(max_length=2083, blank=True, null=True, verbose_name="홈페이지 URL")
    recruits_url = models.URLField(max_length=2083, blank=True, null=True, verbose_name="채용 페이지 URL")
    page_type = models.CharField(
        max_length=20,
        choices=PAGE_TYPE_CHOICES,
        blank=True,
        null=True,
        help_text="채용페이지 타입",
    )
    post_type = models.CharField(
        max_length=20,
        choices=POST_TYPE_CHOICES,
        blank=True,
        null=True,
        help_text="채용포스트 분류",
    )
    hiring = models.BooleanField(
        default=False,
        help_text="채용진행 여부",
    )
    recruits_url_status = models.CharField(max_length=20, blank=True, null=True, verbose_name="채용 URL 상태")
    recruits_url_score = models.IntegerField(blank=True, null=True, verbose_name="채용 URL 신뢰도 점수")
    logo_url = models.URLField(max_length=2083, blank=True, null=True, verbose_name="회사 로고 URL")
    industry = models.CharField(max_length=100, blank=True, null=True, verbose_name="산업 분야")
    address = models.CharField(max_length=255, blank=True, null=True, verbose_name="회사 주소")
    region = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="회사 지역",
    )
    external_job_site = models.URLField(
        blank=True,
        null=True,
        help_text="외부채용사이트 주소",
    )
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


class Trainee(models.Model):
    GENDER_CHOICES = [
        ("M", "남"),
        ("F", "여"),
        ("O", "기타"),
    ]

    # 기본 인적 사항
    counseling_date = models.DateField(verbose_name="날짜")
    student_code = models.CharField(max_length=50, verbose_name="학생ID")
    name_alias = models.CharField(max_length=50, verbose_name="이름(가명)")
    birth_date = models.DateField(verbose_name="생년월일", null=True, blank=True)
    gender = models.CharField(
        max_length=1,
        choices=GENDER_CHOICES,
        verbose_name="성별",
        blank=True,
    )
    education_level = models.CharField(
        max_length=100,
        verbose_name="학력",
        blank=True,
    )
    major = models.CharField(
        max_length=100,
        verbose_name="전공",
        blank=True,
    )

    # 학원 성적 / 경력
    academy_rank = models.IntegerField(
        verbose_name="학원 성적(등수)",
        null=True,
        blank=True,
    )
    career_summary = models.TextField(
        verbose_name="경력",
        blank=True,
    )
    career_months = models.PositiveIntegerField(
        verbose_name="경력기간(M)",
        null=True,
        blank=True,
    )

    # 과정 및 상담 정보
    course_name = models.CharField(
        max_length=200,
        verbose_name="과정명",
        blank=True,
    )
    counseling_summary = models.TextField(
        verbose_name="상담내용 요약",
        blank=True,
    )
    counselor_name = models.CharField(
        max_length=50,
        verbose_name="상담교사",
        blank=True,
    )
    note = models.TextField(
        verbose_name="비고(위험/특이사항)",
        blank=True,
    )

    # === 학생의 희망 조건 (매칭용 핵심) ===

    # 희망 근무 인원(회사 규모)
    preferred_company_size = models.PositiveIntegerField(
        verbose_name="근무인원",
        null=True,
        blank=True,
        help_text="학생이 희망하는 최소 근무 인원(예: 5, 10, 20, 50 등)",
    )

    # 희망 업종
    preferred_industry = models.CharField(
        max_length=100,
        verbose_name="업종분류",
        blank=True,
    )

    # 희망 구인 구분 (신입/경력 등)
    preferred_employment_type = models.CharField(
        max_length=50,
        verbose_name="구인구분(신입,경력)",
        blank=True,
    )

    # 희망 직무/기술 방향
    preferred_job_skill = models.CharField(
        max_length=255,
        verbose_name="구인기술",
        blank=True,
    )

    # 희망 근무지
    preferred_location = models.CharField(
        max_length=100,
        verbose_name="근무지",
        blank=True,
    )

    # 희망 급여 수준 (문자열로 저장, 나중에 파싱 가능)
    preferred_salary = models.CharField(
        max_length=100,
        verbose_name="급여",
        blank=True,
    )

    # 보유 기술 스택
    tech_stack = models.CharField(
        max_length=255,
        verbose_name="기술스택",
        blank=True,
    )

    # 희망 복리후생: 정해진 키워드만 콤마 구분 저장
    welfare_preferences = models.CharField(
        max_length=255,
        verbose_name="복리후생",
        blank=True,
        help_text="식대, 재택근무, 건강검진, 교육비, 사내스터디, 컨퍼런스참가비, 운동비, 도서구입비, 경조사비, 경조휴가, 스톡옵션, 자율출퇴근제 중 선택",
    )

    # 필수조건: 학생이 '이 조건 안 지키면 지원 안함'으로 체크한 항목들
    # (예: 근무인원>=50, 특정 복리후생 포함, 지역 제한 등)
    required_conditions = models.CharField(
        max_length=500,
        verbose_name="필수조건",
        blank=True,
        help_text="사전에 정의된 조건 키만 콤마로 저장 (예: COMPANY_SIZE_10UP,BENEFIT_재택근무 등)",
    )

    class Meta:
        verbose_name = "훈련생"
        verbose_name_plural = "훈련생"

    def __str__(self):
        return f"{self.student_code} / {self.name_alias}"
