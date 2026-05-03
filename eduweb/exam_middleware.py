"""
exam_lock_middleware.py
-----------------------
If a student has an active (IN_PROGRESS) exam, any request to a URL
outside that exam is redirected back to the exam page.

Place this file at:
    eduweb/exam_middleware.py          ← matches what settings.py already has

It is already wired up in your settings.py as:
    'eduweb.exam_middleware.ExamLockMiddleware'
"""

import logging
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)

# ── Paths always allowed through, even during an active exam ──────────────
# IMPORTANT: your app is mounted at /student/ (no trailing 's').
# The whole /student/exam/ prefix must be allowed so that start/, data/,
# save/, flag-tab-switch/, and submit/ are never redirected.
_ALWAYS_ALLOWED = (
    '/static/',
    '/media/',
    '/admin/',
    '/auth/',
    '/logout/',
    '/student/exam/',   # ← /student/ NOT /students/
)


def _is_allowed(path: str) -> bool:
    return any(path.startswith(p) for p in _ALWAYS_ALLOWED)


class ExamLockMiddleware(MiddlewareMixin):
    """
    One DB query per request. If the student has an IN_PROGRESS exam,
    every URL outside /student/exam/... is redirected to that exam page.
    Staff and superusers are never affected.
    """

    def process_request(self, request):
        if not request.user.is_authenticated:
            return None

        if request.user.is_staff or request.user.is_superuser:
            return None

        if _is_allowed(request.path_info):
            return None

        # Import here to avoid app-registry issues at module load time.
        # Your INSTALLED_APPS shows the app is named 'student' (no s).
        from django.utils import timezone
        from eduweb.models import StudentExamResponse

        now = timezone.now()
        active = (
            StudentExamResponse.objects
            .filter(
                student=request.user,
                status=StudentExamResponse.IN_PROGRESS,
                submitted_at__isnull=True,          # not already submitted
                exam__end_datetime__gt=now,          # exam window hasn't closed
                exam_started_at__isnull=False,       # student actually started it
            )
            .select_related('exam')
            .first()
        )

        if active is None:
            return None

        exam_url = reverse('students:start_exam', kwargs={'slug': active.exam.slug})

        if request.path_info == exam_url:
            return None  # already on the right page, don't loop

        logger.info(
            'ExamLock: user=%s redirected from %s → %s (exam=%s)',
            request.user.username, request.path_info, exam_url, active.exam.slug,
        )
        return redirect(exam_url)