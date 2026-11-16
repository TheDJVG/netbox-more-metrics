from django.core.validators import RegexValidator, ValidationError
from django.utils.regex_helper import _lazy_re_compile
from django.utils.translation import gettext_lazy as _

metric_name_re = _lazy_re_compile(r"^[a-zA-Z_:][a-zA-Z0-9_:]*\Z")
metric_name_validator = RegexValidator(
    metric_name_re,
    _("Enter a valid “metric_name” consisting of letters, numbers, colons, or underscores."),
    "invalid",
)
validate_metric_name = metric_name_validator

label_name_re = _lazy_re_compile(r"^[a-zA-Z_][a-zA-Z0-9_]*\Z")
_label_name_regex_validator = RegexValidator(
    label_name_re,
    _("Enter a valid “label_name” consisting of letters, numbers or underscores."),
    "invalid",
)


def validate_label_name(value):
    _label_name_regex_validator(value)
    if value.startswith("__"):
        raise ValidationError(
            _("Label names starting with '__' are reserved for internal use."),
            code="reserved",
        )


label_name_validator = validate_label_name


def validate_labels(value):
    """
    Make sure we don't have duplicate labels.
    """
    if not isinstance(value, list):
        raise ValidationError(
            _("Invalid data type: %(value)s. Expected a list."),
            params={"value": value},
        )

    seen_label_names = set()
    for val in value:
        if val in seen_label_names:
            raise ValidationError(
                _("Duplicate label: %(val)s."),
                params={"val": val},
            )
        seen_label_names.add(val)


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
