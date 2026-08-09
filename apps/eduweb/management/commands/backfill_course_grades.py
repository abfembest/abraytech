"""
One-time backfill for CourseGrade rows created before the exam-aware
recompute existed. Re-runs CourseGrade.recompute_for_student_course for
every existing (student, course, session, term) grade, pulling in exam
data that the old exam-blind logic never considered.

Safe to run repeatedly — recompute_for_student_course always upserts from
live data, so re-running this against already-correct rows is a no-op.
"""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.eduweb.models import AcademicSession, Course, CourseGrade


class Command(BaseCommand):
    help = 'Recomputes every existing CourseGrade row from live exam/quiz/assignment data.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would change without saving anything.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        keys = list(
            CourseGrade.objects.values_list('student_id', 'course_id', 'session_id', 'term').distinct()
        )
        self.stdout.write(f'Found {len(keys)} distinct (student, course, session, term) grade rows to recheck.')

        updated = 0
        unchanged = 0
        skipped_no_enrollment = 0

        for student_id, course_id, session_id, term in keys:
            before_row = CourseGrade.objects.filter(
                student_id=student_id, course_id=course_id, session_id=session_id, term=term,
            ).values('score', 'grade', 'is_passed').first()
            before = {
                'score': float(before_row['score']) if before_row['score'] is not None else None,
                'grade': before_row['grade'],
                'is_passed': before_row['is_passed'],
            }

            result = self._recompute(student_id, course_id, session_id, term, dry_run=dry_run)

            if result is None:
                skipped_no_enrollment += 1
                continue

            after = {
                'score': float(result.score) if result.score is not None else None,
                'grade': result.grade,
                'is_passed': result.is_passed,
            }
            if before != after:
                updated += 1
                self.stdout.write(
                    f'  changed: student={student_id} course={course_id} session={session_id} '
                    f'term={term or "(none)"}: {before} -> {after}'
                )
            else:
                unchanged += 1

        self.stdout.write(self.style.SUCCESS(
            f'{"[DRY RUN] " if dry_run else ""}Done. '
            f'{updated} changed, {unchanged} unchanged, {skipped_no_enrollment} skipped (no active enrollment).'
        ))

    def _recompute(self, student_id, course_id, session_id, term, dry_run=False):
        """
        Resolve ids to instances and call recompute_for_student_course.
        In --dry-run mode, runs the exact same recompute inside a savepoint
        that's always rolled back, so the preview reflects real logic
        (not a hand-duplicated read-only copy of it) without persisting.
        """
        student = User.objects.get(pk=student_id)
        course = Course.objects.get(pk=course_id)
        session = AcademicSession.objects.get(pk=session_id)

        if not dry_run:
            return CourseGrade.recompute_for_student_course(student, course, session, term=term)

        with transaction.atomic():
            result = CourseGrade.recompute_for_student_course(student, course, session, term=term)
            # Detach the result from the rolled-back transaction's row state
            # so its already-evaluated fields remain readable after rollback.
            if result is not None:
                result = CourseGrade(
                    score=result.score, grade=result.grade, is_passed=result.is_passed,
                )
            transaction.set_rollback(True)
        return result
