# accounts/core_middleware.py
import re
from urllib.parse import quote  # <-- replace urlquote with quote
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

class GlobalLoginRequiredMiddleware:
    """
    Redirects anonymous users to LOGIN_URL, except for exempt paths.
    Prevents loops by NOT redirecting when the current request is already
    at LOGIN_URL, and by ignoring admin/login/reset/static/media paths.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.login_url = reverse(settings.LOGIN_URL)

        patterns = getattr(settings, "LOGIN_REQUIRED_IGNORE_PATHS", [
            r"^/login/?$",
            r"^/logout/?$",
            r"^/register/?$",
            r"^/password_reset/?$",
            r"^/reset/.*$",
            r"^/admin/.*$",
            r"^/static/.*$",
            r"^/media/.*$",
        ])
        self.ignore_paths = [re.compile(p) for p in patterns]

    def __call__(self, request):
        # Be defensive: in some code paths AuthenticationMiddleware may not run
        user = getattr(request, "user", None)
        path = request.path

        # Exempt explicitly
        if any(p.match(path) for p in self.ignore_paths):
            return self.get_response(request)

        # If user is authenticated, allow
        if user is not None and getattr(user, "is_authenticated", False):
            return self.get_response(request)

        # If already at LOGIN_URL, do NOT redirect again (prevents /login -> /login loop)
        if path.rstrip("/") == self.login_url:
            return self.get_response(request)

        # Redirect anonymous to login with a clean `next`
        # Use urllib.parse.quote instead of deprecated django.utils.http.urlquote
        return redirect(f"{self.login_url}?next={quote(path)}")