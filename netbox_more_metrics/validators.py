from django.core.validators import RegexValidator
from django.utils.regex_helper import _lazy_re_compile
from django.utils.translation import gettext_lazy as _

metric_name_re = _lazy_re_compile(r"^[a-zA-Z_][a-zA-Z0-9_]+\Z")
validate_metric_name = RegexValidator(
    metric_name_re,
    _("Enter a valid “metric_name” consisting of letters, numbers or underscores."),
    "invalid",
)

label_name_re = _lazy_re_compile(r"^[a-zA-Z_][a-zA-Z0-9_]+\Z")
validate_label_name = RegexValidator(
    label_name_re,
    _("Enter a valid “label_name” consisting of letters, numbers or underscores."),
    "invalid",
)
