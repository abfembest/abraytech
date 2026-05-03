"""
Management command: seed_lms_content
=====================================
Place this file at:
    <your_app>/management/commands/seed_lms_content.py

Run with:
    python manage.py seed_lms_content

What it does
────────────
1. Reads every existing Course from the database.
2. For each Course (up to the first 4 to keep things reasonable), creates
   one LMSCourse linked to it — skips if one already exists for that Course.
3. For each LMSCourse (new or pre-existing) adds:
   • 3 LessonSections
   • 5 Lessons spread across the sections (text lessons — no file uploads needed)
   • 1 Assignment attached to the last lesson of each section
   • 1 Exam (DRAFT) with 5 MCQ questions
4. Assigns the first available instructor-role user as lecturer/instructor
   on every LMSCourse it creates or updates.

Safety
──────
• Never clears existing data.
• Uses get_or_create / exists() checks throughout.
• Skips LMSCourses that already have 3+ sections to avoid duplication on
  repeated runs.
• All DB writes are wrapped in a single transaction — rolls back cleanly
  on any error.
"""

import uuid
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify


# ── lazy imports so the command works even if app label differs ──────────────
def _models():
    from eduweb.models import (
        Assignment,
        Course,
        Exam,
        ExamQuestion,
        LessonSection,
        Lesson,
        LMSCourse,
        UserProfile,
    )
    return Course, LMSCourse, LessonSection, Lesson, Assignment, Exam, ExamQuestion, UserProfile


# ── helpers ──────────────────────────────────────────────────────────────────

def _unique_slug(model, base, field='slug'):
    """Return a slug that does not already exist in `model`."""
    slug = slugify(base)[:180]
    original = slug
    counter = 1
    while model.objects.filter(**{field: slug}).exists():
        slug = f"{original}-{counter}"
        counter += 1
    return slug


def _get_instructor():
    """Return the first active User whose profile role is 'instructor', or None."""
    try:
        from eduweb.models import UserProfile
        profile = (
            UserProfile.objects
            .filter(role='instructor', user__is_active=True)
            .select_related('user')
            .first()
        )
        return profile.user if profile else None
    except Exception:
        return None


# ── per-course seed data ──────────────────────────────────────────────────────

SECTION_TEMPLATES = [
    {
        "title": "Introduction & Foundations",
        "description": "Core concepts, terminology, and the theoretical basis of the subject.",
        "lessons": [
            {
                "title": "Course Overview and Learning Objectives",
                "lesson_type": "text",
                "is_preview": True,
                "description": "An orientation to the course structure, assessment methods, and expected outcomes.",
                "content": (
                    "<h2>Welcome</h2>"
                    "<p>This lesson introduces the course, outlines learning objectives, "
                    "and explains how assessments are structured. By the end you will "
                    "understand what to expect and how to succeed.</p>"
                    "<h3>Learning Objectives</h3>"
                    "<ul>"
                    "<li>Understand the scope and structure of this course</li>"
                    "<li>Identify the key themes covered each week</li>"
                    "<li>Know how assignments and exams contribute to your final grade</li>"
                    "</ul>"
                ),
                "video_duration_minutes": 0,
                "display_order": 1,
            },
            {
                "title": "Fundamental Concepts and Definitions",
                "lesson_type": "text",
                "is_preview": False,
                "description": "Key definitions, terminology, and foundational principles.",
                "content": (
                    "<h2>Core Terminology</h2>"
                    "<p>Before progressing, it is essential to establish a shared vocabulary. "
                    "The definitions introduced here will be used throughout the course.</p>"
                    "<h3>Key Terms</h3>"
                    "<p>Each term is explained in plain language with a worked example "
                    "drawn from real-world scenarios to aid retention.</p>"
                    "<blockquote>Clarity of concept is the first step to mastery.</blockquote>"
                ),
                "video_duration_minutes": 0,
                "display_order": 2,
            },
        ],
        "assignment": {
            "title": "Reflection: Foundations",
            "description": "Demonstrate your understanding of the introductory material.",
            "instructions": (
                "Write a 300–500 word reflection addressing the following:\n"
                "1. Summarise the two most important concepts from this section.\n"
                "2. Explain how each concept applies to a real-world situation.\n"
                "3. Identify one question you still have after completing the lessons.\n\n"
                "Submit as a single PDF or Word document."
            ),
            "max_score": 20.00,
            "passing_score": 10.00,
            "days_until_due": 7,
        },
    },
    {
        "title": "Core Principles and Methods",
        "description": "Deep dive into the principal methods, frameworks, and analytical approaches.",
        "lessons": [
            {
                "title": "Theoretical Frameworks",
                "lesson_type": "text",
                "is_preview": False,
                "description": "Major theoretical frameworks that underpin the subject area.",
                "content": (
                    "<h2>Theoretical Frameworks</h2>"
                    "<p>Understanding the theoretical underpinning of a discipline allows "
                    "practitioners to make principled decisions rather than relying solely "
                    "on intuition.</p>"
                    "<h3>Framework 1 — Structural Analysis</h3>"
                    "<p>Examines how components of a system interact and constrain each other.</p>"
                    "<h3>Framework 2 — Process Modelling</h3>"
                    "<p>Focuses on sequences of operations and how inputs are transformed "
                    "into outputs over time.</p>"
                ),
                "video_duration_minutes": 0,
                "display_order": 1,
            },
            {
                "title": "Practical Methods and Tools",
                "lesson_type": "text",
                "is_preview": False,
                "description": "Hands-on methods and standard tools used by practitioners.",
                "content": (
                    "<h2>Methods in Practice</h2>"
                    "<p>Theory gains its value when applied. This lesson covers the most "
                    "widely used methods in professional and academic settings.</p>"
                    "<h3>Step-by-Step Approach</h3>"
                    "<ol>"
                    "<li>Define the problem clearly before choosing a method.</li>"
                    "<li>Select appropriate tools based on the nature of the data.</li>"
                    "<li>Apply the method systematically, documenting each step.</li>"
                    "<li>Validate results against known benchmarks where possible.</li>"
                    "</ol>"
                ),
                "video_duration_minutes": 0,
                "display_order": 2,
            },
        ],
        "assignment": {
            "title": "Case Study Analysis",
            "description": "Apply the frameworks studied in this section to a real scenario.",
            "instructions": (
                "Select ONE of the following case study prompts:\n"
                "A) Analyse the structural components of a system relevant to this course.\n"
                "B) Model a real-world process using the process-modelling framework.\n\n"
                "Your analysis should:\n"
                "• Be 600–900 words\n"
                "• Reference at least two concepts from Section 2 lessons\n"
                "• Include a brief conclusion with recommendations\n\n"
                "Submit as PDF."
            ),
            "max_score": 30.00,
            "passing_score": 15.00,
            "days_until_due": 10,
        },
    },
    {
        "title": "Advanced Topics and Applications",
        "description": "Advanced concepts, current research directions, and applied problem-solving.",
        "lessons": [
            {
                "title": "Advanced Topics Overview",
                "lesson_type": "text",
                "is_preview": False,
                "description": "Survey of advanced topics extending beyond foundational knowledge.",
                "content": (
                    "<h2>Going Further</h2>"
                    "<p>Having mastered the fundamentals, this section explores areas that "
                    "are actively researched and applied at an advanced level.</p>"
                    "<h3>Topics Covered</h3>"
                    "<ul>"
                    "<li>Emerging trends and their implications</li>"
                    "<li>Complex problem decomposition</li>"
                    "<li>Cross-disciplinary applications</li>"
                    "</ul>"
                    "<p>Each sub-topic is introduced with a motivating example before "
                    "proceeding to formal treatment.</p>"
                ),
                "video_duration_minutes": 0,
                "display_order": 1,
            },
        ],
        "assignment": {
            "title": "Final Project Proposal",
            "description": "Propose and outline a mini-project that applies course knowledge.",
            "instructions": (
                "Submit a project proposal (400–600 words) that:\n"
                "1. Clearly states the problem or question your project addresses.\n"
                "2. Identifies which course concepts and methods will be applied.\n"
                "3. Outlines a realistic timeline and deliverables.\n"
                "4. Lists any resources or data sources you plan to use.\n\n"
                "This proposal will form the basis of your end-of-course submission."
            ),
            "max_score": 50.00,
            "passing_score": 25.00,
            "days_until_due": 14,
        },
    },
]


def _exam_questions_for(course_title):
    """Return 5 MCQ question dicts tailored to a course title."""
    cname = course_title
    questions = [
        {
            "question_text": f"Which of the following best describes the primary purpose of {cname}?",
            "question_type": "mcq",
            "marks": 2,
            "options": [
                {"id": str(uuid.uuid4()), "text": "To memorise isolated facts without application", "is_correct": False},
                {"id": str(uuid.uuid4()), "text": "To develop structured understanding and practical skill", "is_correct": True},
                {"id": str(uuid.uuid4()), "text": "To replace the need for practical experience entirely", "is_correct": False},
                {"id": str(uuid.uuid4()), "text": "To focus solely on historical developments", "is_correct": False},
            ],
            "explanation": "The primary purpose is to develop structured understanding alongside practical skill.",
            "tags": ["general", "overview"],
        },
        {
            "question_text": "Which approach is MOST effective when encountering a new problem in this subject area?",
            "question_type": "mcq",
            "marks": 2,
            "options": [
                {"id": str(uuid.uuid4()), "text": "Apply the first method that comes to mind", "is_correct": False},
                {"id": str(uuid.uuid4()), "text": "Ignore available frameworks and rely purely on intuition", "is_correct": False},
                {"id": str(uuid.uuid4()), "text": "Define the problem clearly, then select an appropriate framework", "is_correct": True},
                {"id": str(uuid.uuid4()), "text": "Delegate the problem to someone else immediately", "is_correct": False},
            ],
            "explanation": "Problem definition precedes method selection — a core principle of structured analysis.",
            "tags": ["methodology", "critical-thinking"],
        },
        {
            "question_text": "True or False: Theoretical frameworks are only useful for academic purposes and have no practical application.",
            "question_type": "true_false",
            "marks": 1,
            "options": [
                {"id": str(uuid.uuid4()), "text": "True", "is_correct": False},
                {"id": str(uuid.uuid4()), "text": "False", "is_correct": True},
            ],
            "explanation": "Theoretical frameworks directly inform practical decision-making and professional practice.",
            "tags": ["theory", "application"],
        },
        {
            "question_text": "Which of the following is a characteristic of a well-defined learning objective?",
            "question_type": "mcq",
            "marks": 2,
            "options": [
                {"id": str(uuid.uuid4()), "text": "It is vague to allow flexibility in interpretation", "is_correct": False},
                {"id": str(uuid.uuid4()), "text": "It is measurable, specific, and achievable within the course duration", "is_correct": True},
                {"id": str(uuid.uuid4()), "text": "It focuses only on rote memorisation", "is_correct": False},
                {"id": str(uuid.uuid4()), "text": "It does not reference assessment criteria", "is_correct": False},
            ],
            "explanation": "Good learning objectives are SMART: Specific, Measurable, Achievable, Relevant, Time-bound.",
            "tags": ["pedagogy", "objectives"],
        },
        {
            "question_text": "When validating the results of an analysis, the BEST practice is to:",
            "question_type": "mcq",
            "marks": 3,
            "options": [
                {"id": str(uuid.uuid4()), "text": "Accept results without question if the method was correctly applied", "is_correct": False},
                {"id": str(uuid.uuid4()), "text": "Cross-check against known benchmarks or independent sources where possible", "is_correct": True},
                {"id": str(uuid.uuid4()), "text": "Discard results that do not match expectations", "is_correct": False},
                {"id": str(uuid.uuid4()), "text": "Report only the results that support the original hypothesis", "is_correct": False},
            ],
            "explanation": "Validation against benchmarks ensures reliability and guards against systematic errors.",
            "tags": ["validation", "methodology"],
        },
    ]
    return questions


# ── main seeder functions ─────────────────────────────────────────────────────

def seed_lms_course(course, instructor, log):
    """Create (or retrieve) an LMSCourse for the given academic Course."""
    Course, LMSCourse, LessonSection, Lesson, Assignment, Exam, ExamQuestion, UserProfile = _models()

    # Skip if an LMSCourse already exists for this academic course
    existing = LMSCourse.objects.filter(academic_course=course).first()
    if existing:
        log(f"  ↳ LMSCourse already exists for '{course}' — updating instructor if needed")
        lms = existing
        changed = False
        if instructor and lms.instructor_id != instructor.id:
            lms.instructor = instructor
            lms.lecturer = instructor
            changed = True
        if not lms.is_published:
            lms.is_published = True
            changed = True
        if changed:
            lms.save()
        return lms, False  # (lms, created)

    code = f"LMS-{course.code}"[:20]
    if LMSCourse.objects.filter(code=code).exists():
        code = f"LMS-{course.code}-{course.id}"[:20]

    title = f"{course.name} — Online Delivery"
    slug = _unique_slug(LMSCourse, title)

    lms = LMSCourse.objects.create(
        title=title,
        slug=slug,
        code=code,
        short_description=(
            f"The online delivery of {course.name} ({course.code}). "
            f"Covers all topics in the {course.get_semester_display()} curriculum "
            f"for Year {course.year_of_study} students."
        ),
        description=(
            f"This LMS course provides structured digital content for the academic unit "
            f"'{course.name}' ({course.code}), a {course.get_course_type_display()} course "
            f"carrying {course.credit_units} credit unit(s). "
            f"Students progress through video lectures, readings, assignments, and a "
            f"formal end-of-semester exam delivered via the CBT platform."
        ),
        learning_objectives=[
            f"Understand and apply the foundational principles of {course.name}",
            "Critically analyse case studies using frameworks introduced in the course",
            "Demonstrate competence through assessed assignments and the end-of-term exam",
            "Develop independent research and problem-solving skills in this subject area",
        ],
        prerequisites=(
            [f"Completion of prerequisite courses for {course.code}"]
            if course.prerequisites.exists()
            else []
        ),
        academic_course=course,
        difficulty_level=course.year_of_study * 100,
        instructor=instructor,
        lecturer=instructor,
        is_published=True,
        meta_description=f"Online delivery of {course.name} for Year {course.year_of_study} students.",
        meta_keywords=f"{course.code}, {course.name}, LMS, online learning",
    )
    log(f"  ✔ Created LMSCourse: {lms.title}")
    return lms, True


def seed_sections_and_lessons(lms, log):
    """Add 3 sections with 5 total lessons if the course doesn't already have them."""
    Course, LMSCourse, LessonSection, Lesson, Assignment, Exam, ExamQuestion, UserProfile = _models()

    if lms.sections.count() >= 3:
        log(f"  ↳ Sections already exist for '{lms.title}' — skipping")
        return

    now = timezone.now()

    for sec_order, sec_data in enumerate(SECTION_TEMPLATES, start=1):
        sec_slug = _unique_slug(LessonSection, sec_data["title"])
        # unique_together is (course, slug) so check scoped
        while LessonSection.objects.filter(course=lms, slug=sec_slug).exists():
            sec_slug = f"{sec_slug}-{sec_order}"

        section = LessonSection.objects.create(
            course=lms,
            title=sec_data["title"],
            slug=sec_slug,
            description=sec_data["description"],
            display_order=sec_order,
            is_active=True,
        )
        log(f"    § Section {sec_order}: {section.title}")

        last_lesson = None
        for lesson_data in sec_data["lessons"]:
            lesson_slug_base = f"{lms.slug[:60]}-{slugify(lesson_data['title'])[:60]}"
            lesson_slug = lesson_slug_base[:200]
            counter = 1
            while Lesson.objects.filter(course=lms, slug=lesson_slug).exists():
                lesson_slug = f"{lesson_slug_base[:190]}-{counter}"
                counter += 1

            lesson = Lesson.objects.create(
                course=lms,
                section=section,
                title=lesson_data["title"],
                slug=lesson_slug,
                lesson_type=lesson_data["lesson_type"],
                description=lesson_data["description"],
                content=lesson_data["content"],
                is_preview=lesson_data["is_preview"],
                video_duration_minutes=lesson_data["video_duration_minutes"],
                display_order=lesson_data["display_order"],
                is_active=True,
            )
            last_lesson = lesson
            log(f"      ✔ Lesson: {lesson.title}")

        # ── Assignment on the last lesson of this section ────────────────────
        if last_lesson:
            asgn_data = sec_data["assignment"]
            asgn_slug_base = slugify(asgn_data["title"])[:180]
            asgn_slug = asgn_slug_base
            counter = 1
            while Assignment.objects.filter(lesson=last_lesson, slug=asgn_slug).exists():
                asgn_slug = f"{asgn_slug_base}-{counter}"
                counter += 1

            Assignment.objects.create(
                lesson=last_lesson,
                title=asgn_data["title"],
                slug=asgn_slug,
                description=asgn_data["description"],
                instructions=asgn_data["instructions"],
                max_score=asgn_data["max_score"],
                passing_score=asgn_data["passing_score"],
                due_date=now + timedelta(days=asgn_data["days_until_due"]),
                allow_late_submission=True,
                late_penalty_percent=10,
                is_active=True,
                display_order=1,
            )
            log(f"      ✔ Assignment: {asgn_data['title']}")


def seed_exam(lms, instructor, log):
    """Create one DRAFT end-of-semester exam with 5 questions if none exists."""
    Course, LMSCourse, LessonSection, Lesson, Assignment, Exam, ExamQuestion, UserProfile = _models()

    if lms.exams.exists():
        log(f"  ↳ Exam already exists for '{lms.title}' — skipping")
        return

    now = timezone.now()
    # Schedule exam 30 days from now, 2 hours duration
    start_dt = now + timedelta(days=30)
    start_dt = start_dt.replace(hour=9, minute=0, second=0, microsecond=0)
    end_dt = start_dt + timedelta(hours=2)

    ref_base = f"EX-{now.year}-{lms.id:04d}"
    ref_code = ref_base[:40]

    title = f"{lms.title} — End-of-Semester Exam"
    slug = _unique_slug(Exam, slugify(title)[:200])

    exam = Exam.objects.create(
        slug=slug,
        reference_code=ref_code,
        title=title,
        description=f"End-of-semester CBT examination for the LMS course: {lms.title}.",
        exam_type=Exam.END_OF_SEMESTER,
        course=lms,
        instructor=instructor,
        start_datetime=start_dt,
        end_datetime=end_dt,
        questions_per_student=5,
        shuffle_questions=True,
        shuffle_options=True,
        total_marks=10.00,
        pass_mark=5.00,
        show_result_immediately=False,
        status=Exam.DRAFT,
        instructions=(
            "Read each question carefully before selecting your answer. "
            "You have 2 hours to complete this examination. "
            "All questions carry equal marks unless stated otherwise. "
            "Do not close your browser tab during the exam."
        ),
        created_by=instructor,
        is_active=True,
    )
    log(f"  ✔ Created Exam: {exam.title}")

    # ── 5 questions ──────────────────────────────────────────────────────────
    for q_data in _exam_questions_for(lms.academic_course.name if lms.academic_course else lms.title):
        q_slug_base = slugify(q_data["question_text"][:100])
        q_slug = _unique_slug(ExamQuestion, q_slug_base, field='slug')

        ExamQuestion.objects.create(
            exam=exam,
            slug=q_slug,
            question_text=q_data["question_text"],
            question_type=q_data["question_type"],
            marks=q_data["marks"],
            options=q_data["options"],
            explanation=q_data["explanation"],
            tags=q_data["tags"],
            is_active=True,
        )

    log(f"    ✔ Added {lms.exams.first().questions.count()} exam questions")


# ── command ──────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = "Seed LMS course content (sections, lessons, assignments, exams) for existing academic courses."

    def handle(self, *args, **options):
        Course, LMSCourse, LessonSection, Lesson, Assignment, Exam, ExamQuestion, UserProfile = _models()

        def log(msg):
            self.stdout.write(msg)

        log("\n══════════════════════════════════════════════")
        log("  LMS Content Seeder")
        log("══════════════════════════════════════════════\n")

        instructor = _get_instructor()
        if instructor:
            log(f"Instructor found: {instructor.get_full_name() or instructor.username} ({instructor.email})\n")
        else:
            log("⚠  No instructor-role user found. LMSCourses will be created without an instructor assigned.\n")

        # Take up to 4 academic courses to keep the seed manageable
        courses = list(Course.objects.filter(is_active=True).select_related('program')[:4])

        if not courses:
            log("⚠  No active Course records found. Create some academic courses first.")
            return

        log(f"Found {len(courses)} active course(s) to process.\n")

        try:
            with transaction.atomic():
                for course in courses:
                    log(f"▶ Processing: {course}")

                    lms, created = seed_lms_course(course, instructor, log)
                    seed_sections_and_lessons(lms, log)
                    seed_exam(lms, instructor, log)

                    log("")

        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"\n✖ Seed failed and was rolled back.\nError: {exc}"))
            raise

        log("══════════════════════════════════════════════")
        log(self.style.SUCCESS("  ✔ Seed completed successfully."))
        log("══════════════════════════════════════════════\n")

        # ── Summary ──────────────────────────────────────────────────────────
        log(f"LMS Courses  : {LMSCourse.objects.count()}")
        log(f"Sections     : {LessonSection.objects.count()}")
        log(f"Lessons      : {Lesson.objects.count()}")
        log(f"Assignments  : {Assignment.objects.count()}")
        log(f"Exams        : {Exam.objects.count()}")
        log(f"Questions    : {ExamQuestion.objects.count()}\n")