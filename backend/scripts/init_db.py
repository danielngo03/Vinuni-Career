from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.platform.database.models import (
    CV,
    AIUsageLog,
    Department,
    Event,
    Industry,
    Job,
    JobApplication,
    Organization,
    Permission,
    Role,
    RolePermission,
    SkillDictionary,
    StudentProfile,
    UniversityMajor,
    User,
    UserOrgRole,
)
from app.platform.database.models.base import now_utc
from app.platform.database.session import SessionLocal
from app.shared.enum import (
    ApplicationStatus,
    ApprovalSource,
    DegreeLevel,
    EventStatus,
    EventType,
    ExperienceLevel,
    JobStatus,
    JobType,
    LocationType,
    OrgType,
)
from app.shared.security import hash_password

DEFAULT_SKILLS = [
    ("python", ["py", "python3"]),
    ("fastapi", ["fast api"]),
    ("postgresql", ["postgres", "psql"]),
    ("redis", []),
    ("kafka", ["apache kafka"]),
    ("docker", []),
    ("react", ["reactjs"]),
    ("typescript", ["ts"]),
    ("machine learning", ["ml"]),
    ("llm", ["large language model", "genai"]),
]

DEFAULT_PERMISSIONS = [
    ("org", "create"),
    ("job", "create"),
    ("job", "moderate"),
    ("cv", "mask"),
    ("student", "create"),
    ("event", "create"),
    ("event", "register"),
    ("ai", "use"),
    ("registration", "review"),
    ("taxonomy", "manage"),
]

DEFAULT_INDUSTRIES = [
    ("INFORMATION_TECHNOLOGY", "Công nghệ thông tin", "Information Technology"),
    ("ARTIFICIAL_INTELLIGENCE", "Trí tuệ nhân tạo", "Artificial Intelligence"),
    ("FINANCE_BANKING", "Tài chính và ngân hàng", "Finance and Banking"),
    ("CONSULTING", "Tư vấn", "Consulting"),
    ("HEALTHCARE", "Y tế và chăm sóc sức khỏe", "Healthcare"),
    ("EDUCATION", "Giáo dục", "Education"),
    ("MANUFACTURING", "Sản xuất", "Manufacturing"),
    ("RETAIL_ECOMMERCE", "Bán lẻ và thương mại điện tử", "Retail and E-commerce"),
]

DEMO_PASSWORD = "password123"


def main() -> None:
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.email == "admin@vinuni.local"))
        if not admin:
            admin = User(
                email="admin@vinuni.local",
                full_name="Vinuni Career Admin",
                password_hash=hash_password("ChangeMe123!"),
            )
            db.add(admin)

        university = db.scalar(select(Organization).where(Organization.name == "Demo University"))
        if not university:
            university = Organization(
                name="Demo University",
                type=OrgType.UNIVERSITY,
                is_verified_partner=True,
                metadata_json={"seed": True},
            )
            db.add(university)

        permissions: list[Permission] = []
        for resource, action in DEFAULT_PERMISSIONS:
            permission = db.scalar(
                select(Permission).where(
                    Permission.resource == resource,
                    Permission.action == action,
                )
            )
            if not permission:
                permission = Permission(resource=resource, action=action)
                db.add(permission)
            permissions.append(permission)

        db.flush()
        role = db.scalar(select(Role).where(Role.org_id.is_(None), Role.name == "super_admin"))
        if not role:
            role = Role(org_id=None, name="super_admin")
            db.add(role)
            db.flush()

        for permission in permissions:
            exists = db.get(RolePermission, {"role_id": role.id, "permission_id": permission.id})
            if not exists:
                db.add(RolePermission(role_id=role.id, permission_id=permission.id))

        for name, synonyms in DEFAULT_SKILLS:
            skill = db.scalar(select(SkillDictionary).where(SkillDictionary.name == name))
            if not skill:
                db.add(SkillDictionary(name=name, synonyms=synonyms))

        seed_demo_product_data(db)
        db.commit()
        print("Database initialized.")
        print("Demo accounts:")
        print(f"  student@vinuni.edu.vn / {DEMO_PASSWORD}")
        print(f"  hr@partner.vn / {DEMO_PASSWORD}")
        print(f"  career.center@vinuni.edu.vn / {DEMO_PASSWORD}")


def seed_demo_product_data(db) -> None:
    university = get_or_create_org(
        db,
        name="VinUniversity",
        org_type=OrgType.UNIVERSITY,
        metadata={"location": "Hà Nội", "country": "VN"},
        verified=True,
    )
    fpt = get_or_create_org(
        db,
        name="FPT Smart Cloud",
        org_type=OrgType.PARTNER,
        metadata={"location": "Hà Nội", "industry": "AI Cloud", "salary_range": "12-22 triệu/tháng"},
        verified=True,
    )
    vinbigdata = get_or_create_org(
        db,
        name="VinBigData",
        org_type=OrgType.PARTNER,
        metadata={"location": "Hồ Chí Minh", "industry": "Healthcare AI", "salary_range": "15-25 triệu/tháng"},
        verified=True,
    )
    one_mount = get_or_create_org(
        db,
        name="One Mount Group",
        org_type=OrgType.PARTNER,
        metadata={"location": "Hà Nội", "industry": "Data Platform", "salary_range": "14-24 triệu/tháng"},
        verified=True,
    )

    get_or_create_department(db, university.id, "College of Engineering and Computer Science")
    get_or_create_department(db, university.id, "College of Business and Management")
    get_or_create_department(db, university.id, "Career and Advising Center")

    cs_major = get_or_create_major(db, university.id, "COMP_SCI", "Computer Science", "B.S. in Computer Science")
    get_or_create_major(
        db,
        university.id,
        "BUS_ADMIN",
        "Business Administration",
        "B.B.A. in Business Administration",
    )
    for code, name_vi, name_en in DEFAULT_INDUSTRIES:
        industry = db.scalar(
            select(Industry).where(
                Industry.university_org_id == university.id,
                Industry.code == code,
            )
        )
        if not industry:
            db.add(
                Industry(
                    university_org_id=university.id,
                    code=code,
                    name_vi=name_vi,
                    name_en=name_en,
                )
            )

    engineering = get_or_create_department(db, fpt.id, "Product Engineering")

    student = get_or_create_user(db, "student@vinuni.edu.vn", "Nguyễn Anh Tuấn")
    hr = get_or_create_user(db, "hr@partner.vn", "Trần Minh HR")
    moderator = get_or_create_user(db, "career.center@vinuni.edu.vn", "VinUni Career Center")

    student_role = get_or_create_role(db, university.id, "student")
    hr_role = get_or_create_role(db, fpt.id, "company_hr")
    moderator_role = get_or_create_role(db, university.id, "university_moderator")

    attach_permissions(db, hr_role, [("job", "create"), ("ai", "use")])
    attach_permissions(
        db,
        moderator_role,
        [
            ("job", "moderate"),
            ("org", "create"),
            ("ai", "use"),
            ("registration", "review"),
            ("taxonomy", "manage"),
        ],
    )
    attach_permissions(db, student_role, [("student", "create"), ("cv", "mask"), ("ai", "use")])

    get_or_create_user_org_role(db, student.id, university.id, None, student_role.id)
    get_or_create_user_org_role(db, hr.id, fpt.id, engineering.id, hr_role.id)
    get_or_create_user_org_role(db, moderator.id, university.id, None, moderator_role.id)

    if not db.get(StudentProfile, student.id):
        db.add(
            StudentProfile(
                id=student.id,
                org_id=university.id,
                major_id=cs_major.id,
                student_code="SE2026-001",
                enrollment_year=2022,
                graduation_year=2026,
                degree_level=DegreeLevel.BACHELOR,
                gpa_overall=3.67,
                attendance_overall=96,
                skills=["Python", "FastAPI", "React", "Docker"],
                social_links={"linkedin": "https://linkedin.com/in/student", "github": "https://github.com/student"},
                privacy_settings={"blind_hiring": True, "pii_unmask_requires_consent": True},
            )
        )
        db.flush()

    cv = db.scalar(select(CV).where(CV.student_id == student.id, CV.is_primary.is_(True)))
    if not cv:
        cv = CV(
            student_id=student.id,
            title="Backend AI Engineering CV",
            summary="Passionate AI intern with experience in Python, FastAPI, and RAG architectures.",
            experience_years=0.5,
            skills=["Python", "FastAPI", "PostgreSQL", "Docker", "RAG", "Observability"],
            education_history=[{"school": "VinUniversity", "degree": "B.S. Computer Science", "gpa": 3.67}],
            work_experience=[{"company": "VinUni AI Lab", "role": "Research Assistant", "duration": "3 months"}],
            parsed_data={
                "projects": ["AI monitoring lab", "CV matching API", "PostgreSQL analytics pipeline"],
            },
            masked_data={
                "text": "[MASKED_NAME]\n[MASKED_EMAIL]\nPython, FastAPI, PostgreSQL, Docker, RAG, Observability. Built AI monitoring and CV matching systems.",
                "entities": ["name", "email"],
            },
            is_primary=True,
        )
        db.add(cv)
        db.flush()

    jobs = [
        (
            fpt,
            "Backend AI Engineer Intern",
            "Build production FastAPI services with Python, PostgreSQL, Docker and AI observability for recruitment workflows.",
            ["Python", "FastAPI", "PostgreSQL", "Docker", "Observability"],
            JobStatus.APPROVED,
            JobType.INTERNSHIP,
            ExperienceLevel.INTERN,
            LocationType.HYBRID,
            "FPT Tower, Cau Giay, Hanoi",
            5000000,
            8000000,
        ),
        (
            vinbigdata,
            "LLMOps Analyst Intern",
            "Monitor LLM gateway, Langfuse traces, token usage, prompt quality and fallback reliability across AI products.",
            ["LLMOps", "Langfuse", "LiteLLM", "Monitoring", "Python"],
            JobStatus.APPROVED,
            JobType.INTERNSHIP,
            ExperienceLevel.INTERN,
            LocationType.ONSITE,
            "Vincom Center, District 1, HCM",
            7000000,
            12000000,
        ),
        (
            one_mount,
            "Data Platform Associate",
            "Operate Kafka and ClickHouse data pipelines for large scale user activity analytics and reporting dashboards.",
            ["Kafka", "ClickHouse", "Python", "Analytics"],
            JobStatus.APPROVED,
            JobType.FULL_TIME,
            ExperienceLevel.FRESHER,
            LocationType.HYBRID,
            "Times City, Hanoi",
            15000000,
            22000000,
        ),
        (
            fpt,
            "Junior Prompt Automation Engineer",
            "Design automation workflows for JD moderation. Pending salary policy review by university moderator.",
            ["Prompt Engineering", "Workflow", "Policy Review"],
            JobStatus.PENDING_APPROVAL,
            JobType.FULL_TIME,
            ExperienceLevel.JUNIOR,
            LocationType.REMOTE,
            "",
            12000000,
            20000000,
        ),
    ]
    created_jobs: list[Job] = []
    for org, title, description, skills, status_value, job_type, exp_lvl, loc_type, loc_add, s_min, s_max in jobs:
        job = get_or_create_job(db, org.id, title, description, skills, status_value, job_type, exp_lvl, loc_type, loc_add, s_min, s_max)
        created_jobs.append(job)

    if created_jobs:
        first_job = created_jobs[0]
        existing_app = db.scalar(
            select(JobApplication).where(JobApplication.job_id == first_job.id, JobApplication.student_id == student.id)
        )
        if not existing_app:
            db.add(
                JobApplication(
                    job_id=first_job.id,
                    student_id=student.id,
                    cv_id=cv.id,
                    status=ApplicationStatus.SHORTLISTED,
                    ai_match_score=92.0,
                    ai_reasoning={
                        "summary": "Strong backend and database match.",
                        "matched_skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
                        "missing_skills": [],
                    },
                    consent_to_unmask=False,
                )
            )

    for org in [university, fpt, vinbigdata, one_mount]:
        existing_usage = db.scalar(select(AIUsageLog).where(AIUsageLog.org_id == org.id))
        if not existing_usage:
            db.add(
                AIUsageLog(
                    org_id=org.id,
                    user_id=moderator.id if org.type == OrgType.UNIVERSITY else hr.id,
                    feature_name="demo_dashboard_seed",
                    provider="openrouter",
                    model="nvidia/nemotron-3-ultra-550b-a55b:free",
                    request_id="seed-demo",
                    raw_usage={"source": "seed"},
                    input_tokens=2400,
                    output_tokens=850,
                    cost_usd=0.0042,
                )
            )

    # Seed Demo Event
    event = db.scalar(select(Event).where(Event.org_id == fpt.id))
    if not event:
        event = Event(
            org_id=fpt.id,
            title="FPT Software Career Tour 2026",
            description="Join us for an exclusive look into FPT Software's AI ecosystem.",
            event_type=EventType.COMPANY_TOUR,
            start_time=now_utc() + timedelta(days=10),
            end_time=now_utc() + timedelta(days=10, hours=4),
            location_type="ONSITE",
            location_address="FPT Tower, Cau Giay",
            max_attendees=50,
            status=EventStatus.PUBLISHED,
        )
        db.add(event)
        db.flush()

def get_or_create_major(db, org_id: str, code: str, name: str, description: str) -> UniversityMajor:
    major = db.scalar(select(UniversityMajor).where(UniversityMajor.major_code == code))
    if major:
        return major
    major = UniversityMajor(org_id=org_id, major_code=code, major_name=name, description=description)
    db.add(major)
    db.flush()
    return major


def get_or_create_user(db, email: str, full_name: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if user:
        user.full_name = full_name
        user.password_hash = hash_password(DEMO_PASSWORD)
        user.is_active = True
        user.deleted_at = None
        db.flush()
        return user
    user = User(email=email, full_name=full_name, password_hash=hash_password(DEMO_PASSWORD))
    db.add(user)
    db.flush()
    return user


def get_or_create_org(db, *, name: str, org_type: OrgType, metadata: dict, verified: bool) -> Organization:
    org = db.scalar(select(Organization).where(Organization.name == name))
    if org:
        return org
    org = Organization(name=name, type=org_type, metadata_json=metadata, is_verified_partner=verified)
    db.add(org)
    db.flush()
    return org


def get_or_create_department(db, org_id: str, name: str) -> Department:
    dept = db.scalar(select(Department).where(Department.org_id == org_id, Department.name == name))
    if dept:
        return dept
    dept = Department(org_id=org_id, name=name)
    db.add(dept)
    db.flush()
    return dept


def get_or_create_role(db, org_id: str, name: str) -> Role:
    role = db.scalar(select(Role).where(Role.org_id == org_id, Role.name == name))
    if role:
        return role
    role = Role(org_id=org_id, name=name)
    db.add(role)
    db.flush()
    return role


def attach_permissions(db, role: Role, permission_pairs: list[tuple[str, str]]) -> None:
    for resource, action in permission_pairs:
        permission = db.scalar(select(Permission).where(Permission.resource == resource, Permission.action == action))
        if not permission:
            permission = Permission(resource=resource, action=action)
            db.add(permission)
            db.flush()
        if not db.get(RolePermission, {"role_id": role.id, "permission_id": permission.id}):
            db.add(RolePermission(role_id=role.id, permission_id=permission.id))


def get_or_create_user_org_role(db, user_id: str, org_id: str, dept_id: str | None, role_id: str) -> UserOrgRole:
    item = db.scalar(
        select(UserOrgRole).where(
            UserOrgRole.user_id == user_id,
            UserOrgRole.org_id == org_id,
            UserOrgRole.dept_id.is_(dept_id) if dept_id is None else UserOrgRole.dept_id == dept_id,
            UserOrgRole.role_id == role_id,
        )
    )
    if item:
        return item
    item = UserOrgRole(user_id=user_id, org_id=org_id, dept_id=dept_id, role_id=role_id)
    db.add(item)
    db.flush()
    return item


def get_or_create_job(
    db,
    org_id: str,
    title: str,
    description: str,
    skills: list[str],
    status_value: JobStatus,
    job_type: JobType,
    experience_level: ExperienceLevel,
    location_type: LocationType,
    location_address: str,
    salary_min: int,
    salary_max: int,
) -> Job:
    job = db.scalar(select(Job).where(Job.org_id == org_id, Job.title == title, Job.deleted_at.is_(None)))
    if job:
        return job
    job = Job(
        org_id=org_id,
        title=title,
        description=description,
        job_type=job_type,
        experience_level=experience_level,
        location_type=location_type,
        location_address=location_address,
        salary_min=salary_min,
        salary_max=salary_max,
        currency="VND",
        skills=skills,
        benefits=["Health Insurance", "Macbook", "Lunch"],
        application_deadline=now_utc() + timedelta(days=30),
        is_active=True,
        parsed_requirements={"skills": skills, "location": location_address, "salary_range": f"{salary_min}-{salary_max}"},
        status=status_value,
        approval_source=ApprovalSource.AI_AUTOMATION if status_value == JobStatus.APPROVED else None,
        approved_at=now_utc() if status_value == JobStatus.APPROVED else None,
    )
    db.add(job)
    db.flush()
    return job


if __name__ == "__main__":
    main()
