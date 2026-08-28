from django import template

register = template.Library()

_STATUS_CLASSES = {
    'new': 'bg-blue-100 text-blue-700',
    'contacted': 'bg-amber-100 text-amber-700',
    'qualified': 'bg-purple-100 text-purple-700',
    'converted': 'bg-green-100 text-green-700',
    'lost': 'bg-red-100 text-red-700',
}


@register.filter
def status_pill_class(status):
    return _STATUS_CLASSES.get(status, 'bg-gray-100 text-gray-600')
