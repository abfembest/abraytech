from django import template
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

register = template.Library()

BULLET_PREFIXES = ('- ', '* ', '• ')


@register.filter
def rich_text(value):
    """Render staff-typed plain text as paragraphs and bullet lists.

    Blank lines separate blocks; consecutive lines starting with "- ", "* " or
    "• " become one <ul>; other consecutive lines become one <p> joined with
    <br>. Every line is escaped, so the result is safe to output.
    """
    blocks = []
    kind = None
    for line in (raw.strip() for raw in str(value or '').splitlines()):
        if not line:
            kind = None
            continue
        line_kind = 'ul' if line.startswith(BULLET_PREFIXES) else 'p'
        if line_kind != kind:
            blocks.append((line_kind, []))
            kind = line_kind
        blocks[-1][1].append(line[2:].strip() if line_kind == 'ul' else line)

    html = []
    for kind, lines in blocks:
        if kind == 'ul':
            items = format_html_join('', '<li>{}</li>', ((line,) for line in lines))
            html.append(format_html(
                '<ul class="list-disc space-y-2 pl-6 marker:text-brandblue">{}</ul>', items,
            ))
        else:
            html.append(format_html('<p>{}</p>', format_html_join(mark_safe('<br>'), '{}', ((line,) for line in lines))))
    return mark_safe(''.join(html))
