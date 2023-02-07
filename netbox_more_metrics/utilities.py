import re
import sys


def enable_metrics():
    # Enable metrics on the devserver
    if "runserver" in sys.argv:
        return True

    # Enable metrics if not running manage.py.
    regex = re.compile(r"(?:\.\/)?manage\.py", flags=re.IGNORECASE)
    if not any(filter(regex.match, sys.argv)):
        return True

    return False
