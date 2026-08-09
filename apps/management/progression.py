"""
management/progression.py

End-of-session student progression + carry-over decision logic.

Kept separate from views.py (already ~5,700 lines) because the
computation has real branching logic that benefits from being
testable in isolation, and the admin-facing preview step needs to run
the exact same computation with zero side effects before a separate
confirm step persists anything.

Two entry points:
  compute_progression_decision(profile, program, session) -> dict
      Pure computation, no DB writes. Used for both preview and confirm.
  apply_progression_decision(decision, admin_user) -> ProgressionDecisionLog
      Persists the decision: UserProfile fields, CourseCarryOver rows,
      one immutable ProgressionDecisionLog row, and a notification.
"""
import math

from apps.eduweb.models import Course, CourseGrade, CourseRegistration, CourseCarryOver, ProgressionDecisionLog


def compute_cgpa(user):
    """
    Cumulative GPA for this user. Thin wrapper around the canonical
    CourseGrade.compute_cgpa — kept here so existing callers of
    management.progression.compute_cgpa don't need to change, but the
    dashboard and Academic Records now call the same underlying model
    method directly, so all three can never disagree.
    """
    return CourseGrade.compute_cgpa(user)


def already_processed_student_ids(session, user_ids):
    """
    Student IDs that already have a ProgressionDecisionLog for this
    session — used to skip double-processing on a resubmitted confirm
    POST (double-click, back-button resubmit) since progression_status
    alone can't tell "not yet run" apart from "just ran".
    """
    return set(
        ProgressionDecisionLog.objects.filter(session=session, student_id__in=list(user_ids))
        .values_list('student_id', flat=True)
    )


def compute_progression_decision(profile, program, session):
    """
    Pure computation — no DB writes. Returns a dict describing what
    would happen to this student if the decision were applied for the
    given (program, session).
    """
    current_level_courses = list(
        Course.objects.filter(program=program, year_of_study=profile.year_of_study, is_active=True)
    )
    core_courses = [c for c in current_level_courses if c.course_type == 'core']

    # result_status='released' — progression must reflect approved,
    # published results only; an un-released grade (still pending registrar
    # sign-off) can't count toward a promotion decision.
    core_passed = all(
        CourseGrade.objects.filter(
            student=profile.user, course=c, is_passed=True, result_status='released',
        ).exists()
        for c in core_courses
    )

    cgpa = compute_cgpa(profile.user)
    cgpa_ok = cgpa is not None and cgpa >= program.min_cgpa_to_progress

    # A course counts as "failed this run" if either (a) the student registered
    # for it this session and didn't pass, or (b) it's still an open carry-over
    # from a prior session — (b) closes the loophole where a student dodges
    # probation/withdrawal indefinitely by simply not re-registering for a
    # course they've already failed.
    prior_attempts = {}
    failed_courses = []
    for course in current_level_courses:
        passed = CourseGrade.objects.filter(
            student=profile.user, course=course, is_passed=True, result_status='released',
        ).exists()
        if passed:
            continue
        registered = CourseRegistration.objects.filter(
            student=profile.user, course=course, session=session,
            status__in=['pending', 'approved'],
        ).exists()
        existing = CourseCarryOver.objects.filter(student=profile.user, course=course, is_cleared=False).first()
        if not registered and not existing:
            continue
        failed_courses.append(course)
        prior_attempts[course.id] = existing.attempts if existing else 0

    promote = core_passed and cgpa_ok
    previous_year_of_study = profile.year_of_study
    previous_status = profile.progression_status
    max_level = math.ceil(float(program.duration_years))

    if promote:
        if previous_year_of_study >= max_level:
            new_status = 'graduated'
            new_year_of_study = previous_year_of_study
        else:
            new_status = 'active'
            new_year_of_study = previous_year_of_study + 1
    else:
        new_year_of_study = previous_year_of_study
        if failed_courses:
            max_attempt = max(prior_attempts[c.id] + 1 for c in failed_courses)
        else:
            max_attempt = 0
        if max_attempt >= 3:
            new_status = 'withdrawn'
        elif max_attempt == 2:
            new_status = 'probation'
        else:
            new_status = 'repeated'

    return {
        'profile': profile,
        'program': program,
        'session': session,
        'cgpa': cgpa,
        'cgpa_ok': cgpa_ok,
        'core_passed': core_passed,
        'failed_courses': failed_courses,
        'prior_attempts': prior_attempts,
        'promote': promote,
        'previous_year_of_study': previous_year_of_study,
        'previous_status': previous_status,
        'new_year_of_study': new_year_of_study,
        'new_status': new_status,
    }


def apply_progression_decision(decision, admin_user):
    """
    Persists a decision computed by compute_progression_decision:
    updates the student's UserProfile, opens/increments CourseCarryOver
    rows for newly failed courses, clears any previously-open carry-over
    where a passing grade now exists (e.g. a resit), writes one
    immutable ProgressionDecisionLog row, and notifies the student.
    """
    profile = decision['profile']
    session = decision['session']

    # Clear any open carry-over now covered by a passing, released grade
    # (resits, etc.) — the single shared reconciliation also used live by
    # student-facing registration pages, so progression doesn't hand-roll a
    # second copy of the same clearing condition.
    CourseCarryOver.sync_cleared_for_student(profile.user)

    # Open/increment carry-over for this run's failed courses
    for course in decision['failed_courses']:
        rec, created = CourseCarryOver.objects.get_or_create(
            student=profile.user, course=course,
            defaults={
                'first_failed_session': session,
                'first_failed_term': course.semester,
                'attempts': 1,
                'is_cleared': False,
            },
        )
        if not created:
            rec.attempts += 1
            rec.is_cleared = False
            rec.save(update_fields=['attempts', 'is_cleared', 'updated_at'])

    profile.year_of_study = decision['new_year_of_study']
    profile.progression_status = decision['new_status']
    profile.save(update_fields=['year_of_study', 'progression_status'])

    if decision['failed_courses']:
        note = 'Carried over: ' + ', '.join(
            f"{c.code} (attempt {decision['prior_attempts'][c.id] + 1})" for c in decision['failed_courses']
        )
    else:
        note = 'No carried-over courses this session.'

    log = ProgressionDecisionLog.objects.create(
        student=profile.user,
        session=session,
        previous_year_of_study=decision['previous_year_of_study'],
        new_year_of_study=decision['new_year_of_study'],
        previous_status=decision['previous_status'],
        new_status=decision['new_status'],
        cgpa=decision['cgpa'],
        core_courses_passed=decision['core_passed'],
        changed_by=admin_user,
        note=note,
    )

    from apps.management.views import _notify  # local import avoids a module-load circular import
    messages_by_status = {
        'graduated': (f"Congratulations — You've Graduated!",
                      f"You have completed all requirements for your program. Congratulations!"),
        'active': (f"Promoted to {decision['new_year_of_study'] * 100}L",
                   f"You have been promoted to {decision['new_year_of_study'] * 100}L for the new session."),
        'probation': ("Academic Probation",
                      "You have been placed on academic probation due to outstanding carry-over courses. "
                      "Please register your carry-over courses as soon as registration opens."),
        'withdrawn': ("Academic Withdrawal Notice",
                      "Your academic standing has been reviewed and you have been withdrawn. "
                      "Please contact the academic office for further guidance."),
        'repeated': ("Repeating Current Level",
                     "You did not meet the requirements to progress this session. "
                     "You'll need to register any outstanding carry-over courses alongside your current level courses."),
    }
    title, message = messages_by_status.get(decision['new_status'], ('Academic Status Updated', 'Your academic status has been updated.'))
    _notify(user=profile.user, title=title, message=message, notif_type='system', link='/student/courses/')

    return log


def apply_manual_override(profile, program, session, new_year_of_study, new_status, reason, admin_user):
    """
    Directly sets one student's level/status for a session, bypassing
    the automatic calculation — for appeals or one-off corrections.
    Does not touch CourseCarryOver (use the Carry-Over page for that);
    still writes one ProgressionDecisionLog row, tagged as manual, so
    every progression change — computed or overridden — has one audit
    trail. Records what the automatic calculation would have decided,
    for context.
    """
    reference = compute_progression_decision(profile, program, session)

    profile.year_of_study = new_year_of_study
    profile.progression_status = new_status
    profile.save(update_fields=['year_of_study', 'progression_status'])

    system_decision = f"promote to {reference['new_year_of_study']}L" if reference['promote'] else reference['new_status']
    note = f"[Manual override by {admin_user.username}] {reason} (system-computed decision was: {system_decision})"

    log = ProgressionDecisionLog.objects.create(
        student=profile.user,
        session=session,
        previous_year_of_study=reference['previous_year_of_study'],
        new_year_of_study=new_year_of_study,
        previous_status=reference['previous_status'],
        new_status=new_status,
        cgpa=reference['cgpa'],
        core_courses_passed=reference['core_passed'],
        changed_by=admin_user,
        note=note,
    )

    from apps.management.views import _notify  # local import avoids a module-load circular import
    _notify(
        user=profile.user,
        title='Academic Status Updated',
        message='Your academic status has been manually reviewed and updated by the academic office. '
                'Contact the academic office if you have questions.',
        notif_type='system',
        link='/student/courses/',
    )

    return log
