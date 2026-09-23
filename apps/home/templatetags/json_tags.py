import json

from django import template
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.safestring import mark_safe

register = template.Library()

# Same escapes Django's json_script uses, so the output can sit inside a
# <script> block without a value being able to close it or open markup.
_JSON_SCRIPT_ESCAPES = {
    ord('>'): '\\u003E',
    ord('<'): '\\u003C',
    ord('&'): '\\u0026',
}


@register.filter(name='safe_json')
def safe_json(value, default=None):
    """Serialise a value as a JavaScript-safe JSON literal.

    Use instead of `{{ value|safe }}` for data embedded in <script>: a Python
    dict rendered with |safe is a repr (None/True break JS) and user text in it
    can close the <script> element.
    """
    if value is None or value == '':
        # Default is a JSON literal ("{}", "[]", "null"), not a value to encode.
        if default in ('{}', '[]', 'null'):
            return mark_safe(default)
        value = None
    if isinstance(value, str):
        # Legacy rows may hold the JSON as text; emit the decoded structure.
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            pass
    return mark_safe(json.dumps(value, cls=DjangoJSONEncoder).translate(_JSON_SCRIPT_ESCAPES))
