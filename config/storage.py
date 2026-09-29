"""
Static files storage: WhiteNoise compression plus hashed filenames, so
browsers can cache CSS/JS/images for a year and still get new versions
right after a deploy (the name changes when the content does).

Tailwind sources (static/src/*.css) and the vendored font stylesheets
(static/vendor/fonts/<font>/<font>.css) are skipped when collectstatic
rewrites url()s: they are build inputs, never loaded by a page. The fonts:
Tailwind inlines them into static/css/*.css, and scripts/vendor-assets.js
writes their url()s relative to static/css/ for that reason, so read in
place those paths point nowhere and would abort collectstatic. The compiled
stylesheets that actually load the font files are processed as normal.
Source-map comments are also left alone (see _without_source_maps).
"""
from whitenoise.storage import CompressedManifestStaticFilesStorage


def _is_build_input(path):
    """Tailwind sources (src/*.css) and vendored font stylesheets: inputs to
    `npm run build:*`, never loaded by a page."""
    path = path.replace('\\', '/')  # collectstatic uses OS separators
    return path.endswith('.css') and path.startswith(('src/', 'vendor/fonts/'))


def _without_source_maps(patterns):
    """Django's url-rewrite patterns minus the sourceMappingURL ones: vendored
    minified files point at .map files that were never copied (they only
    matter to browser devtools), which would otherwise abort collectstatic."""
    def keep(pattern):
        regex = pattern if isinstance(pattern, str) else pattern[0]
        return 'sourceMappingURL' not in regex
    return tuple((glob, tuple(p for p in group if keep(p))) for glob, group in patterns)


class StaticFilesStorage(CompressedManifestStaticFilesStorage):
    # A {% static %} path missing from the manifest falls back to the plain
    # filename instead of raising a server error.
    manifest_strict = False
    patterns = _without_source_maps(CompressedManifestStaticFilesStorage.patterns)

    def post_process(self, paths, dry_run=False, **options):
        paths = {path: value for path, value in paths.items() if not _is_build_input(path)}
        yield from super().post_process(paths, dry_run=dry_run, **options)
