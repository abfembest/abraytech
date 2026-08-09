# Restructure Map — Phase 1 (DigitalCampus → Abraytech skeleton)

## Header

- **Date of restructure:** 2026-08-09
- **Pre-restructure commit hash:** `3346f41602fd5a7a3d8cc242db43b5e11bcd8b9e` ("image display", 2026-08-07 22:11:37 +0100), on the `main` branch of `origin/abfembest/DigitalCampus.git`.
- This repo's local git history was deliberately wiped and reinitialized as a fresh repo after this restructure (no remote attached yet — a new repo hasn't been created). **The full pre-restructure history is not lost**: it still lives, untouched, at `C:\Users\George\Videos\DigitalCampus` (same commit, same remote) and on GitHub at `origin/abfembest/DigitalCampus.git`. If you ever need to diff against "how the code looked before this restructure," use that copy or that commit hash — not this repo's history, which now starts fresh from the restructure commit.

## Purpose

This document exists so that a future commit made to the live school deployment (`Videos\DigitalCampus`) can still be manually reconciled into this restructured repo — since the two will diverge in file layout (this one moved to a PRD-aligned `apps/` + `config/` structure) even though the underlying app code is otherwise untouched.

## Directory rename table

| Old path | New path | App Python package name change | Django `app_label` change |
|---|---|---|---|
| `DigitalCampus/` | `config/` | project config package: `DigitalCampus` → `config` | n/a (not a Django app) |
| `eduweb/` | `apps/eduweb/` | `eduweb` → `apps.eduweb` | unchanged (`eduweb`) |
| `management/` | `apps/management/` | `management` → `apps.management` | unchanged (`management`) |
| `student/` | `apps/student/` | `student` → `apps.student` | unchanged (`student`) |
| `parent/` | `apps/parent/` | `parent` → `apps.parent` | unchanged (`parent`) — still dormant (in `INSTALLED_APPS`, but its URL include stays commented out in `config/urls.py`) |
| `instructor/` | `apps/instructor/` | `instructor` → `apps.instructor` | unchanged (`instructor`) |
| `finance/` | `apps/finance/` | `finance` → `apps.finance` | unchanged (`finance`) |
| `payment/` | `apps/payments/` | `payment` → `apps.payments` | **changed**: `payment` → `payments` (safe — zero migrations existed) |
| `melbac/` | `apps/melbac/` | `melbac` → `apps.melbac` | unchanged (`melbac`) — still dormant (URL include commented out) |
| `library/` | `apps/library/` | `library` → `apps.library` | unchanged (`library`) |
| `chatbot/` | `apps/chatbot/` | `chatbot` → `apps.chatbot` | unchanged (`chatbot`) |
| `support/` | `apps/support/` | `support` → `apps.support` | unchanged (`support`) |

## AppConfig identity table

| App | Old `name=` | New `name=` | `label=` (explicit) | Has real migrations? |
|---|---|---|---|---|
| eduweb | `'eduweb'` | `'apps.eduweb'` | `'eduweb'` | Yes (66 migrations) |
| management | `'management'` | `'apps.management'` | `'management'` | No |
| student | `'student'` | `'apps.student'` | `'student'` | No |
| parent | `'parent'` | `'apps.parent'` | `'parent'` | No |
| instructor | `'instructor'` | `'apps.instructor'` | `'instructor'` | No |
| finance | `'finance'` | `'apps.finance'` | `'finance'` | No |
| payments | `'payment'` (class `PaymentConfig`) | `'apps.payments'` (class renamed to `PaymentsConfig`) | `'payments'` | No |
| melbac | `'melbac'` | `'apps.melbac'` | `'melbac'` | No |
| library | `'library'` | `'apps.library'` | `'library'` | No |
| chatbot | `'chatbot'` | `'apps.chatbot'` | `'chatbot'` | Yes (2 migrations) |
| support | `'support'` | `'apps.support'` | `'support'` | Yes (1 migration; FK-coupled to `eduweb`) |

All `app_label`s were kept identical to their pre-restructure values (except the intentional `payments` rename), so the existing `db.sqlite3` and its `django_migrations`/`django_content_type` rows required **no migration surgery, no `--fake`, no `ContentType` fixups** — confirmed via `manage.py showmigrations` (all pre-existing migrations still show `[X]` applied) and `manage.py makemigrations --check --dry-run` (no model drift detected).

## Settings/bootstrapping changes checklist

| File | Old | New |
|---|---|---|
| `manage.py` | `DJANGO_SETTINGS_MODULE=DigitalCampus.settings` | `config.settings` |
| `passenger_wsgi.py` | `DigitalCampus.settings`, `from DigitalCampus.wsgi import application` | `config.settings`, `from config.wsgi import application`. **cPanel venv path left untouched**: `/home/miuenecd/virtualenv/DigitalCampus/3.12/...` — that's an unrelated hosting-account artifact, not a Python import path. |
| `train_model.py` | `DigitalCampus.settings`; `from chatbot.models import IntentResponse` | `config.settings`; `from apps.chatbot.models import IntentResponse` |
| `config/wsgi.py` / `config/asgi.py` | `DJANGO_SETTINGS_MODULE=DigitalCampus.settings` | `config.settings` |
| `config/settings.py` | `INSTALLED_APPS` had a phantom `"DigitalCampus"` entry (no models/migrations behind it) | entry removed; all 11 project apps prefixed `apps.` |
| `config/settings.py` | `MIDDLEWARE`: `eduweb.security_middleware...`, `eduweb.exam_middleware...` | `apps.eduweb.security_middleware...`, `apps.eduweb.exam_middleware...` |
| `config/settings.py` | `ROOT_URLCONF = "DigitalCampus.urls"` | `"config.urls"` |
| `config/settings.py` | `WSGI_APPLICATION = "DigitalCampus.wsgi.application"` | `"config.wsgi.application"` |
| `config/settings.py` | `TEMPLATES` context_processors (8 entries, 7 eduweb + 1 support) | all 8 prefixed `apps.` |
| `config/settings.py` | `LOGIN_REDIRECT_URL`/`LOGOUT_REDIRECT_URL` (`eduweb:apply`, `eduweb:index`) | **unchanged** — these are Django URL namespace:name references, not Python import paths; app namespaces didn't change |
| `config/urls.py` | `handler404 = 'eduweb.views.custom_404'` | `'apps.eduweb.views.custom_404'` |
| `config/urls.py` | `include('eduweb.urls')`, `include('management.urls')`, `include('student.urls')`, `include('instructor.urls')`, `include('finance.urls')`, `include('payment.urls')`, `include('chatbot.urls')`, `include('library.urls')`, `include('support.urls', namespace='support')` | all prefixed `apps.` (`payment.urls` → `apps.payments.urls`); the commented-out `parent`/`melbac` includes were updated too for when they're re-enabled |
| `config/urls.py` | URL prefix strings (`path('payment/', ...)`, etc.) | **unchanged** — only the Python module path changed, not the public URL surface, to minimize divergence from the live site |

## Import-path translation rule

**General rule:** `from <app>.` → `from apps.<app>.` (and `import <app>.` → `import apps.<app>.`) everywhere, for all 11 apps. `payment` also becomes `payments` as part of the translation.

**Exceptions:**
1. **5 migration files** had module-level bareword self-imports (`import eduweb.models`, `import support.models`) used for `upload_to=` callables and mixin `bases=` — these needed an *aliased* import, not a plain prefix rewrite, to avoid also rewriting the safe `to='eduweb.foo'` app_label strings that must stay as-is:
   - `apps/eduweb/migrations/0001_initial.py`, `0004_libraryitem.py`, `0010_exam_examquestion_examstatuslog_studentexamresponse_and_more.py`, `0038_program_min_cgpa_to_progress_and_more.py`
   - `apps/support/migrations/0001_initial.py`
   - Pattern used: `import eduweb.models` → `import apps.eduweb.models as eduweb_models`, then every `eduweb.models.X` call-site in that file → `eduweb_models.X`. Same for `support.models` → `support_models`.
2. **`payment/` URL prefix stays `payment/`** in `config/urls.py` even though the app package/module is now `apps.payments` — only the `include()` target's Python path changed, the public route string didn't.
3. **`passenger_wsgi.py`'s cPanel venv path** still contains the literal substring `DigitalCampus` — intentionally left alone (see settings table above).

## Deleted items log

| Item | Size | Why |
|---|---|---|
| `staticfiles/` | ~34MB | `collectstatic` build output, regenerable, zero tracked files |
| `media/` | ~100MB | Confirmed disposable local dev/test uploads (recreated as an empty dir with `.gitkeep`) |
| `stripeinstallations/stripe.exe` | ~30MB | Stripe CLI binary, not source code, shouldn't have been tracked |
| `BK/HTML template/` (5 files) | ~420KB | Legacy pre-Django static HTML mockups |
| `.claude/worktrees/agent-a0ecc390a9189c948/` | ~105MB | Leftover stray agent worktree from a prior Claude Code session |
| `base (1).html` | 59KB | Stray duplicate/backup of a base template |
| `stderr.log` | small | Stray log file |
| `tailwind cmd` | small | Scratch note; the actual command is already documented as npm scripts (`npm run watch:css` etc., see `package.json`/`CLAUDE.md`) |
| `db.sqlite3.backup-20260721-191849` | ~2.7MB | Stray DB backup |
| Empty `migrations/__pycache__/` in the 8 model-less apps | small | Stale bytecode cache; the `migrations/` folders themselves only ever contained `__init__.py` |

## Deferred to future phases (explicitly NOT part of this pass)

- **Template/static reorganization** into the PRD's `templates/{public,dashboard,accounts,store,lms,consultation,travel,repository,support,admin}` shape. The existing root `templates/` (per-app subfolders: `management/`, `students/`, `instructor/`, `finance/`, `library/`, `blog/`, `applications/`, `account/`, `chatbot/`, `includes/`) and `static/` trees are completely untouched.
- **New PRD business-module apps**: `store`, `orders`, `consultation`, `travel`, `repository`, `accounts`, `permissions`, `core`, `website`, `notifications`, `audit`, `blog` do not exist yet — only the 11 pre-existing apps were relocated.
- **eduweb → lms consolidation**: the PRD envisions a dedicated `lms` app; today that functionality is spread across `eduweb` + `student` + `instructor` + `management`. No consolidation happened in this pass.
- Custom email-based `AUTH_USER_MODEL`, PostgreSQL migration, Celery/Redis, `/api/v1/` layer — all still outstanding per the original PRD-vs-codebase gap analysis, untouched here.
- `.gitignore` cleanup went further than originally planned as "optional": once `.git` was wiped and reinitialized, the repo had **zero tracked files**, meaning the old blanket rules (`**/settings.py`, `*.md`, and a directory-level `migrations/` rule that — combined with its own negations — only re-included `__init__.py`, not actual migration content) would have **silently excluded `config/settings.py`, every doc in `docs/`, and all 66+ real migration files** from the fresh initial commit. Previously these survived only because they'd been committed *before* those ignore rules were ever added (gitignore doesn't retroactively untrack already-tracked files) — that grandfathering disappeared the moment history was wiped. All three rules were removed from `.gitignore` so this repo's first commit actually contains its own settings, docs, and migrations.

## Reconciliation workflow — applying a future `Videos\DigitalCampus` commit onto this repo

1. Find the changed file's **old path** in the commit/diff from `Videos\DigitalCampus` (e.g. `eduweb/views.py`).
2. Look it up in the **directory rename table** above to find its **new path** in this repo (e.g. `apps/eduweb/views.py`).
3. Apply the diff's content changes at the new path.
4. If the diff touches an import line referencing another project app (`from eduweb.models import ...`, `from student.forms import ...`, etc.), mechanically translate it per the **import-path translation rule** above (`from eduweb.` → `from apps.eduweb.`, `payment` → `payments`, etc.) before/while applying.
5. If the diff touches `DigitalCampus/settings.py` or `DigitalCampus/urls.py`, apply the equivalent edit to `config/settings.py` / `config/urls.py`, translating any app-path strings per the settings/bootstrapping table above.
6. If the diff adds a new migration file, check whether it needs the same bareword-self-import treatment (rare — only matters if the new migration references `upload_to=`/`bases=` callables from the same app's `models.py` directly rather than via Django's normal FK `to='applabel.model'` strings).
7. Re-run `python manage.py check`, `python manage.py showmigrations`, and `python manage.py makemigrations --check --dry-run` after applying, same as this restructure's own verification pass.
