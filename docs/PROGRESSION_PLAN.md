# Student Progression & Carry-Over — Implementation Plan

Status: **planning only — nothing in this document has been built yet.**
Companion to `AUDIT.md` (cross-cutting theme #1: "Student progression is not built, anywhere").

## 1. Problem, grounded in the actual code

Confirmed by reading the models directly (not just the audit summary):

- `UserProfile.year_of_study` (`eduweb/models.py:3296`) is written exactly once — at admission, inside `management.make_decision`. Nothing else in any of the seven apps ever changes it.
- `UserProfile.progression_status` (`eduweb/models.py:3308`) has 5 states — `active`, `probation`, `repeated`, `graduated`, `withdrawn` — and defaults to `active` at creation. No view, command, or signal in the codebase ever sets it to anything else. `'repeated'` and `'probation'` are enum values with zero logic behind them.
- `Program.duration_years` and `Program.credits_required` (`eduweb/models.py:1240,1245`) exist and could tell us when a student should graduate, but nothing reads them for that purpose today.
- `CourseGrade.is_passed` (`eduweb/models.py:4711`) is the only pass/fail signal that exists. There is **no GPA/CGPA field anywhere in the codebase** — grepped `eduweb/models.py` for `gpa`/`cgpa`, zero hits. Progression can only be course-pass-based, not grade-point-based, unless a GPA system is built first (out of scope here unless you want it in scope).
- `CourseRegistration` (`eduweb/models.py:4628`) already enforces prerequisites via `CourseGrade.is_passed` at registration time (`clean()` method, line 4667) — so the "prerequisite" concept the carry-over logic needs already has a working precedent to follow.

### The blocking issue: grade sources disagree (audit theme #2)

`student/views.py:_record_academic_grade` (line 1463) is the **only** place `CourseGrade` gets written automatically. It averages:
- `QuizAttempt.percentage` (best attempt per quiz)
- `AssignmentSubmission.score` (graded submissions, as % of max_score)

It does **not** read `StudentExamResponse` (`eduweb/models.py:5615`) at all — the CBT exam engine (`Exam` → `StudentExamResponse`, with `total_score`/`score_percentage`/`passed` fields already computed and stored, linked via `exam.course` → `LMSCourse`) is completely invisible to `CourseGrade`. Per your decision below, this must be fixed before progression is built on top of `CourseGrade`, or the computed pass/fail will be wrong for any course examined via the CBT engine.

Separately (already known from the audit, not re-verified here): the "Grades & Performance" page has its `CourseGrade` query commented out, and "Academic Records" builds a third, independent proxy from `StudentExamResponse` directly. Both need to be pointed at the same, now-unified, `CourseGrade` source.

## 2. Decisions locked in (from your answers)

| Question | Decision |
|---|---|
| Trigger | **Hybrid.** System auto-computes draft progression results when a session ends (or on-demand), but nothing is applied to `UserProfile` until an admin reviews and explicitly approves. |
| Carry-over policy | **Carry-over cap.** Student advances to `year_of_study + 1` regardless of individual course failures, but must re-register each failed **core** course as a carry-over alongside their new-level courses. If the number of failed core courses exceeds a threshold, the student repeats the level instead of advancing. *(Exact threshold number — see open questions below.)* |
| Grade source | **Fix unification first.** `_record_academic_grade` must incorporate `StudentExamResponse` before progression is computed from `CourseGrade`. |

## 3. Phased build order

### Phase 0 — Grade unification (prerequisite, do first)
1. Extend `_record_academic_grade` (or a new equivalent) to also pull `StudentExamResponse` rows for the course (`exam__course=lms_course, status='graded'`) and fold `score_percentage` into the average alongside quiz/assignment scores.
2. Decide and implement a weighting formula (currently everything is a flat average — CA/assignment/quiz vs. end-of-semester exam probably shouldn't be weighted equally). **Open question — see below.**
3. Point `student`'s "Grades & Performance" page at the real `CourseGrade` query (currently commented out) instead of its quiz/assignment-only proxy.
4. Point "Academic Records" at the same `CourseGrade` source instead of its separate `StudentExamResponse`-only proxy.
5. Manual QA pass (no test suite exists in this repo) — confirm dashboard, Grades & Performance, and Academic Records show identical numbers for the same student.

### Phase 1 — Data model additions
1. **New model** `CourseCarryOver` (home: `eduweb/models.py`, next to `CourseGrade`/`CourseRegistration`) — one row per student per failed-and-carried course: `student`, `course`, `originating_session` (session it was failed in), `cleared` (bool), `cleared_session` (nullable FK, set when finally passed). This is what `student`'s registration page reads to force re-registration of carry-over courses, and what `CourseRegistration.clean()`'s existing prerequisite check needs to be aware doesn't block a carry-over course from being retaken.
2. **New model** `SessionProgressionRun` (home: `management`, since it already owns `AcademicSession`) — one row per `(session, student)`: computed draft outcome (`advance` / `repeat` / `graduate` / `probation`), `failed_core_courses` (M2M or JSON list), `computed_at`, `status` (`pending_review` / `approved` / `rejected` / `overridden`), `reviewed_by`, `reviewed_at`, admin override fields. This is the "draft" layer the hybrid trigger needs — nothing touches `UserProfile` until a row here is approved.

### Phase 2 — Computation engine
1. A function (callable both from a management command for the "auto" half and from an admin-triggered view for the "on-demand" half): `compute_progression_for_session(session)`.
2. For each student with an `approved` `CourseRegistration` in that session: gather their level's core courses, check `CourseGrade.is_passed` for each (now trustworthy per Phase 0), apply the carry-over-cap rule from your decision, write a `SessionProgressionRun` row per student with a draft outcome. Never writes to `UserProfile` directly — this phase only ever produces draft rows for review.
3. Idempotency: re-running for the same session should update existing `pending_review` rows, not duplicate them, and should never touch rows already `approved`.

### Phase 3 — Admin review UI (`management` app)
1. New page: "End of Session Review" (natural home: alongside the existing Academic Session management, `management/views.py:3245`). Lists every `SessionProgressionRun` for a chosen session, grouped by draft outcome, with per-student failed-course detail.
2. Per-row override control (admin can flip a draft `repeat` to `advance` with a required reason, etc. — mirrors the existing exam-approval audit-trail pattern already in this app, which the audit calls out as the best-built workflow here).
3. "Approve & Apply" action (bulk, with a confirmation step — this app currently has zero confirmation on destructive Faculty/Department/Course cascades per the audit, so this must not repeat that mistake): on approval, for each row —
   - Advance/repeat `UserProfile.year_of_study` and set `progression_status` accordingly.
   - Create `CourseCarryOver` rows for every failed core course.
   - Set `progression_status = 'graduated'` when `year_of_study` would exceed `Program.duration_years`.
   - Fire a notification to the student (existing `Notification` model/pattern, used everywhere else in the codebase already).

### Phase 4 — Student-facing surfacing (`student` app)
1. Course registration page: carry-over courses from `CourseCarryOver` (uncleared) must appear pre-selected/required alongside the student's new-level core courses, and clearing one should set `cleared=True` on the matching row when `_record_academic_grade` later marks it passed.
2. Dashboard: show `progression_status` (probation/repeat banner) and current level clearly — right now the dashboard doesn't surface this at all since nothing has ever set it beyond `active`.

## 4. Open questions still needing your call before Phase 1 starts

1. **Carry-over threshold number** — "repeat the level if more than N core courses are failed." What's N? (Common Nigerian university conventions are 1, 2, or a credit-unit-based cap rather than a course count — let me know which you want.)
2. **Exam vs. CA/assignment weighting** — right now everything going into `CourseGrade.score` is a flat average. Do you want a weighted formula (e.g. 30% CA/assignment + 70% end-of-semester exam), and if so what split? Or is a flat average across everything (quiz + assignment + exam) fine?
3. **Probation before repeat?** — does a student get a `probation` warning on their *first* poor session before `repeated` kicks in on a second occurrence, or does the carry-over-cap rule alone decide `repeat` vs `advance` with no separate probation step?
4. **Graduation trigger** — automatic the moment `year_of_study` would exceed `Program.duration_years`, or does graduation need a separate manual sign-off step (e.g. final project/thesis clearance) that this system doesn't model yet?
5. **Does the "auto" half of the hybrid trigger mean "on session end date" or "on demand, any time an admin clicks compute"?** Both are described as "auto-compute, admin approves" but they're different scheduling mechanisms (a real cron/date-based trigger vs. a button that just doesn't need to wait for a scheduled job).

Nothing in Phase 1 onward should start until at least questions 1 and 2 are answered, since they change what `SessionProgressionRun` needs to store and what `compute_progression_for_session` actually computes.
