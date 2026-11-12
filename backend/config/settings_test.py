"""Postavke za testove: brže lozinke i bez ograničenja pokušaja prijave."""

import os

os.environ.setdefault("DJANGO_DEBUG", "1")

from .settings import *  # noqa: F403
from .settings import REST_FRAMEWORK

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
FRONTEND_URL = "https://racuni.test"
CSRF_TRUSTED_ORIGINS = [FRONTEND_URL]

REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {"login": "1000/hour"}}
