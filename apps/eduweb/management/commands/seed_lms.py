"""
Seed the learning content (LMS courses, sections, lessons) and the
Admissions FAQs for the six AbrayTech Academy programmes.

Source of truth: the "COURSE CONTENTS" section of
"AbrayTech Website Content Development.docx", already loaded into
`eduweb.Course` rows by `seed_courses` (each Course = one month of a
programme; its description is an outline of "Module N: Title" headings with
comma-separated topics, plus a "Capstone: Title" entry).

For every Course this command creates:
  - one LMSCourse (published, linked to the Course via academic_course)
  - one LessonSection per module (and one for the capstone)
  - one Lesson per topic group. Lessons are video-type placeholders with
    the topic as title and the module as description; the capstone is an
    assignment lesson carrying the docx capstone brief.

It also creates the "Admissions" FAQ category and its FAQs, which the
Admission Requirements page reads from the backend.

What is left for you: thumbnails, promo/lesson videos, instructors.

Safe to re-run: it only CREATES what is missing. Existing courses, lessons,
videos, thumbnails and edited text are never overwritten. If no Course rows
exist yet it runs `seed_courses` first.

Text is kept ASCII-only on purpose (the MySQL database has rejected
non-ASCII seed text before, see seed_courses).

MySQL / transactions: the whole run is one transaction.atomic() block, so a
failure part-way rolls back every course, section, lesson and FAQ it had
created (InnoDB; these are plain INSERTs, no DDL). Lessons are inserted with
bulk_create(batch_size=200) to stay under max_allowed_packet. bulk_create
skips Lesson.save()/clean(), which is fine here: slugs are set explicitly and
Lesson has no signals. Note Lesson.clean() requires a video URL or file for
video-type lessons, so a placeholder can only be saved from the admin/forms
once its video has been added.

Usage:
    python manage.py seed_lms
"""

import re

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.eduweb.models import Course, LMSCourse, Lesson, LessonSection
from apps.support.models import FAQ, FAQCategory

# Longest topic that counts as "short" and may be grouped with its
# neighbours into one lesson (e.g. "for, while, range()" -> one lesson).
SHORT_TOPIC_CHARS = 14
MAX_TOPICS_PER_LESSON = 4

_ASCII_MAP = {
    "–": "-", "—": "-", "‘": "'", "’": "'",
    "“": '"', "”": '"', "…": "...", " ": " ",
    "→": "to",
}

ADMISSIONS_FAQS = [
    (
        "What is the application fee?",
        "The application fee varies by programme. You will see the exact amount on the "
        "programme's page before you apply, and you pay it securely online as part of your application.",
    ),
    (
        "Can I apply to more than one programme?",
        "Yes. Each programme needs its own application and application fee, since each is reviewed separately.",
    ),
    (
        "Is there an application deadline?",
        "Admissions are rolling. You can apply at any time, and we review complete applications as they come in.",
    ),
    (
        "What happens after I am accepted?",
        "Accept your offer in the student portal and you will get access to your programme's courses.",
    ),
    (
        "Is coursework live or self-paced?",
        "Courses are self-paced. Once you are enrolled, there is no term or semester limit on when you "
        "complete a course. Work through the material on your own schedule.",
    ),
    (
        "Do I get a certificate when I finish?",
        "Yes. Once you complete all of a programme's core courses, a completion certificate is issued to your account.",
    ),
]


def ascii_text(value):
    """Replace common typographic characters, then drop anything non-ASCII."""
    for char, replacement in _ASCII_MAP.items():
        value = value.replace(char, replacement)
    return value.encode("ascii", "ignore").decode("ascii").strip()


def split_topics(text):
    """Split a comma-separated topic list without breaking inside brackets."""
    topics, depth, current = [], 0, []
    for char in text:
        if char in "([":
            depth += 1
        elif char in ")]":
            depth = max(depth - 1, 0)
        if char == "," and depth == 0:
            topics.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    topics.append("".join(current).strip())
    return [topic for topic in topics if topic]


def group_topics(topics):
    """One lesson per topic, except runs of very short topics share a lesson."""
    lessons = []
    for topic in topics:
        is_short = len(topic) <= SHORT_TOPIC_CHARS
        if lessons and is_short and lessons[-1]["short"] and len(lessons[-1]["topics"]) < MAX_TOPICS_PER_LESSON:
            lessons[-1]["topics"].append(topic)
        else:
            lessons.append({"topics": [topic], "short": is_short})
    return [", ".join(lesson["topics"]) for lesson in lessons]


def lesson_title(text):
    title = text[0].upper() + text[1:] if text else text
    return title if len(title) <= 200 else title[:197] + "..."


def unique_slug_in(taken, text):
    base = slugify(text)[:180] or "lesson"
    slug, counter = base, 2
    while slug in taken:
        slug = f"{base}-{counter}"
        counter += 1
    taken.add(slug)
    return slug


class Command(BaseCommand):
    help = "Create LMS courses, sections, lessons and Admissions FAQs from the seeded academy courses."

    def handle(self, *args, **options):
        if not Course.objects.exists():
            self.stdout.write("No academic courses found - running seed_courses first.")
            call_command("seed_courses")

        stats = {"courses": 0, "sections": 0, "lessons": 0}
        with transaction.atomic():
            first_of_program = set()
            courses = Course.objects.select_related("program").order_by("program_id", "code")
            for course in courses:
                make_preview = course.program_id not in first_of_program
                first_of_program.add(course.program_id)
                self._seed_course(course, make_preview, stats)
            faqs_created = self._seed_faqs()

        self.stdout.write(self.style.SUCCESS(
            f"LMS courses created: {stats['courses']} | sections: {stats['sections']} | "
            f"lessons: {stats['lessons']} | admissions FAQs created: {faqs_created}"
        ))

    def _seed_course(self, course, make_preview, stats):
        sections = course.scheme_of_work
        # The first block is the month's intro sentence (a header with no items).
        intro = ""
        if sections and not sections[0]["items"]:
            intro = ascii_text(sections.pop(0)["header"])
        modules = [
            (ascii_text(block["header"]), [ascii_text(item) for item in block["items"]])
            for block in sections
        ]

        lms_course = LMSCourse.objects.filter(academic_course=course).first()
        if lms_course is None:
            objectives = [
                re.sub(r"^Module \d+:\s*", "", title) if not title.startswith("Capstone")
                else "Complete the capstone: " + title.split(":", 1)[-1].strip()
                for title, _ in modules
            ]
            module_list = "\n".join(f"- {title}" for title, _ in modules)
            lms_course = LMSCourse.objects.create(
                title=ascii_text(course.name),
                slug=self._course_slug(course),
                code=course.code[:20],
                short_description=(intro or ascii_text(course.name))[:500],
                description=f"{intro}\n\n{module_list}".strip(),
                learning_objectives=objectives,
                academic_course=course,
                is_published=True,
                published_at=timezone.now(),
                meta_description=(intro or ascii_text(course.name))[:160],
            )
            stats["courses"] += 1

        taken_lesson_slugs = set(lms_course.lessons.values_list("slug", flat=True))
        new_lessons = []

        for order, (title, lines) in enumerate(modules, start=1):
            section_slug = slugify(title)[:180] or f"section-{order}"
            section = lms_course.sections.filter(slug=section_slug).first()
            if section is None:
                section = LessonSection.objects.create(
                    course=lms_course, title=title[:200], slug=section_slug, display_order=order,
                )
                stats["sections"] += 1

            if section.lessons.exists():
                continue  # never touch a section that already has lessons

            body = " ".join(re.sub(r"^\d+\.\d+\s+", "", line) for line in lines)
            if title.startswith("Capstone"):
                lesson_texts = [(title, body, "assignment")]
            else:
                lesson_texts = [(lesson_title(topic), title, "video") for topic in group_topics(split_topics(body))]

            for position, (lesson_name, description, lesson_type) in enumerate(lesson_texts, start=1):
                new_lessons.append(Lesson(
                    course=lms_course,
                    section=section,
                    title=lesson_name,
                    slug=unique_slug_in(taken_lesson_slugs, lesson_name),
                    lesson_type=lesson_type,
                    description=description if lesson_type == "video" else "",
                    content=description if lesson_type == "assignment" else "",
                    is_preview=make_preview and order == 1 and position == 1,
                    display_order=position,
                ))

        if new_lessons:
            # Batched so no single INSERT can exceed MySQL's max_allowed_packet.
            Lesson.objects.bulk_create(new_lessons, batch_size=200)
            stats["lessons"] += len(new_lessons)

    @staticmethod
    def _course_slug(course):
        base = slugify(f"{course.program.name} {course.name}")[:190]
        slug, counter = base, 2
        while LMSCourse.objects.filter(slug=slug).exists():
            slug = f"{base}-{counter}"
            counter += 1
        return slug

    @staticmethod
    def _seed_faqs():
        category, _ = FAQCategory.objects.get_or_create(name="Admissions", defaults={"order": 1})
        created = 0
        for order, (question, answer) in enumerate(ADMISSIONS_FAQS, start=1):
            _, was_created = FAQ.objects.get_or_create(
                category=category, question=question, defaults={"answer": answer, "order": order},
            )
            created += was_created
        return created
