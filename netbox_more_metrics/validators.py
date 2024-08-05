from django.core.validators import RegexValidator, ValidationError
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


def validate_label_renames(value):
    """
    Validator to ensure that the JSONField only contains key-value pairs where both keys and values are strings.
    Nested structures are not allowed.
    """
    if not isinstance(value, dict):
        raise ValidationError(
            _("Invalid data type: %(value)s. Expected a dictionary."),
            params={"value": value},
        )

    seen_label_names = set()
    for key, val in value.items():
        if not isinstance(key, str):
            raise ValidationError(
                _("Invalid key type: %(key)s. Expected a string."),
                params={"key": key},
            )
        if not isinstance(val, str):
            raise ValidationError(
                _("Invalid value type for key '%(key)s': %(val)s. Expected a string."),
                params={"key": key, "val": val},
            )

        if val in seen_label_names:
            raise ValidationError(
                _("Duplicate label name: %(val)s."),
                params={"val": val},
            )

        # Add the label name to the set of seen label names
        seen_label_names.add(val)

        # Check if the value is a valid label name
        validate_label_name(val)
