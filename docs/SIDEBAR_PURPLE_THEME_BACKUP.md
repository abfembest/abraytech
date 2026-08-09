# Sidebar Redesign Backup — Management Portal

Created before restyling the staff-portal sidebar (`templates/management/base.html`).
This file is NOT a template — it's just a backup/revert record — and is safe
to delete once the new design is approved.

**Current state (v2):** a bold purple gradient —
`bg-gradient-to-b from-purple-600 via-violet-700 to-indigo-900` with white
text and the original white-transparency overlay system (`hover:bg-white/10`,
active `bg-white/20`, dividers `border-white/10`, section labels
`text-white/50`, etc.) — unchanged from the original file, since white
overlays work on any sufficiently dark/saturated base color. Only the base
gradient itself moved from blue-purple (`from-primary-500 to-secondary-500`)
to a deliberate purple-to-indigo gradient, plus the submenu background CSS
override was retinted to a deep purple (`rgba(76, 29, 149, 0.45)` instead of
the original dark navy `rgba(30, 58, 138, 0.45)`).

**v1 (superseded):** an earlier pass used a *light* lavender gradient with
dark text and purple-tinted overlays throughout — replaced after feedback
that it should be a richer/darker purple, not light. The table below still
describes that v1 mapping for reference, in case you want to compare the two.

This portal's sidebar (and its `<style>` overrides) live entirely inside
`templates/management/base.html`, between:
- the `<style>` block starting at (original) line 67 — sidebar-specific CSS rules
- the `<aside id="sidebar">...</aside>` block starting at (original) line 450

Nothing outside those two regions was touched. No Django template tags, URLs,
permission checks, IDs, or JS behavior were changed — only Tailwind color
utility classes and a handful of CSS color values.

## How to revert

Every change was a mechanical find-and-replace of a small set of color
tokens, confined to the sidebar. To revert, re-run the same replacements
with old/new swapped (new → old), in this order, across
`templates/management/base.html`:

| New (purple theme)         | Original (revert to this)  |
|-----------------------------|------------------------------|
| `hover:bg-purple-100/70`    | `hover:bg-white/10`          |
| `bg-purple-200/70`          | `bg-white/20`                |
| `border-purple-200/50`      | `border-white/10`            |
| `border-purple-300/50`      | `border-white/20`            |
| `border-purple-300`         | `border-white/30`            |
| `bg-purple-50/70`           | `bg-white/5`                 |
| `text-purple-400` (section labels) | `text-white/50`       |
| `text-purple-300`          | `text-white/40`              |
| `text-purple-400` (course code, 1 spot) | `text-white/60`  |
| `text-purple-500` (role label, 1 spot) | `text-white/70`   |

Plus these one-off, non-global edits:

1. `<aside id="sidebar" class="...">` root classes:
   - New: `bg-gradient-to-b from-purple-50 via-fuchsia-50 to-violet-100 text-gray-700 border-r border-purple-100 flex-shrink-0 ...`
   - Original: `bg-gradient-to-b from-primary-500 to-secondary-500 text-white flex-shrink-0 ...`

2. Mobile close button (`#closeSidebar`):
   - New: `text-gray-500 hover:text-purple-700 focus:outline-none md:hidden`
   - Original: `text-white hover:text-gray-300 focus:outline-none md:hidden`

3. "Add New User" link text color:
   - New: `...transition-all text-sm text-purple-700">`
   - Original: `...transition-all text-sm text-white">`

4. Active-course chip (instructor sidebar) background + text:
   - New: `mb-1 bg-purple-100 rounded-lg px-3 py-2.5 sidebar-course-chip`
     and `text-xs font-bold text-purple-900 truncate leading-tight`
   - Original: `mb-1 bg-white/10 rounded-lg px-3 py-2.5 sidebar-course-chip`
     and `text-xs font-bold text-white truncate leading-tight`

5. In-CSS rules (inside the `<style>` block, ~line 106-439):
   - `.sidebar-item-active { background-color: ... }` — was `rgba(255,255,255,0.2)`, now a light-purple rgba
   - `#sidebar [id$="Menu"] { background-color: ... }` — was `rgba(30,58,138,0.45)` (dark navy), now a light-purple rgba
   - `#sidebar::-webkit-scrollbar-thumb` (both duplicate blocks) — was `rgba(255,255,255,0.15)` / hover `rgba(255,255,255,0.25)`, now purple-tinted equivalents
   - `#sidebar { scrollbar-color: ... }` (Firefox, both duplicate blocks) — same rgba swap as above

6. JS active-item scroll-into-view (`scrollSidebarToActive`, near the bottom
   `<script>` block): `nav.getElementsByClassName('bg-white/20')` was
   automatically updated to `nav.getElementsByClassName('bg-purple-200/70')`
   by the global token replacement in row 2 of the table above, since it's
   the same literal string. If reverting, this line must be changed back to
   `'bg-white/20'` too, or the "scroll to active sidebar item on load"
   feature will silently stop working.

Nothing else in the file (topbar, dropdowns, footer, modals, the global
`:root` `--color-primary-*`/`--color-secondary-*` variables used elsewhere
on management pages) was modified.

## Reverting the current (v2) bold-purple version to the true original

Since v2 kept the original white-overlay system intact, reverting to the
very first design (before any of this) only requires undoing two things:

1. `<aside id="sidebar" class="...">` root classes:
   - Current (v2): `bg-gradient-to-b from-purple-600 via-violet-700 to-indigo-900 text-white ...`
   - True original: `bg-gradient-to-b from-primary-500 to-secondary-500 text-white ...`

2. Submenu background CSS rule (`#sidebar [id$="Menu"]`):
   - Current (v2): `background-color: rgba(76, 29, 149, 0.45) !important;`
   - True original: `background-color: rgba(30, 58, 138, 0.45) !important;`

Everything else (all `hover:bg-white/10`, `bg-white/20`, `border-white/10`,
`text-white/50`, scrollbar rgba values, `.sidebar-item-active`, the JS
`getElementsByClassName('bg-white/20')` lookup) is already back to its
original value in the current file — no further changes needed for those.
