import dateutil.parser
from django import template

register = template.Library()


@register.filter(name="parse_date")
def parse_date(value):
    return value
    return dateutil.parser.isoparse(value)
