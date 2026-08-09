# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

DigitalCampus is a Django 5.0 Learning Management System (LMS) for a Nigerian university/institution ("MIU"). Locale is `en-ng` / `Africa/Lagos`. It's a monolithic multi-app Django project (not microservices) — most apps share one data model defined in `eduweb`.

## Commands

**Run the dev server:**
```
python manage.py runserver
```

**Migrations:**
```
python manage.py makemigrations
python manage.py migrate
```

**Tailwind CSS build** (two separate stylesheets, built from `static/src/*.css` into `static/css/*.css` via `@tailwindcss/cli`):
```
npm run watch:css     # site theme, watch mode
npm run build:css     # site theme, minified
npm run watch:all     # both stylesheets, watch mode
npm run build:all     # both stylesheets, minified
```

**Chatbot intent model training** (regenerates `ml_models/intent_pipeline.joblib` from `intents.json` and syncs `chatbot.IntentResponse` rows):
```
python train_model.py
```

There is effectively no automated test suite — every app's `tests.py` is the untouched Django boilerplate stub. Don't assume `python manage.py test` exercises anything meaningful; verify behavior manually (e.g. via the `verify` skill) instead of relying on tests.

## Environment / config

Settings are loaded via `python-decouple` from a git-ignored `.env` file at the repo root (`DigitalCampus/settings.py`). Expected variables: `SECRET_KEY`, `DEBUG`, `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`, `CONTACT_EMAIL`, `DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_CSRF_COOKIE_SECURE`, `STRIPE_SECRET_KEY`, `STRIPE_PUBLIC_KEY`, `STRIPE_WEBHOOK_SECRET`. `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` are hardcoded rather than env-driven. Database is SQLite (`db.sqlite3`) with no Postgres switch, despite `psycopg2` being in `requirements.txt`.

Deployment is via Passenger (`passenger_wsgi.py`, `tmp/restart.txt` triggers app restart on cPanel-style hosts). Static files are served through WhiteNoise in production.

## Architecture

### The "core app" pattern

`eduweb` is not just the public marketing site — it's the shared kernel. Its `models.py` (~6000 lines, ~68 model classes) defines nearly everything: `Faculty`, `Department`, `Program`, `Course`, `CourseApplication`, `Exam`/`ExamQuestion`, `Enrollment`, `Certificate`, `Badge`, `BlogPost`, `UserProfile`, `Invoice`, `LMSCourse`/`Lesson`/`Quiz`, etc. Other apps (`student`, `instructor`, `finance`, `management`, `payment`, `library`) mostly import and operate on `eduweb`'s models rather than defining their own — check `eduweb/models.py` first when looking for a model, even if you're working inside another app.

`eduweb` also provides the template context processors wired into `TEMPLATES` (`application_status_context`, `navigation_data`, `site_config_context`, `student_counts`, `admin_counts`, `permissions_context`) and two custom middleware classes used project-wide: `eduweb.security_middleware.SessionSecurityMiddleware` (inactivity timeout logout) and `eduweb.exam_middleware.ExamLockMiddleware` (locks navigation during an active exam session).

### Users, roles, and access control

There's no custom `AUTH_USER_MODEL` — it's stock `django.contrib.auth.User`. Role-based behavior is layered on with `eduweb.models.UserProfile` (one-to-one with `User`, accessed as `request.user.profile`), which carries a `role` field (`student`, `instructor`, `admin`, `finance`, ...). A separate, finer-grained `StaffPermissionsMatrix` model in the same file governs per-role `can_view`/`can_edit`/`can_export` permissions for back-office staff.

All role-gating decorators live in one place, `eduweb/decorators.py`, and are imported by views across every app: `check_for_auth`, `applicant_required`/`smart_redirect_applicant`, `instructor_required`, `admin_required`, `finance_required`. They all follow the same check order — `is_authenticated` → `is_active` → `profile.email_verified` → `profile.role` — before redirecting to `eduweb:auth_page` with a `messages` framework notice. When adding a new staff-facing view, reuse one of these decorators rather than hand-rolling role checks.

### App map (routed from `DigitalCampus/urls.py`)

| URL prefix | App | Role |
|---|---|---|
| `/` | `eduweb` | Public site, auth/registration/OTP, applications; the shared model layer for everything else |
| `/student/` | `student` | Student portal: dashboard, course catalog/registration, enrollment, lessons, assignments, quizzes/exams (large) |
| `/instructor/` | `instructor` | Instructor portal: course/section/lesson/quiz/question/assignment CRUD, grading (large) |
| `/management/` | `management` | Admin/back-office: application review, transcripts, faculties/departments/programs/sessions/intakes/courses CRUD, staff permissions (largest app besides `eduweb`) |
| `/finance/` | `finance` | Finance-staff dashboard: payroll, subscriptions |
| `/payment/` | `payment` | Payment records/refunds/invoices/transaction reports; calls the `stripe` SDK directly (e.g. `stripe.Refund.create`) |
| `/library/` | `library` | Digital library: category browsing, item detail, download, search |
| `/chatbot/` | `chatbot` | NLU chatbot session API (`start_session`/`send_message`/`close_session`/`session_status`) backed by the trained intent model |

`parent` exists as an app skeleton (models/views are near-empty stubs) but is **not wired into `urls.py`** — its URL include is commented out. Treat it as unimplemented, not a working portal.

`stripeinstallations/` and `ml_models/` are plain directories, not Django apps — the former just bundles the Stripe CLI binary (local webhook testing), the latter holds the trained `intent_pipeline.joblib` artifact consumed by `chatbot`.

### Chatbot / intent model

`intents.json` (root) is the training data; `train_model.py` builds a `TfidfVectorizer` + `LogisticRegression` pipeline (scikit-learn) via `make_pipeline`, saves it to `ml_models/intent_pipeline.joblib`, and upserts the first canned response per intent into `chatbot.IntentResponse`. The runtime `chatbot` app loads that pipeline to classify incoming `ChatMessage`s within a `ChatSession` and looks up the matching `IntentResponse`. If you edit `intents.json`, re-run `train_model.py` for the change to take effect.

### Frontend / static assets

Tailwind input lives in `static/src/`, compiled output in `static/css/` (see Commands above) — always edit the `static/src/*.css` source, never hand-edit the compiled `static/css/*.css` output directly. There's also a hand-written, non-Tailwind `static/css/course.css`. Templates live under root `templates/`, with shared pages at the top level and per-app subdirectories (`applications/`, `blog/`, `chatbot/`, `finance/`, `instructor/`, `library/`, `management/`, `students/`).

### Not relevant to app logic

`BK/` holds pre-Django static HTML mockups (legacy design backup). `tmp/restart.txt` is a Passenger deployment artifact. `stderr.log` / `OLd_stderr.log` are stray log files, not source.
