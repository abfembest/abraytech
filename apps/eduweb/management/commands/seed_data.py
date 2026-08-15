"""
Seeds the whole platform with realistic, cross-linked demo data: academic
structure, staff/students, applications, LMS content, exams, grades,
finance, the public site, the library, support desk, and more — so every
page/modal in the app has real, related records behind it instead of an
empty state or an orphaned row.

Idempotent-ish: safe to re-run (uses get_or_create for lookup-style data),
but user/application/enrollment volume will grow on each run unless
--flush is passed first.

Usage:
    python manage.py seed_data
    python manage.py seed_data --flush
"""
import random
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from faker import Faker

from apps.eduweb.models import (
    AcademicSession, AllRequiredPayments, Announcement, Assignment,
    AssignmentSubmission, AuditLog, Badge, BlogCategory, BlogPost,
    BroadcastMessage, Certificate, ContactMessage, Course, CourseApplication,
    CourseCarryOver, CourseCategory, CourseGrade, CourseIntake,
    CourseRegistration, Department, Discussion, DiscussionReply, Enrollment,
    Exam, ExamQuestion, ExamStatusLog, Faculty, FeePayment, InstitutionMember,
    InstitutionPartner, InstitutionalSubscription, Invoice, JobListing,
    LMSCourse, Lesson, LessonProgress, LessonSection, LibraryItem, Message,
    Notification, PaymentGateway, Program, ProgramSessionCreditCap,
    ProgressionDecisionLog, Quiz, QuizAnswer, QuizAttempt, QuizQuestion,
    QuizResponse, Review, Service, Solution, Industry, Project, Product,
    ConsultationRequest, NewsletterSubscriber, SiteConfig,
    SiteHistoryMilestone, StaffPayroll, StaffPermissionsMatrix, StudentBadge,
    StudentExamResponse, StudyGroup, StudyGroupMember, StudyGroupMessage,
    Subscription, SubscriptionPlan, SupportTicket, SystemConfiguration,
    Testimonial, TicketReply, Transaction, UserProfile, Vendor,
    check_and_award_badges, _score_to_grade,
)
from apps.support.models import (
    SLAPolicy, SupportDepartment, SupportTicketExtra, TicketHistory,
    KBCategory, KBArticle, FAQCategory, FAQ, CannedResponse,
    ChatSession as SupportChatSession, ChatMessage as SupportChatMessage,
    AgentProfile, SupportAnnouncement, SupportAuditLog,
)

fake = Faker()

NG_FIRST_M = ["Chinedu", "Emeka", "Yusuf", "Tunde", "Segun", "Obinna", "Femi",
              "Kelechi", "Nnamdi", "Ibrahim", "Musa", "Chukwuemeka", "Adewale",
              "Uche", "Babatunde", "Suleiman", "Ikenna", "Olumide", "Garba", "Junaid"]
NG_FIRST_F = ["Adaeze", "Ngozi", "Oluwaseun", "Aisha", "Folake", "Kemi",
              "Ifeoma", "Bola", "Amara", "Chiamaka", "Fatima", "Blessing",
              "Chidinma", "Adaobi", "Grace", "Halima", "Zainab", "Nkechi",
              "Yewande", "Rahma"]
NG_LAST = ["Okafor", "Adeyemi", "Balogun", "Eze", "Okonkwo", "Abubakar",
           "Nwosu", "Adewale", "Bello", "Chukwu", "Danjuma", "Ibe", "Lawal",
           "Nwachukwu", "Ogundipe", "Okoro", "Suleiman", "Uduak", "Afolabi",
           "Duru", "Ekwueme", "Garba", "Ike", "Jibril", "Mohammed",
           "Nkemdirim", "Oyelaran", "Adisa", "Chukwuma", "Yakubu"]

INTL_COUNTRIES = ["Ghana", "Kenya", "South Africa", "United Kingdom",
                   "United States", "Canada", "India", "United Arab Emirates",
                   "Cameroon", "Ivory Coast", "Rwanda", "Philippines"]

NOW = timezone.now()


def rand_name(nigerian_ratio=0.75):
    """Return (first, last, nationality) — mostly Nigerian, some international."""
    if random.random() < nigerian_ratio:
        first = random.choice(NG_FIRST_M + NG_FIRST_F)
        last = random.choice(NG_LAST)
        nationality = "Nigerian"
    else:
        first = fake.first_name()
        last = fake.last_name()
        nationality = random.choice(INTL_COUNTRIES)
    return first, last, nationality


def unique_username(first, last):
    base = f"{first}.{last}".lower().replace(" ", "")
    username = base
    n = 1
    while User.objects.filter(username=username).exists():
        n += 1
        username = f"{base}{n}"
    return username


def past_dt(days_min, days_max):
    return NOW - timedelta(days=random.randint(days_min, days_max),
                            hours=random.randint(0, 23), minutes=random.randint(0, 59))


def past_date(days_min, days_max):
    return (NOW - timedelta(days=random.randint(days_min, days_max))).date()


def backdate(model_cls, pk, **fields):
    """Bypass auto_now_add/auto_now to give seeded rows a believable timeline."""
    model_cls.objects.filter(pk=pk).update(**fields)


class Command(BaseCommand):
    help = "Seed the database with realistic, cross-linked demo data across the whole platform."

    def add_arguments(self, parser):
        parser.add_argument("--flush", action="store_true",
                             help="Delete previously-seeded data (keeps superusers) before seeding.")

    def handle(self, *args, **options):
        random.seed(2026)
        fake.seed_instance(2026)

        if options["flush"]:
            self._flush()

        with transaction.atomic():
            self.stdout.write("Seeding academic structure...")
            self._seed_sessions()
            self._seed_faculties()
            self._seed_users_staff()
            self._seed_intakes()

            self.stdout.write("Seeding students + applications...")
            self._seed_applicants_and_students()

            self.stdout.write("Seeding LMS content (lessons/quizzes/assignments)...")
            self._seed_lms_content()

            self.stdout.write("Seeding enrollments, registrations, grades, progress...")
            self._seed_academic_records()

            self.stdout.write("Seeding exams...")
            self._seed_exams()

            self.stdout.write("Seeding finance...")
            self._seed_finance()

            self.stdout.write("Seeding public site content...")
            self._seed_site_content()

            self.stdout.write("Seeding library...")
            self._seed_library()

            self.stdout.write("Seeding communications...")
            self._seed_communications()

            self.stdout.write("Seeding support desk...")
            self._seed_support()

            self.stdout.write("Seeding community (discussions/study groups)...")
            self._seed_community()

            self.stdout.write("Seeding permissions matrix + audit log...")
            self._seed_permissions_and_audit()

            self.stdout.write("Awarding badges...")
            self._award_badges()

        self.stdout.write(self.style.SUCCESS("Seed complete."))
        self._print_summary()

    # ------------------------------------------------------------------
    # FLUSH
    # ------------------------------------------------------------------
    def _flush(self):
        self.stdout.write("Flushing previously seeded data...")
        # StudentExamResponse/Exam use on_delete=PROTECT on their User/LMSCourse
        # FKs, so they must go before the User bulk-delete below.
        StudentExamResponse.objects.all().delete()
        Exam.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()
        for model in [Faculty, Department, Program, Course, AcademicSession,
                      CourseIntake, BlogCategory, BlogPost, Testimonial,
                      Service, Solution, Industry, Project, Product,
                      JobListing, LibraryItem, SiteConfig, PaymentGateway,
                      SubscriptionPlan, Vendor, SupportDepartment, SLAPolicy,
                      KBCategory, FAQCategory, CannedResponse,
                      InstitutionMember, InstitutionPartner,
                      NewsletterSubscriber, SystemConfiguration]:
            model.objects.all().delete()

    # ------------------------------------------------------------------
    # ACADEMIC SESSIONS
    # ------------------------------------------------------------------
    def _seed_sessions(self):
        self.sessions = []
        specs = [
            ("2023/2024", "closed", False),
            ("2024/2025", "closed", False),
            ("2025/2026", "active", True),
        ]
        for name, status, is_current in specs:
            start_year = int(name[:4])
            session, _ = AcademicSession.objects.get_or_create(
                name=name,
                defaults=dict(
                    term_dates=[
                        {"term": "first", "start": f"{start_year}-09-01", "end": f"{start_year}-12-20"},
                        {"term": "second", "start": f"{start_year + 1}-01-15", "end": f"{start_year + 1}-06-15"},
                    ],
                    status=status,
                    is_current=is_current,
                    registration_override="open" if is_current else "closed",
                ),
            )
            self.sessions.append(session)
        self.current_session = self.sessions[-1]
        self.past_sessions = self.sessions[:-1]

    # ------------------------------------------------------------------
    # FACULTIES / DEPARTMENTS / PROGRAMS / COURSES
    # ------------------------------------------------------------------
    # Abraytech Academy's training tracks (= Faculty), practice areas
    # (= Department) and certificate/diploma programs — Abraytech is a
    # technology company (software, cybersecurity, AI & data, cloud/DevOps)
    # that also trains engineers; this is NOT a university, so degree
    # levels stay at certificate/diploma and course topics are real tech
    # curricula, not academic subjects.
    STRUCTURE = {
        "Software & Web Development": {
            "code": "SWD", "icon": "code-2", "color": "blue",
            "departments": {
                "Web Development": {
                    "code": "WEB",
                    "programs": [
                        ("Certificate in Front-End Web Development", "certificate", 1),
                        ("Diploma in Full-Stack Web Development", "diploma", 2),
                    ],
                    "courses": ["HTML, CSS & JavaScript Fundamentals", "React.js Development",
                                "Node.js & Express Backend", "Responsive Web Design",
                                "Version Control with Git", "RESTful API Design",
                                "Database Design with SQL", "Web Application Testing"],
                },
                "Mobile App Development": {
                    "code": "MOB",
                    "programs": [
                        ("Certificate in Mobile App Development", "certificate", 1),
                        ("Diploma in Cross-Platform App Engineering", "diploma", 2),
                    ],
                    "courses": ["Mobile UI/UX Design", "React Native Development",
                                "Flutter & Dart Fundamentals", "iOS Development with Swift",
                                "Android Development with Kotlin", "Mobile App Deployment",
                                "Cross-Platform App Testing", "Mobile App Performance Optimization"],
                },
                "Backend Engineering": {
                    "code": "BKE",
                    "programs": [
                        ("Certificate in Backend Engineering", "certificate", 1),
                        ("Diploma in Software Engineering", "diploma", 2),
                    ],
                    "courses": ["Python Programming Fundamentals", "Object-Oriented Programming",
                                "Database Systems & SQL", "API Development with Django/FastAPI",
                                "Microservices Architecture", "System Design Fundamentals",
                                "Backend Testing & QA", "Server Administration"],
                },
            },
        },
        "Cybersecurity": {
            "code": "CYB", "icon": "shield-check", "color": "navy",
            "departments": {
                "Network Security": {
                    "code": "NSC",
                    "programs": [
                        ("Certificate in Cybersecurity Fundamentals", "certificate", 1),
                        ("Diploma in Network Security", "diploma", 2),
                    ],
                    "courses": ["Networking Fundamentals", "Firewall & VPN Configuration",
                                "Network Security Monitoring", "Intrusion Detection Systems",
                                "Wireless Security", "Security Protocols & Cryptography",
                                "Incident Response", "Network Forensics"],
                },
                "Offensive Security": {
                    "code": "OFS",
                    "programs": [
                        ("Certificate in Ethical Hacking", "certificate", 1),
                        ("Diploma in Penetration Testing", "diploma", 2),
                    ],
                    "courses": ["Ethical Hacking Fundamentals", "Penetration Testing Methodology",
                                "Web Application Security Testing", "Vulnerability Assessment",
                                "Exploit Development Basics", "Social Engineering Awareness",
                                "Capture The Flag (CTF) Practice", "Red Team Operations"],
                },
                "Governance, Risk & Compliance": {
                    "code": "GRC",
                    "programs": [
                        ("Certificate in Security Governance & Risk", "certificate", 1),
                        ("Diploma in IT Governance & Compliance", "diploma", 2),
                    ],
                    "courses": ["Information Security Governance", "Risk Assessment & Management",
                                "Compliance Frameworks (ISO 27001, SOC 2)", "Security Policy Development",
                                "Data Privacy & Protection", "Business Continuity Planning",
                                "Security Audit Fundamentals", "Third-Party Risk Management"],
                },
            },
        },
        "AI & Data Science": {
            "code": "AID", "icon": "brain", "color": "cyan",
            "departments": {
                "Data Science": {
                    "code": "DSC",
                    "programs": [
                        ("Certificate in Data Science Foundations", "certificate", 1),
                        ("Diploma in Data Science", "diploma", 2),
                    ],
                    "courses": ["Python for Data Science", "Statistics & Probability",
                                "Data Wrangling & Cleaning", "Exploratory Data Analysis",
                                "Data Visualization", "SQL for Data Analysis",
                                "Big Data Fundamentals", "Data Science Capstone Project"],
                },
                "Machine Learning Engineering": {
                    "code": "MLE",
                    "programs": [
                        ("Certificate in Machine Learning", "certificate", 1),
                        ("Diploma in Machine Learning Engineering", "diploma", 2),
                    ],
                    "courses": ["Machine Learning Fundamentals", "Supervised Learning Algorithms",
                                "Deep Learning with Neural Networks", "Natural Language Processing",
                                "Computer Vision Basics", "MLOps & Model Deployment",
                                "Feature Engineering", "Model Evaluation & Tuning"],
                },
                "Data Analytics": {
                    "code": "DAN",
                    "programs": [
                        ("Certificate in Data Analytics", "certificate", 1),
                        ("Diploma in Business Intelligence & Analytics", "diploma", 2),
                    ],
                    "courses": ["Business Intelligence Fundamentals", "Excel & Power BI for Analytics",
                                "Data-Driven Decision Making", "Dashboard Design",
                                "A/B Testing & Experimentation", "Predictive Analytics",
                                "Analytics Reporting", "Data Storytelling"],
                },
            },
        },
        "Cloud & DevOps": {
            "code": "CLD", "icon": "cloud", "color": "lime",
            "departments": {
                "Cloud Infrastructure": {
                    "code": "CIN",
                    "programs": [
                        ("Certificate in Cloud Computing", "certificate", 1),
                        ("Diploma in Cloud Architecture", "diploma", 2),
                    ],
                    "courses": ["Cloud Computing Fundamentals", "AWS Core Services",
                                "Azure Fundamentals", "Cloud Architecture Design",
                                "Cloud Cost Optimization", "Cloud Security Basics",
                                "Infrastructure as Code", "Cloud Migration Strategies"],
                },
                "DevOps Engineering": {
                    "code": "DVO",
                    "programs": [
                        ("Certificate in DevOps Fundamentals", "certificate", 1),
                        ("Diploma in DevOps Engineering", "diploma", 2),
                    ],
                    "courses": ["DevOps Fundamentals", "CI/CD Pipeline Design",
                                "Containerization with Docker", "Kubernetes Orchestration",
                                "Configuration Management", "Automated Testing in DevOps",
                                "Monitoring & Logging", "DevSecOps Practices"],
                },
                "Site Reliability Engineering": {
                    "code": "SRE",
                    "programs": [
                        ("Certificate in Site Reliability Engineering", "certificate", 1),
                        ("Diploma in Systems & Reliability Engineering", "diploma", 2),
                    ],
                    "courses": ["SRE Fundamentals", "Incident Management",
                                "Service Level Objectives (SLOs)", "System Reliability Design",
                                "Performance Monitoring & Alerting", "Capacity Planning",
                                "Chaos Engineering Basics", "On-Call Best Practices"],
                },
            },
        },
    }

    def _seed_faculties(self):
        self.faculties = []
        self.departments = []
        self.programs = []
        self.courses = []

        for fac_name, fac_data in self.STRUCTURE.items():
            faculty, _ = Faculty.objects.get_or_create(
                code=fac_data["code"],
                defaults=dict(
                    name=fac_name,
                    icon=fac_data["icon"],
                    color_primary=fac_data["color"],
                    color_secondary=fac_data["color"],
                    tagline=f"Build real, job-ready skills in {fac_name}",
                    description=fake.paragraph(nb_sentences=6),
                    mission=fake.paragraph(nb_sentences=3),
                    vision=fake.paragraph(nb_sentences=3),
                    dean_name=f"{rand_name()[0]} {rand_name()[1]}",
                    dean_role="Head of Training",
                    student_count=random.randint(40, 220),
                    placement_rate=random.randint(70, 98),
                    partner_count=random.randint(5, 25),
                    international_faculty=random.randint(5, 40),
                    accreditation="Curriculum aligned with industry certification standards (AWS, Microsoft, CompTIA, (ISC)²)",
                ),
            )
            self.faculties.append(faculty)

            for dept_name, dept_data in fac_data["departments"].items():
                department, _ = Department.objects.get_or_create(
                    code=dept_data["code"],
                    defaults=dict(
                        faculty=faculty,
                        name=dept_name,
                        description=fake.paragraph(nb_sentences=4),
                    ),
                )
                self.departments.append(department)

                for prog_name, degree_level, duration_years in dept_data["programs"]:
                    CAREER_PATHS_BY_TRACK = {
                        "Software & Web Development": ["Frontend Developer", "Backend Developer", "Full-Stack Engineer", "Mobile App Developer"],
                        "Cybersecurity": ["SOC Analyst", "Penetration Tester", "Security Engineer", "GRC Analyst"],
                        "AI & Data Science": ["Data Analyst", "Data Scientist", "Machine Learning Engineer", "BI Developer"],
                        "Cloud & DevOps": ["Cloud Engineer", "DevOps Engineer", "Site Reliability Engineer", "Cloud Solutions Architect"],
                    }
                    program, _ = Program.objects.get_or_create(
                        code=f"{dept_data['code']}-{degree_level[:3].upper()}",
                        defaults=dict(
                            department=department,
                            name=prog_name,
                            degree_level=degree_level,
                            duration_years=Decimal(duration_years),
                            credits_required=16 if degree_level == "certificate" else 32,
                            max_credits_per_semester=8 if degree_level == "certificate" else 16,
                            tagline=f"Job-ready skills in {dept_name.lower()}, taught by practitioners",
                            overview=fake.paragraph(nb_sentences=5),
                            description=fake.paragraph(nb_sentences=8),
                            entry_requirements=["Basic computer literacy", "A laptop capable of running a code editor",
                                                 "No prior coding experience required for certificate tracks"],
                            core_courses=dept_data["courses"][:4],
                            learning_outcomes=[fake.sentence() for _ in range(4)],
                            career_paths=CAREER_PATHS_BY_TRACK.get(fac_name, [fake.job() for _ in range(4)]),
                            tuition_fee=Decimal(random.choice([450, 650, 900, 1200, 1500, 1900])),
                            available_study_modes=["Full Time", "Online", "Blended"],
                            is_active=True,
                            is_featured=random.random() < 0.3,
                        ),
                    )
                    self.programs.append(program)

                    n_levels = min(duration_years, 4)
                    course_pool = dept_data["courses"]
                    idx = 0
                    for level in range(1, n_levels + 1):
                        for slot in range(2):  # 2 courses per level
                            title = course_pool[idx % len(course_pool)]
                            if slot == 1:
                                title = f"{title} II"
                            idx += 1
                            code = f"{dept_data['code']}{level}{slot + 1}{random.randint(0,9)}"
                            course, created = Course.objects.get_or_create(
                                program=program, code=code,
                                defaults=dict(
                                    name=title,
                                    course_type="core" if slot == 0 else "elective",
                                    credit_units=random.choice([2, 3, 3, 4]),
                                    year_of_study=level,
                                    semester=random.choice(["first", "second"]),
                                    description=fake.paragraph(nb_sentences=3),
                                    learning_outcomes=[fake.sentence() for _ in range(3)],
                                ),
                            )
                            if created:
                                self.courses.append(course)

    # ------------------------------------------------------------------
    # STAFF USERS
    # ------------------------------------------------------------------
    def _make_user(self, role, faculty=None, department=None, program=None,
                    year_of_study=1, extra_profile=None):
        first, last, nationality = rand_name()
        username = unique_username(first, last)
        email = f"{username}@abraytech.com" if role != "student" else f"{username}@learners.abraytech.com"
        user = User.objects.create_user(
            username=username, email=email, password="Passw0rd!2026",
            first_name=first, last_name=last,
        )
        profile = user.profile
        profile.role = role
        profile.faculty = faculty
        profile.department = department
        profile.program = program
        profile.year_of_study = year_of_study
        profile.country = nationality if nationality != "Nigerian" else "Nigeria"
        profile.phone = fake.phone_number()[:20]
        profile.bio = fake.sentence(nb_words=12)
        profile.city = fake.city()
        profile.email_verified = True
        profile.admission_session = self.current_session
        if extra_profile:
            for k, v in extra_profile.items():
                setattr(profile, k, v)
        profile.save()
        return user

    def _seed_users_staff(self):
        self.admins = [self._make_user("admin") for _ in range(4)]
        self.finance_staff = [self._make_user("finance") for _ in range(3)]
        self.support_staff = [self._make_user("support") for _ in range(5)]

        self.instructors = []
        for department in self.departments:
            for _ in range(2):
                instr = self._make_user("instructor", faculty=department.faculty, department=department)
                self.instructors.append(instr)

    # ------------------------------------------------------------------
    # INTAKES
    # ------------------------------------------------------------------
    def _seed_intakes(self):
        self.intakes = []
        for program in self.programs:
            for period, month in [("september", 9), ("january", 1)]:
                year = 2026 if period == "january" else 2025
                intake, _ = CourseIntake.objects.get_or_create(
                    program=program, intake_period=period, year=year,
                    defaults=dict(
                        application_start_date=date(year, month, 1) - timedelta(days=90),
                        start_date=date(year, month, 1),
                        application_deadline=date(year, month, 1) - timedelta(days=14),
                        application_fee=Decimal(random.choice([50, 75, 100])),
                        available_slots=random.randint(30, 80),
                    ),
                )
                self.intakes.append(intake)

    # ------------------------------------------------------------------
    # APPLICANTS + STUDENTS
    # ------------------------------------------------------------------
    def _seed_applicants_and_students(self):
        self.students = []
        self.applications = []

        # Prospect applications not yet tied to an account (draft / rejected / withdrawn)
        for _ in range(25):
            first, last, nationality = rand_name()
            program = random.choice(self.programs)
            status = random.choice(["draft", "pending_payment", "under_review", "rejected", "withdrawn"])
            app = CourseApplication.objects.create(
                user=None, program=program,
                academic_session=self.current_session,
                intake=random.choice([i for i in self.intakes if i.program == program]),
                study_mode=random.choice(["Full Time", "Part Time", "Online"]),
                first_name=first, last_name=last,
                email=f"{first}.{last}{random.randint(1,999)}@example.com".lower(),
                phone=fake.phone_number()[:20],
                date_of_birth=past_date(365 * 30, 365 * 45),
                gender=random.choice(["male", "female"]),
                nationality=nationality,
                address_line1=fake.street_address(),
                city=fake.city(), state=fake.state(), postal_code=fake.postcode(),
                country=nationality if nationality != "Nigerian" else "Nigeria",
                highest_qualification=random.choice(["Secondary School Certificate", "Diploma", "Bachelor's Degree"]),
                institution_name=fake.company() + " College",
                graduation_year=str(random.randint(2018, 2025)),
                gpa_or_grade=random.choice(["A", "B+", "3.5 CGPA", "Merit"]),
                work_experience_years=random.randint(0, 6),
                personal_statement=fake.paragraph(nb_sentences=5),
                emergency_contact_name=f"{rand_name()[0]} {rand_name()[1]}",
                emergency_contact_phone=fake.phone_number()[:20],
                emergency_contact_relationship=random.choice(["Parent", "Sibling", "Spouse", "Guardian"]),
                status=status,
                accept_privacy_policy=True, accept_terms_conditions=True,
            )
            backdate(CourseApplication, app.pk, created_at=past_dt(30, 400))
            self.applications.append(app)

        # Enrolled students — approved applications with real accounts
        n_students = 130
        for _ in range(n_students):
            program = random.choice(self.programs)
            max_level = min(int(program.duration_years), 4)
            year_of_study = random.randint(1, max_level)
            first, last, nationality = rand_name()

            student = self._make_user(
                "student",
                faculty=program.department.faculty,
                department=program.department,
                program=program,
                year_of_study=year_of_study,
                extra_profile=dict(
                    first_name_override=None,
                    progression_status="active",
                ),
            )
            student.first_name, student.last_name = first, last
            student.save()

            intake_choices = [i for i in self.intakes if i.program == program]
            app = CourseApplication.objects.create(
                user=student, program=program,
                academic_session=random.choice(self.past_sessions) if year_of_study > 1 else self.current_session,
                intake=random.choice(intake_choices) if intake_choices else None,
                entry_level=1,
                study_mode=random.choice(["Full Time", "Online", "Blended"]),
                first_name=first, last_name=last, email=student.email,
                phone=fake.phone_number()[:20],
                date_of_birth=past_date(365 * 19, 365 * 35),
                gender=random.choice(["male", "female"]),
                nationality=nationality,
                address_line1=fake.street_address(),
                city=fake.city(), state=fake.state(), postal_code=fake.postcode(),
                country=nationality if nationality != "Nigerian" else "Nigeria",
                highest_qualification="Secondary School Certificate",
                institution_name=fake.company() + " Secondary School",
                graduation_year=str(random.randint(2018, 2024)),
                gpa_or_grade=random.choice(["A", "B+", "B", "Distinction"]),
                work_experience_years=random.randint(0, 4),
                personal_statement=fake.paragraph(nb_sentences=5),
                emergency_contact_name=f"{rand_name()[0]} {rand_name()[1]}",
                emergency_contact_phone=fake.phone_number()[:20],
                emergency_contact_relationship=random.choice(["Parent", "Sibling", "Guardian"]),
                status="approved",
                reviewer=random.choice(self.admins),
                submitted_at=past_dt(200, 500),
                reviewed_at=past_dt(190, 495),
                admission_accepted=True,
                admission_accepted_at=past_dt(185, 490),
                accept_privacy_policy=True, accept_terms_conditions=True,
            )
            backdate(CourseApplication, app.pk, created_at=past_dt(200, 500),
                     admission_number=f"ABT/{random.randint(2022,2025)}/{app.pk:05d}")
            self.applications.append(app)
            self.students.append(student)

        # A handful of graduated alumni
        self.graduates = self.students[:12]
        for grad in self.graduates:
            grad.profile.progression_status = "graduated"
            grad.profile.year_of_study = min(int(grad.profile.program.duration_years), 4)
            grad.profile.save()

    # ------------------------------------------------------------------
    # LMS CONTENT
    # ------------------------------------------------------------------
    def _seed_lms_content(self):
        self.lms_courses = []
        for course in self.courses:
            lecturer = random.choice([
                i for i in self.instructors if i.profile.department_id == course.program.department_id
            ] or self.instructors)

            lms = LMSCourse.objects.create(
                title=course.name,
                code=f"{course.code}-{course.pk}",
                short_description=fake.sentence(nb_words=15),
                description=fake.paragraph(nb_sentences=6),
                learning_objectives=[fake.sentence() for _ in range(4)],
                prerequisites=[],
                academic_course=course,
                session=self.current_session,
                term=course.semester,
                lecturer=lecturer,
                instructor=lecturer,
                difficulty_level=course.level,
                is_published=True,
                is_featured=random.random() < 0.15,
            )
            backdate(LMSCourse, lms.pk, created_at=past_dt(60, 300), published_at=past_dt(55, 295))
            self.lms_courses.append(lms)

            sections = []
            for s in range(2):
                section = LessonSection.objects.create(
                    course=lms, title=f"Module {s + 1}: {fake.catch_phrase()}",
                    description=fake.sentence(), display_order=s,
                )
                sections.append(section)

            lessons = []
            for section in sections:
                for l in range(3):
                    lesson = Lesson.objects.create(
                        course=lms, section=section,
                        title=fake.sentence(nb_words=5).rstrip("."),
                        lesson_type=random.choice(["video", "text", "video", "file"]),
                        description=fake.sentence(),
                        content=fake.paragraph(nb_sentences=10),
                        video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ" if random.random() < 0.6 else "",
                        video_duration_minutes=random.randint(5, 40),
                        is_preview=(l == 0 and section.display_order == 0),
                        display_order=l,
                    )
                    lessons.append(lesson)

            # one quiz on the first lesson of each section
            for section, lesson in zip(sections, [lessons[0], lessons[3]]):
                quiz = Quiz.objects.create(
                    lesson=lesson, title=f"{section.title} Check",
                    description="Test your understanding of this module.",
                    time_limit_minutes=20, passing_score=Decimal("60.00"), max_attempts=3,
                )
                for q in range(5):
                    question = QuizQuestion.objects.create(
                        quiz=quiz, question_type="multiple_choice",
                        question_text=fake.sentence() + "?",
                        points=Decimal("2.00"), display_order=q,
                    )
                    correct_idx = random.randint(0, 3)
                    for a in range(4):
                        QuizAnswer.objects.create(
                            question=question,
                            answer_text=fake.sentence(nb_words=4).rstrip("."),
                            is_correct=(a == correct_idx), display_order=a,
                        )

            # one assignment
            Assignment.objects.create(
                lesson=lessons[0], title=f"{course.name} Assignment",
                description=fake.paragraph(nb_sentences=3),
                instructions=fake.paragraph(nb_sentences=2),
                due_date=NOW + timedelta(days=random.randint(-30, 30)),
                allow_late_submission=True, late_penalty_percent=10,
            )

    # ------------------------------------------------------------------
    # ENROLLMENTS / REGISTRATIONS / GRADES / PROGRESS
    # ------------------------------------------------------------------
    def _seed_academic_records(self):
        lms_by_course = {lms.academic_course_id: lms for lms in self.lms_courses}

        for student in self.students:
            profile = student.profile
            program = profile.program
            current_level = profile.year_of_study
            student_courses = [c for c in self.courses if c.program_id == program.id]

            for course in student_courses:
                if course.year_of_study > current_level:
                    continue
                is_current = course.year_of_study == current_level
                lms = lms_by_course.get(course.id)
                session = self.current_session if is_current else random.choice(self.past_sessions)

                # -- CourseRegistration --
                reg = CourseRegistration(
                    student=student, course=course, session=session,
                    term=course.semester if course.semester != "annual" else "first",
                    status="approved",
                )
                reg.save(skip_window_check=True)
                backdate(CourseRegistration, reg.pk, registered_at=past_dt(20, 500))

                failed = (not is_current) and random.random() < 0.08

                if not is_current:
                    score = Decimal(random.randint(30, 45)) if failed else Decimal(random.randint(45, 98))
                    grade_letter = _score_to_grade(float(score))
                    grade = CourseGrade.objects.create(
                        student=student, course=course, lms_course=lms, session=session,
                        term=course.semester,
                        score=score, grade=grade_letter,
                        credit_units=course.credit_units,
                        is_passed=not failed,
                        result_status="released",
                        recorded_by=random.choice(self.instructors),
                    )
                    backdate(CourseGrade, grade.pk, recorded_at=past_dt(20, 480))

                    if failed:
                        CourseCarryOver.objects.get_or_create(
                            student=student, course=course,
                            defaults=dict(
                                first_failed_session=session,
                                first_failed_term=course.semester,
                                attempts=1,
                            ),
                        )

                if lms:
                    if is_current:
                        enrollment = Enrollment.objects.create(
                            student=student, course=lms, enrolled_by=student,
                            progress_percentage=Decimal(random.randint(5, 90)),
                            completed_lessons=random.randint(0, 5),
                            status="active",
                        )
                        backdate(Enrollment, enrollment.pk, enrolled_at=past_dt(10, 150))
                    else:
                        enrollment = Enrollment.objects.create(
                            student=student, course=lms, enrolled_by=student,
                            progress_percentage=Decimal("100.00") if not failed else Decimal(random.randint(20, 60)),
                            completed_lessons=6 if not failed else random.randint(1, 3),
                            status="completed" if not failed else "dropped",
                        )
                        backdate(Enrollment, enrollment.pk,
                                 enrolled_at=past_dt(200, 500),
                                 completed_at=past_dt(20, 190) if not failed else None)

                    for lesson in Lesson.objects.filter(course=lms):
                        completed = (not is_current) and not failed
                        progress = LessonProgress.objects.create(
                            enrollment=enrollment, lesson=lesson,
                            is_completed=completed or (is_current and random.random() < 0.4),
                            completion_percentage=Decimal("100.00") if completed else Decimal(random.randint(0, 80)),
                            time_spent_minutes=random.randint(5, 60),
                        )
                        if progress.is_completed:
                            backdate(LessonProgress, progress.pk, completed_at=past_dt(15, 480))

                    # quiz attempts
                    for quiz in Quiz.objects.filter(lesson__course=lms):
                        if is_current and random.random() < 0.5:
                            continue
                        score = random.randint(4, 10)
                        attempt = QuizAttempt.objects.create(
                            quiz=quiz, student=student,
                            score=Decimal(score), max_score=Decimal("10.00"),
                            percentage=Decimal(score * 10),
                            is_completed=True, passed=score >= 6,
                            time_taken_minutes=random.randint(5, 18),
                        )
                        backdate(QuizAttempt, attempt.pk, started_at=past_dt(20, 400))
                        for question in quiz.questions.all():
                            answers = list(question.answers.all())
                            chosen = random.choice(answers) if random.random() < 0.8 else \
                                next((a for a in answers if a.is_correct), answers[0])
                            QuizResponse.objects.create(
                                attempt=attempt, question=question, selected_answer=chosen,
                                is_correct=chosen.is_correct,
                                points_earned=question.points if chosen.is_correct else Decimal("0.00"),
                            )

                    # assignment submissions
                    for assignment in Assignment.objects.filter(lesson__course=lms):
                        if is_current and random.random() < 0.4:
                            continue
                        score = Decimal(random.randint(50, 100))
                        sub = AssignmentSubmission.objects.create(
                            assignment=assignment, student=student,
                            submission_text=fake.paragraph(nb_sentences=4),
                            score=score, feedback=fake.sentence(),
                            graded_by=random.choice(self.instructors),
                            status="graded",
                        )
                        backdate(AssignmentSubmission, sub.pk,
                                 submitted_at=past_dt(20, 200), graded_at=past_dt(15, 195),
                                 created_at=past_dt(25, 205))

            # Reviews for a couple of completed LMS courses
            completed_enrollments = Enrollment.objects.filter(student=student, status="completed")[:2]
            for enrollment in completed_enrollments:
                if not Review.objects.filter(course=enrollment.course, student=student).exists():
                    Review.objects.create(
                        course=enrollment.course, student=student,
                        rating=random.randint(3, 5),
                        review_text=fake.sentence(nb_words=15),
                    )

        # Program certificates for graduates
        for grad in self.graduates:
            Certificate.objects.get_or_create(
                student=grad, program=grad.profile.program, certificate_type="program",
                defaults=dict(
                    completion_date=past_date(30, 200),
                    grade=random.choice(["Distinction", "Merit", "Pass"]),
                    payment_status="paid",
                ),
            )
        # LMS course certificates for some completed enrollments
        for enrollment in Enrollment.objects.filter(status="completed").order_by("?")[:40]:
            Certificate.objects.get_or_create(
                student=enrollment.student, course=enrollment.course, certificate_type="lms_course",
                defaults=dict(
                    completion_date=enrollment.completed_at.date() if enrollment.completed_at else past_date(10, 100),
                    grade=random.choice(["A", "B", "C"]),
                    payment_status=random.choice(["paid", "paid", "unpaid"]),
                ),
            )

    # ------------------------------------------------------------------
    # EXAMS
    # ------------------------------------------------------------------
    def _seed_exams(self):
        sample_courses = random.sample(self.lms_courses, k=min(30, len(self.lms_courses)))
        for lms in sample_courses:
            exam = Exam.objects.create(
                title=f"{lms.title} - End of Semester Exam",
                description=f"Comprehensive assessment covering {lms.title}.",
                exam_type="end_of_semester",
                course=lms, instructor=lms.instructor,
                start_datetime=NOW - timedelta(days=random.randint(5, 40)),
                end_datetime=NOW - timedelta(days=random.randint(1, 4)),
                total_marks=Decimal("100.00"), pass_mark=Decimal("50.00"),
                show_result_immediately=True,
                status="published",
                submitted_by=lms.instructor, submitted_at=past_dt(45, 60),
                approved_by=random.choice(self.admins), approved_at=past_dt(42, 55),
                published_by=random.choice(self.admins), published_at=past_dt(40, 50),
                created_by=lms.instructor,
                instructions="Answer all questions. No external materials permitted.",
            )
            backdate(Exam, exam.pk, created_at=past_dt(50, 65))
            ExamStatusLog.objects.create(exam=exam, from_status="draft", to_status="submitted",
                                          changed_by=lms.instructor, note="Submitted for approval")
            ExamStatusLog.objects.create(exam=exam, from_status="submitted", to_status="approved",
                                          changed_by=random.choice(self.admins), note="Looks good")
            ExamStatusLog.objects.create(exam=exam, from_status="approved", to_status="published",
                                          changed_by=random.choice(self.admins), note="Published to students")

            questions = []
            for q in range(10):
                correct_idx = random.randint(0, 3)
                options = [
                    {"id": f"opt-{uuid.uuid4().hex[:8]}",
                     "text": fake.sentence(nb_words=4).rstrip("."),
                     "is_correct": a == correct_idx}
                    for a in range(4)
                ]
                question = ExamQuestion.objects.create(
                    exam=exam, question_text=fake.sentence() + "?",
                    question_type="mcq", marks=Decimal("10.00"),
                    options=options, accepted_answers=[],
                    created_by=lms.instructor,
                )
                questions.append(question)

            enrolled_students = User.objects.filter(enrollments__course=lms).distinct()
            for student in enrolled_students:
                if random.random() < 0.25:
                    continue  # some students were absent
                answers = {}
                score = 0
                for question in questions:
                    correct_opt = next(o for o in question.options if o["is_correct"])
                    if random.random() < 0.7:
                        chosen = correct_opt
                        score += float(question.marks)
                    else:
                        chosen = random.choice(question.options)
                    answers[str(question.pk)] = chosen["id"]
                resp = StudentExamResponse.objects.create(
                    exam=exam, student=student,
                    assigned_question_ids=[q.pk for q in questions],
                    answers=answers,
                    total_score=Decimal(str(score)),
                    score_percentage=Decimal(str(score)),
                    passed=score >= 50,
                    status="graded",
                    graded_by=lms.instructor,
                )
                backdate(StudentExamResponse, resp.pk,
                         submitted_at=past_dt(5, 35), graded_at=past_dt(3, 30),
                         created_at=past_dt(6, 36))

    # ------------------------------------------------------------------
    # FINANCE
    # ------------------------------------------------------------------
    def _seed_finance(self):
        for gw_name, gw_type in [("Stripe", "stripe"), ("PayPal", "paypal")]:
            PaymentGateway.objects.get_or_create(
                slug=gw_name.lower(),
                defaults=dict(name=gw_name, gateway_type=gw_type, is_active=True, is_test_mode=True),
            )
        stripe_gw = PaymentGateway.objects.filter(gateway_type="stripe").first()

        required_payments = []
        for program in self.programs:
            for purpose, amount in [("Tuition Fee - Full Semester", program.tuition_fee / 2),
                                     ("Library Fee", Decimal("25.00")),
                                     ("Technology Fee", Decimal("40.00"))]:
                rp, _ = AllRequiredPayments.objects.get_or_create(
                    program=program, academic_session=self.current_session,
                    purpose=purpose, semester="first",
                    defaults=dict(amount=amount, who_to_pay="student",
                                  due_date=date.today() + timedelta(days=30)),
                )
                required_payments.append(rp)

        for student in self.students:
            student_fees = [rp for rp in required_payments if rp.program_id == student.profile.program_id]
            for fee in student_fees:
                status = random.choices(["success", "pending", "failed"], weights=[80, 15, 5])[0]
                payment = FeePayment.objects.create(
                    fee=fee, user=student, amount=fee.amount,
                    status=status,
                    payment_method=random.choice(["card", "bank_transfer"]),
                    payment_reference=f"FEE-{uuid.uuid4().hex[:12].upper()}",
                )
                backdate(FeePayment, payment.pk, created_at=past_dt(10, 300),
                         paid_at=past_dt(9, 299) if status == "success" else None)

            invoice = Invoice.objects.create(
                invoice_number=f"INV-{uuid.uuid4().hex[:10].upper()}",
                student=student, subtotal=student.profile.program.tuition_fee,
                tax_rate=Decimal("0.00"), tax_amount=Decimal("0.00"),
                discount_amount=Decimal("0.00"),
                total_amount=student.profile.program.tuition_fee,
                status=random.choice(["paid", "paid", "sent", "overdue"]),
                due_date=date.today() + timedelta(days=random.randint(-30, 60)),
            )
            backdate(Invoice, invoice.pk, created_at=past_dt(10, 300))

            if random.random() < 0.6:
                txn = Transaction.objects.create(
                    transaction_id=f"TXN-{uuid.uuid4().hex[:12].upper()}",
                    user=student, transaction_type="enrollment",
                    amount=student.profile.program.tuition_fee / 4,
                    gateway=stripe_gw, status="completed",
                )
                backdate(Transaction, txn.pk, created_at=past_dt(10, 300), completed_at=past_dt(9, 299))

        # subscription plans + subscriptions (institutional online-access tiers)
        plans = []
        for name, price, cycle in [("Basic Access", 19, "monthly"), ("Pro Learner", 49, "monthly"),
                                    ("Annual Unlimited", 399, "yearly")]:
            plan, _ = SubscriptionPlan.objects.get_or_create(
                slug=name.lower().replace(" ", "-"),
                defaults=dict(name=name, description=fake.sentence(),
                              features=[fake.sentence() for _ in range(3)],
                              price=Decimal(price), billing_cycle=cycle,
                              is_popular=(name == "Pro Learner")),
            )
            plans.append(plan)
        for student in random.sample(self.students, k=min(25, len(self.students))):
            Subscription.objects.get_or_create(
                user=student, plan=random.choice(plans),
                defaults=dict(end_date=date.today() + timedelta(days=180)),
            )

        InstitutionalSubscription.objects.get_or_create(
            purpose="Turnitin Plagiarism Detection - Annual License",
            defaults=dict(amount=Decimal("4500.00"), start_date=date(2025, 9, 1),
                          expiry_date=date(2026, 8, 31), created_by=random.choice(self.admins)),
        )
        InstitutionalSubscription.objects.get_or_create(
            purpose="Zoom Education Plan - Annual License",
            defaults=dict(amount=Decimal("2200.00"), start_date=date(2025, 9, 1),
                          expiry_date=date(2026, 8, 31), created_by=random.choice(self.admins)),
        )

        # payroll for staff
        all_staff = self.admins + self.finance_staff + self.support_staff + self.instructors
        for staff in all_staff:
            base = Decimal(random.choice([1800, 2200, 2600, 3200, 4000]))
            for months_ago in range(3):
                month_date = (date.today().replace(day=1) - timedelta(days=months_ago * 30))
                gross = base + Decimal("200.00")
                tax = gross * Decimal("0.10")
                net = gross - tax
                payroll = StaffPayroll.objects.create(
                    payroll_reference=f"PR-{uuid.uuid4().hex[:10].upper()}",
                    staff=staff, month=month_date.month, year=month_date.year,
                    base_salary=base, allowances=Decimal("200.00"),
                    gross_salary=gross, tax_deduction=tax, net_salary=net,
                    payment_status="paid", payment_method="bank_transfer",
                    payment_date=month_date,
                    bank_name=random.choice(["GTBank", "Access Bank", "Zenith Bank", "First Bank"]),
                    account_number=str(random.randint(10**9, 10**10 - 1)),
                    created_by=random.choice(self.finance_staff),
                    approved_by=random.choice(self.admins),
                )
                backdate(StaffPayroll, payroll.pk, created_at=past_dt(30, 100))

        for i in range(4):
            Vendor.objects.get_or_create(
                slug=f"vendor-{i+1}",
                defaults=dict(name=fake.company(), email=fake.company_email(),
                              country=random.choice(["Nigeria", "United States", "United Kingdom"])),
            )

    # ------------------------------------------------------------------
    # PUBLIC SITE CONTENT
    # ------------------------------------------------------------------
    def _seed_site_content(self):
        SiteConfig.objects.get_or_create(
            pk=1,
            defaults=dict(
                school_name="Abraytech",
                school_short_name="Abraytech",
                tagline="Building Digital Solutions for a Smarter Future",
                email="info@abraytech.com", phone_primary="+1 302 555 0142",
                phone_ng_primary="+234 803 555 0199",
                whatsapp="+234 803 555 0199",
                email_admissions="academy@abraytech.com",
                address_usa="8 The Green, Suite A, Dover, DE 19901, USA",
                address_nigeria="Landmark Towers, Water Corporation Drive, Victoria Island, Lagos, Nigeria",
                facebook="https://facebook.com/abraytech", instagram="https://instagram.com/abraytech",
                linkedin="https://linkedin.com/company/abraytech",
                twitter="https://twitter.com/abraytech",
                about_mission="Abraytech delivers reliable, well-engineered technology services and makes high-quality technical training accessible to everyone we work with.",
                about_vision="Abraytech is a technology company built to help organizations design, build, secure, and scale the software and systems they run on.",
                copyright_year="2026",
            ),
        )
        site = SiteConfig.objects.first()
        for year, title in [(2016, "Abraytech Founded"), (2019, "Launched Managed Security Services"),
                             (2021, "Opened Abraytech Academy"), (2024, "500th Academy Graduate")]:
            SiteHistoryMilestone.objects.get_or_create(
                site=site, year=year,
                defaults=dict(title=title, description=fake.sentence(nb_words=18)),
            )

        blog_categories = []
        for name in ["Company News", "Engineering Deep Dives", "Academy & Training", "Cybersecurity", "Client Success Stories"]:
            cat, _ = BlogCategory.objects.get_or_create(name=name, defaults=dict(description=fake.sentence()))
            blog_categories.append(cat)

        for _ in range(25):
            author = random.choice(self.admins + self.instructors)
            title = fake.sentence(nb_words=8).rstrip(".")
            post = BlogPost.objects.create(
                title=title, subtitle=fake.sentence(nb_words=10),
                excerpt=fake.paragraph(nb_sentences=2)[:490],
                content="\n\n".join(fake.paragraphs(nb=6)),
                category=random.choice(blog_categories), tags=fake.words(nb=4),
                author=author, author_name=author.get_full_name(),
                author_title=author.profile.role.title(),
                read_time=random.randint(3, 12),
                status="published", is_featured=random.random() < 0.15,
            )
            backdate(BlogPost, post.pk, created_at=past_dt(5, 500), publish_date=past_dt(5, 500))

        for _ in range(7):
            person = random.choice(self.students + self.instructors)
            Testimonial.objects.create(
                quote=fake.paragraph(nb_sentences=2),
                author_name=person.get_full_name(),
                author_role=("Abraytech Academy Graduate" if person in self.students else "Abraytech Instructor"),
            )
        for _ in range(8):
            Testimonial.objects.create(
                quote=fake.paragraph(nb_sentences=2),
                author_name=fake.name(),
                author_role=f"{random.choice(['CEO', 'CTO', 'COO', 'Head of Engineering', 'IT Director'])}, {fake.company()}",
            )

        services = []
        for title in ["Software Development", "Cybersecurity Services", "AI & Data Solutions",
                      "IT Consulting", "Cloud & DevOps Services", "Technology Training"]:
            svc, _ = Service.objects.get_or_create(
                title=title,
                defaults=dict(summary=fake.sentence(nb_words=20), description=fake.paragraph(nb_sentences=4)),
            )
            services.append(svc)

        industries = []
        for title in ["Healthcare", "Financial Services", "Education", "Government & Public Sector",
                      "Retail & E-Commerce", "Technology"]:
            ind, _ = Industry.objects.get_or_create(
                title=title,
                defaults=dict(summary=fake.sentence(nb_words=20), description=fake.paragraph(nb_sentences=3)),
            )
            industries.append(ind)

        solution_titles = ["Cloud Migration", "Managed IT Services", "Custom Software Platforms",
                            "Enterprise Security Hardening", "Data Platform Modernization",
                            "DevOps Transformation", "Legacy System Modernization", "AI-Powered Automation"]
        for i, title in enumerate(solution_titles):
            sol, _ = Solution.objects.get_or_create(
                title=title,
                defaults=dict(summary=fake.sentence(nb_words=18),
                              description=fake.paragraph(nb_sentences=3), order=i),
            )
            sol.related_services.set(random.sample(services, k=random.randint(1, 3)))

        for i in range(10):
            Project.objects.get_or_create(
                title=fake.catch_phrase(),
                defaults=dict(
                    summary=fake.sentence(nb_words=20), client_name=fake.company(),
                    industry=random.choice(industries), service=random.choice(services),
                    challenge=fake.paragraph(nb_sentences=2),
                    solution_text=fake.paragraph(nb_sentences=2),
                    results=fake.paragraph(nb_sentences=2),
                    is_featured=random.random() < 0.2, order=i,
                ),
            )

        product_titles = ["CodeGuard Security Scanner", "DataPulse Analytics Dashboard",
                           "CloudSync Migration Toolkit", "DevFlow CI/CD Suite",
                           "ThreatWatch Monitoring Platform", "InsightAI Automation Engine"]
        for i, title in enumerate(product_titles):
            Product.objects.get_or_create(
                title=title,
                defaults=dict(summary=fake.sentence(nb_words=15), description=fake.paragraph(nb_sentences=2),
                              price=Decimal(random.choice([49, 79, 99, 149, 199])), order=i),
            )

        for title in ["Software Engineer (Backend)", "Frontend Developer", "Cybersecurity Analyst",
                      "Data Scientist", "DevOps Engineer", "Technical Trainer / Instructor",
                      "IT Support Specialist", "Product Marketing Manager", "Cloud Solutions Architect",
                      "QA Engineer"]:
            JobListing.objects.get_or_create(
                title=title,
                defaults=dict(
                    department=random.choice(["Engineering", "Security", "Data & AI", "Cloud & DevOps", "Academy", "IT"]),
                    location=random.choice(["Lagos, Nigeria", "Remote", "Dover, DE, USA"]),
                    employment_type=random.choice(["full_time", "part_time", "contract"]),
                    description=fake.paragraph(nb_sentences=4),
                    requirements=fake.paragraph(nb_sentences=3),
                    closes_at=date.today() + timedelta(days=random.randint(10, 90)),
                ),
            )

        for _ in range(15):
            ConsultationRequest.objects.create(
                name=fake.name(), email=fake.email(), phone=fake.phone_number()[:30],
                company=fake.company(), service_interest=random.choice(services),
                preferred_date=date.today() + timedelta(days=random.randint(1, 30)),
                message=fake.sentence(nb_words=20),
                status=random.choice(["new", "contacted", "scheduled", "completed"]),
            )

        for _ in range(40):
            NewsletterSubscriber.objects.get_or_create(email=fake.unique.email())

        for i, (member_type, title_prefix) in enumerate(
            [("admin_board", "CEO & Founder"), ("admin_board", "Chief Technology Officer"),
             ("academic_board", "Head of Abraytech Academy"), ("advisorate_board", "Board Advisor")] * 3
        ):
            first, last, _ = rand_name()
            InstitutionMember.objects.get_or_create(
                name=f"{first} {last}", member_type=member_type,
                defaults=dict(role=title_prefix,
                              bio=fake.paragraph(nb_sentences=2), is_who_we_are=(i < 4)),
            )

        for name, category in [("ISO/IEC 27001 Information Security Certified", "accreditation"),
                                ("AWS Advanced Consulting Partner", "partner"),
                                ("Microsoft Solutions Partner", "partner"),
                                ("AWS Academy Training Partner", "partner"),
                                ("(ISC)² Official Training Provider", "affiliation"),
                                ("Google Cloud Partner", "partner")]:
            InstitutionPartner.objects.get_or_create(name=name, defaults=dict(category=category))

        for key, value, vtype in [
            ("site_maintenance_mode", "false", "boolean"),
            ("max_upload_size_mb", "25", "number"),
            ("default_currency", "USD", "text"),
            ("registration_open", "true", "boolean"),
        ]:
            SystemConfiguration.objects.get_or_create(
                key=key, defaults=dict(value=value, setting_type=vtype, is_public=(key != "max_upload_size_mb")),
            )

    # ------------------------------------------------------------------
    # LIBRARY
    # ------------------------------------------------------------------
    def _seed_library(self):
        subjects = ["Software Engineering", "Cybersecurity", "Cloud Computing", "Data Science",
                    "Machine Learning", "DevOps", "Web Development", "Mobile Development",
                    "IT Project Management", "Network Security"]
        for _ in range(45):
            title = f"{random.choice(['Introduction to', 'Advanced', 'Principles of', 'Understanding', 'Modern'])} {random.choice(subjects)}"
            LibraryItem.objects.get_or_create(
                title=title, author=fake.name(),
                defaults=dict(
                    category=random.choice(["Books", "Periodicals", "References", "Other"]),
                    subcategory=random.choice(subjects),
                    publisher=fake.company(),
                    year=random.randint(2010, 2025),
                    isbn=fake.isbn13(),
                    language="en",
                    description=fake.paragraph(nb_sentences=3),
                    access=random.choice(["public", "public", "members"]),
                    featured=random.random() < 0.15,
                    created_by=random.choice(self.admins),
                    view_count=random.randint(0, 800),
                    download_count=random.randint(0, 300),
                ),
            )

    # ------------------------------------------------------------------
    # COMMUNICATIONS
    # ------------------------------------------------------------------
    def _seed_communications(self):
        for _ in range(10):
            Announcement.objects.create(
                title=fake.sentence(nb_words=8),
                content=fake.paragraph(nb_sentences=4),
                announcement_type=random.choice(["system", "course"]),
                priority=random.choice(["low", "normal", "normal", "high"]),
                created_by=random.choice(self.admins),
            )

        for _ in range(5):
            BroadcastMessage.objects.create(
                subject=fake.sentence(nb_words=6),
                message=fake.paragraph(nb_sentences=3),
                filter_type="all_users",
                status="sent",
                created_by=random.choice(self.admins),
                sent_at=past_dt(5, 60),
                recipient_count=random.randint(50, 200),
            )

        notif_types = ["enrollment", "assignment", "grade", "announcement", "message", "certificate"]
        for student in random.sample(self.students, k=min(60, len(self.students))):
            for _ in range(random.randint(1, 4)):
                notif = Notification.objects.create(
                    user=student, notification_type=random.choice(notif_types),
                    title=fake.sentence(nb_words=6),
                    message=fake.sentence(nb_words=15),
                    is_read=random.random() < 0.5,
                )
                backdate(Notification, notif.pk, created_at=past_dt(1, 90))

        for _ in range(40):
            sender = random.choice(self.students)
            recipient = random.choice(self.instructors)
            msg = Message.objects.create(
                sender=sender, recipient=recipient,
                subject=fake.sentence(nb_words=6),
                body=fake.paragraph(nb_sentences=3),
                is_read=random.random() < 0.6,
            )
            backdate(Message, msg.pk, created_at=past_dt(1, 120))

        for _ in range(18):
            cm = ContactMessage.objects.create(
                name=fake.name(), email=fake.email(),
                subject=random.choice(["admissions", "programs", "financial", "support", "other"]),
                message=fake.paragraph(nb_sentences=3),
                is_read=random.random() < 0.7,
                responded=random.random() < 0.5,
            )
            backdate(ContactMessage, cm.pk, created_at=past_dt(1, 180))

    # ------------------------------------------------------------------
    # SUPPORT DESK
    # ------------------------------------------------------------------
    def _seed_support(self):
        departments = []
        for name in ["Technical Support", "Admissions Help", "Billing & Payments", "Academic Records"]:
            dept, _ = SupportDepartment.objects.get_or_create(
                name=name, defaults=dict(description=fake.sentence(), head=random.choice(self.support_staff)),
            )
            dept.members.add(*random.sample(self.support_staff, k=min(2, len(self.support_staff))))
            departments.append(dept)

        sla_policies = {}
        for priority, first, resolve, esc in [("low", 24, 96, 48), ("normal", 8, 48, 24),
                                                ("high", 4, 24, 8), ("urgent", 1, 8, 2)]:
            policy, _ = SLAPolicy.objects.get_or_create(
                priority=priority,
                defaults=dict(name=f"{priority.title()} Priority SLA",
                              first_response_hours=first, resolution_hours=resolve, escalation_hours=esc),
            )
            sla_policies[priority] = policy

        for agent in self.support_staff:
            AgentProfile.objects.get_or_create(
                user=agent,
                defaults=dict(department=random.choice(departments),
                              specializations=fake.sentence(nb_words=6),
                              bio=fake.sentence(), average_rating=Decimal(str(round(random.uniform(3.5, 5.0), 1))),
                              total_resolved=random.randint(10, 200)),
            )

        for i in range(4):
            CannedResponse.objects.get_or_create(
                title=f"Standard Reply {i+1}",
                defaults=dict(category=random.choice(["technical", "account", "course", "payment"]),
                              body=fake.paragraph(nb_sentences=2),
                              created_by=random.choice(self.support_staff)),
            )

        kb_categories = []
        for name in ["Getting Started", "Payments & Billing", "Courses & Enrollment", "Account & Security"]:
            cat, _ = KBCategory.objects.get_or_create(name=name, defaults=dict(description=fake.sentence()))
            kb_categories.append(cat)
        for _ in range(16):
            KBArticle.objects.create(
                category=random.choice(kb_categories),
                title=fake.sentence(nb_words=7),
                summary=fake.sentence(nb_words=15),
                body="\n\n".join(fake.paragraphs(nb=3)),
                status="published",
                author=random.choice(self.support_staff),
                view_count=random.randint(0, 500),
            )

        faq_categories = []
        for name in ["Admissions", "Tuition & Fees", "Technical Issues", "Academics"]:
            cat, _ = FAQCategory.objects.get_or_create(name=name)
            faq_categories.append(cat)
        for _ in range(20):
            FAQ.objects.create(
                category=random.choice(faq_categories),
                question=fake.sentence(nb_words=10) + "?",
                answer=fake.paragraph(nb_sentences=2),
                created_by=random.choice(self.support_staff),
            )

        for _ in range(35):
            requester = random.choice(self.students)
            priority = random.choice(["low", "normal", "normal", "high", "urgent"])
            status = random.choice(["open", "in_progress", "waiting_response", "resolved", "closed"])
            agent = random.choice(self.support_staff)
            ticket = SupportTicket.objects.create(
                user=requester,
                category=random.choice(["technical", "account", "course", "payment", "other"]),
                subject=fake.sentence(nb_words=8),
                description=fake.paragraph(nb_sentences=4),
                priority=priority, status=status, assigned_to=agent,
            )
            backdate(SupportTicket, ticket.pk, created_at=past_dt(1, 200))

            SupportTicketExtra.objects.get_or_create(
                ticket=ticket,
                defaults=dict(department=random.choice(departments), sla_policy=sla_policies[priority],
                              source=random.choice(["portal", "email", "chat"]),
                              first_response_at=past_dt(0, 5) if status != "open" else None,
                              due_at=NOW + timedelta(hours=sla_policies[priority].resolution_hours)),
            )

            for _ in range(random.randint(0, 3)):
                author = random.choice([requester, agent])
                reply = TicketReply.objects.create(
                    ticket=ticket, author=author, message=fake.paragraph(nb_sentences=2),
                    is_internal_note=(author == agent and random.random() < 0.2),
                )
                backdate(TicketReply, reply.pk, created_at=past_dt(0, 190))

            TicketHistory.objects.create(
                ticket=ticket, changed_by=agent, field_name="status",
                old_value="open", new_value=status, note="Status updated",
            )

        for i in range(3):
            SupportAnnouncement.objects.create(
                title=fake.sentence(nb_words=6), body=fake.paragraph(nb_sentences=2),
                is_pinned=(i == 0), created_by=random.choice(self.support_staff),
            )

        for _ in range(10):
            session = SupportChatSession.objects.create(
                student=random.choice(self.students),
                agent=random.choice(self.support_staff),
                status=random.choice(["ended", "active"]),
                subject=fake.sentence(nb_words=6),
                category=random.choice(["technical", "account", "course"]),
                rating=random.randint(3, 5),
                wait_time_seconds=random.randint(10, 300),
                duration_seconds=random.randint(60, 1800),
            )
            for _ in range(random.randint(2, 6)):
                SupportChatMessage.objects.create(
                    session=session,
                    sender=random.choice([session.student, session.agent]),
                    body=fake.sentence(nb_words=12),
                )

        for _ in range(20):
            SupportAuditLog.objects.create(
                actor=random.choice(self.support_staff), action=random.choice(
                    ["ticket_assigned", "ticket_resolved", "kb_article_published", "faq_created"]),
                target_type="SupportTicket", target_id=str(random.randint(1, 100)),
                description=fake.sentence(),
            )

    # ------------------------------------------------------------------
    # COMMUNITY: DISCUSSIONS + STUDY GROUPS
    # ------------------------------------------------------------------
    def _seed_community(self):
        for lms in random.sample(self.lms_courses, k=min(20, len(self.lms_courses))):
            enrolled = list(User.objects.filter(enrollments__course=lms).distinct())
            if not enrolled:
                continue
            for _ in range(random.randint(1, 3)):
                author = random.choice(enrolled)
                discussion = Discussion.objects.create(
                    course=lms, title=fake.sentence(nb_words=8), content=fake.paragraph(nb_sentences=3),
                    author=author, views_count=random.randint(5, 200),
                )
                for _ in range(random.randint(0, 4)):
                    DiscussionReply.objects.create(
                        discussion=discussion, author=random.choice(enrolled + [lms.instructor]),
                        content=fake.sentence(nb_words=20),
                    )

            if random.random() < 0.4:
                group = StudyGroup.objects.create(
                    name=f"{lms.title} Study Circle", description=fake.sentence(nb_words=15),
                    course=lms, created_by=random.choice(enrolled),
                )
                members = random.sample(enrolled, k=min(len(enrolled), random.randint(2, 6)))
                for member in members:
                    StudyGroupMember.objects.get_or_create(
                        study_group=group, user=member,
                        defaults=dict(role="moderator" if member == group.created_by else "member"),
                    )
                for _ in range(random.randint(2, 8)):
                    StudyGroupMessage.objects.create(
                        study_group=group, author=random.choice(members),
                        content=fake.sentence(nb_words=15),
                    )

    # ------------------------------------------------------------------
    # PERMISSIONS + AUDIT LOG
    # ------------------------------------------------------------------
    def _seed_permissions_and_audit(self):
        role_defaults = {
            "admin": dict(can_view=True, can_create=True, can_edit=True, can_delete=True,
                          can_approve=True, can_export=True),
            "instructor": dict(can_view=True, can_create=True, can_edit=True, can_delete=False,
                               can_approve=False, can_export=True),
            "finance": dict(can_view=True, can_create=True, can_edit=True, can_delete=False,
                            can_approve=True, can_export=True),
            "support": dict(can_view=True, can_create=True, can_edit=True, can_delete=False,
                            can_approve=False, can_export=False),
        }
        modules_by_role = {
            "admin": ["dashboard", "user_management", "academics", "lms_courses", "applications",
                      "exams", "enrollments", "finance", "communications", "blog", "library",
                      "site_content", "security_audit", "academic_progression", "results_publish",
                      "role_permissions"],
            "instructor": ["instructor_courses", "instructor_assessments", "instructor_analytics",
                          "instructor_resources", "instructor_communications"],
            "finance": ["finance_payments", "finance_subscriptions", "finance_payroll", "dashboard"],
            "support": ["support_tickets", "support_knowledge_base", "support_communications",
                       "support_analytics", "support_config"],
        }
        for role, modules in modules_by_role.items():
            for module in modules:
                StaffPermissionsMatrix.objects.get_or_create(
                    role=role, module=module, defaults=role_defaults[role],
                )

        actions = ["create", "update", "delete", "login", "logout", "access", "export"]
        all_staff = self.admins + self.finance_staff + self.support_staff + self.instructors
        for _ in range(80):
            log = AuditLog.objects.create(
                user=random.choice(all_staff), action=random.choice(actions),
                model_name=random.choice(["CourseApplication", "Invoice", "Exam", "UserProfile", "BlogPost"]),
                object_id=str(random.randint(1, 200)),
                description=fake.sentence(nb_words=10),
                ip_address=fake.ipv4(),
            )
            backdate(AuditLog, log.pk, timestamp=past_dt(1, 180))

        for _ in range(20):
            log = ProgressionDecisionLog.objects.create(
                student=random.choice(self.students), session=random.choice(self.past_sessions),
                previous_year_of_study=random.randint(1, 3), new_year_of_study=random.randint(2, 4),
                previous_status="active", new_status="active",
                cgpa=Decimal(str(round(random.uniform(1.5, 4.5), 2))),
                core_courses_passed=True, changed_by=random.choice(self.admins),
                note="Automatic end-of-session progression.",
            )
            backdate(ProgressionDecisionLog, log.pk, created_at=past_dt(30, 300))

        for program in random.sample(self.programs, k=min(6, len(self.programs))):
            ProgramSessionCreditCap.objects.get_or_create(
                program=program, session=self.current_session, term="first",
                defaults=dict(max_credit_units=21, updated_by=random.choice(self.admins)),
            )

    # ------------------------------------------------------------------
    # BADGES
    # ------------------------------------------------------------------
    def _award_badges(self):
        for student in self.students:
            check_and_award_badges(student)

    # ------------------------------------------------------------------
    def _print_summary(self):
        from django.apps import apps
        self.stdout.write("\n--- Row counts ---")
        for label, app_label in [("eduweb", "eduweb"), ("support", "support"), ("chatbot", "chatbot")]:
            for model in apps.get_app_config(app_label).get_models():
                count = model.objects.count()
                if count:
                    self.stdout.write(f"{app_label}.{model.__name__}: {count}")
