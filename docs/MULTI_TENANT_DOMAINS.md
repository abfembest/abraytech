# Multi-Tenant Domains — MIU (miuedu.com) + Theology (theology.miuedu.com)

Status: **DEFERRED — discussion only, nothing implemented.** Revisit when ready to apply.

## The problem

`miuedu.com` (this repo, `main` branch) and `theology.miuedu.com` (`Videos/melbac`, `melbac` branch)
are two schools run off what used to be the same Django codebase, now split into two git branches
with **unrelated histories** (no common ancestor — confirmed via `git merge-base main origin/melbac`).
Every backend/dashboard fix has to be manually re-applied to both. That manual porting is the actual
pain point, not the branding difference.

## What we found comparing the two branches

Backend logic is ~99% identical — the real drift is smaller than the raw diff (240 files,
72k+/93k- lines) suggests, because most of that is branding (colors, copy, logo), not logic.

**Real, substantive drift found (not just cosmetic):**
- `melbac` is **missing AuditLog calls main added later** — `eduweb/views.py`'s `profile()` (email
  change logging) and `confirm_payment()` (Stripe payment logging) both lack the `_get_client_ip()`
  helper and `AuditLog.objects.create(...)` calls that exist in `main`. Real compliance/traceability gap.
- **Model schema differs.** `eduweb/models.py`: melbac added `display_order` fields + `ordering`
  changes to 7 models (Faculty, Department, BlogCategory, InstitutionPartner, SiteHistoryMilestone,
  Testimonial, InstitutionMember) that main doesn't have. Main uses different
  `Program.STUDY_MODE_CHOICES` value encoding (`'full_time'`) vs melbac (`'Full Time'`) — a data-shape
  mismatch, not just cosmetic.
- `management/views.py` has a 196-line delta — admin dashboard logic, not public pages.
- **Dashboard templates diverged structurally**: main consolidated per-role profile/settings into one
  shared `account/profile.html` + `account/settings.html`; melbac still has separate
  `instructor/profile.html`, `students/profile.html`, etc. Main uses modals for department/program CRUD
  in the admin dashboard; melbac uses full standalone pages. Support ticket templates live in different
  app locations on each side.
- **Currently live and unported**: the last two `main` commits (`1b5eea0 responsiveness`,
  `548f3fa solved ui responsiveness`) touched `templates/base.html` and `templates/index.html` (public)
  plus a long list of management templates. None of that has been ported to melbac — right now melbac's
  homepage/base layout is running the pre-responsiveness-fix version.

**Public-facing pages: byte-identical (zero drift today)**
`research.html`, `campus_life.html`, `admission_requirement.html`, `404.html`, `blank_page.html`,
`applications/admission_letter.html`, library's `category.html`/`detail.html`/`home.html`/`search.html`.

**Public-facing pages: differ (mostly branding wrapper, not logic)**
`about.html`, `all_programs.html`, `applications/application_status.html`, `auth.html`, `blog.html`,
`blog/blog_list.html`, `blog/blog_detail.html`, `chatbot/chatbot.html`, `contact.html`,
`faculty_detail.html`, `form.html`, `includes/auth_branding_panel.html`, `includes/searchable_select.html`,
`otp_verify.html`, `program_detail.html`, `signup.html`, `library/base.html`, `base.html`, `index.html`.

**Bugs found along the way (independent of the merge question):**
- Main: `/activities/` URL is wired (`eduweb/urls.py:10` → `views.activities`) but
  `templates/activities.html` doesn't exist anywhere in main — throws `TemplateDoesNotExist`. Not
  linked from any nav, so unhit in practice, but a live dead route. Two-line fix whenever convenient.
- `form.action` shadowing bug: a `<form>` with a hidden `<input name="action">` breaks `this.action` in
  JS (resolves to the DOM element, not the URL string) — found and fixed in melbac's `signup.html`.
  **Main's own `templates/signup.html` has the exact same pattern right now** — flagged, not fixed,
  since it's outside whatever task surfaces it next. Fix: `form.getAttribute('action')` instead of
  `form.action`. (Already logged in project memory as `form_action_shadowing_gotcha`.)
- Melbac has two orphaned pre-Django mockup pages, `templates/course.html` and `templates/detail.html`
  (reference `test2.html#programs`, old static-HTML copy) — not wired into any current view, melbac's
  version of main's `BK/` clutter.

## Recommendation: converge to one codebase, tenant-selected by domain

Two branches of the same app is the worst of both worlds — full maintenance cost of separate
codebases (drift, manual porting, the AuditLog gap above) with none of the benefit real separation
would give (independent release cadence, isolated blast radius). The codebase already has `SiteConfig`
driving branding, so this isn't fighting the architecture — it's finishing a decision it already implies.

### How it would work

1. **Tenant resolution.** Small middleware reads `request.get_host()`, maps it to a tenant slug
   (`'miu'` vs `'theology'`) via a DB table or setting (not hardcoded domains), stashes
   `request.tenant`. Exposed to templates via a context processor next to the existing
   `site_config_context`.

2. **Branding/copy — mostly already solved.** Make `SiteConfig` tenant-scoped (one row per tenant
   instead of a singleton); context processor picks the row matching `request.tenant`. Most copy
   differences (school name, addresses, emails, phones — see `contact.html`) disappear here, no
   template branching needed.

3. **Visual theme (colors) — the easy part, and it's basically already built.**
   `static/src/melbac.css` already exists as a **real, distinct** Tailwind theme
   (`--mb-primary: #840384`, its own Playfair Display / Crimson Pro / Outfit font pairing) with its own
   `npm run build:melbac` script — confirmed via `package.json`. It's just currently
   `@source`'d against the dead in-app `melbac/` sub-app's templates (`@source "../templates/melbac/**/*.html"`),
   so it's never linked from any live page. Fix: re-point that `@source` at the real shared templates,
   and in `base.html`: `{% if request.tenant == 'theology' %}<link href="melbac.css">{% else %}<link href="styles.css">{% endif %}`.
   The palette work is done — it just needs to be re-targeted at the live site instead of the dead one.

4. **Whole pages that exist for one tenant only.** Two flavors:
   - Soft-hide (page works for both, only relevant for one) — gate the `<a>` in nav/sidebar only.
   - Hard-hide (must 404 for the wrong tenant) — one `if request.tenant != 'theology': raise Http404`
     at the top of the view.
   - Tenant-exclusive extra pages are just normal views/templates, gated the same way.

5. **Inner content on shared pages.** Two tiers, in priority order:
   - **Data-driven (preferred):** add fields to `SiteConfig` (e.g. `hero_cta_text`, `hero_cta_url`) so
     copy differences are admin-editable, no deploy needed, and it scales past 2 tenants.
   - **Structural branching:** for a genuinely different section/layout, a plain
     `{% if request.tenant == 'theology' %}...{% endif %}` block is fine — matches the project's
     existing convention (see memory `feedback_no_custom_templatetags`) of preferring built-in `{% if %}`
     chains over custom template tags.

### Worked example: the homepage hero (what "add the gate" would look like)

Main's `templates/index.html` hero (~line 172-204) currently renders **two** CTA buttons:
`SECULAR` → `{% url 'eduweb:all_programs' %}`, and `THEOLOGICAL` → hardcoded external link
`https://theology.miuedu.com/` (`target="_blank"`). This is main's current way of cross-linking to the
theology site as a *separate* deployment.

Melbac's `templates/index.html` hero (confirmed by reading it directly, ~line 149-159) has **one**
single CTA: `Explore Our Programs` → `{% url 'eduweb:all_programs' %}`, same visual style as main's
`SECULAR` button (`graduation-cap` icon instead of `book-open`) — no dual-button split, because on
that site you're already "in" the theology school.

Once on one shared codebase, the gate is a single template condition, no middleware even required for
this one case since `request` is already in every template's context (confirmed via
`contact.html`'s use of `request.build_absolute_uri`):

```django
{% if 'theology' in request.get_host %}
  {# single "Explore Our Programs" button, melbac's existing markup #}
{% else %}
  {# current SECULAR / THEOLOGICAL dual-button pair #}
{% endif %}
```

Note: this only fires in production once both domains are actually served by the *same* deployment.
Today `theology.miuedu.com` is a fully separate checkout/deployment (`Videos/melbac`), so this
conditional would be a harmless no-op until the convergence actually happens — it's meant to be
written in preparation, not to change current behavior on its own.

## Tradeoffs, ranked by actual size

1. **Biggest hidden cost: data scoping, not theming.** If MIU and the theology school have genuinely
   separate student bodies/programs (near-certain), `Program`, `Faculty`, `Course`, applications, and
   enrollments all need a `school` FK too, not just `SiteConfig` — so listings, applications, and
   dashboards filter by tenant. That's 60+ models to audit. Theming is the easy 20%; this is the real 80%.
2. **Migration risk** lives in backfilling that FK onto existing rows correctly, not in adding the
   field itself.
3. **Local dev gets harder** — testing "the other school" becomes "hit the other hostname"
   (`/etc/hosts` entries, or a DEBUG-only query-param/session override), not "check out the other branch."
4. **Template `{% if tenant %}` branching doesn't scale past 2-3 tenants** — fine at 2 schools; push
   toward `SiteConfig`-driven fields as the difference is just copy/links, reserve branching for
   genuinely structural differences.
5. **Setup cost is real but one-time**: middleware + context processor + `SiteConfig` tenant migration +
   re-pointing `melbac.css` + auditing ~150 templates that currently assume single-tenant. Weighed
   against the *recurring* cost of manual git-porting forever, this is the better trade — but it isn't free.

## When ready to apply

Suggested order: (1) tenant middleware + context processor, (2) `SiteConfig` → per-tenant rows +
migration, (3) re-point `melbac.css` and wire the stylesheet switch in `base.html`, (4) the hero gate
above as the first real template case, (5) audit remaining public templates one at a time, (6) only
then tackle the `school` FK data-scoping work on `Program`/`Faculty`/`Course`/applications — the part
most likely to need careful migration planning.
