import re
import sys

from django.conf import settings


def enable_metrics():
    if hasattr(settings, "METRICS_ENABLED") and not settings.METRICS_ENABLED:
        return False

    # Enable metrics on the devserver
    if "runserver" in sys.argv:
        return True

    # Enable metrics if not running manage.py.
    regex = re.compile(r"(?:\.\/)?manage\.py", flags=re.IGNORECASE)
    if not any(filter(regex.match, sys.argv)):
        return True

    return False
