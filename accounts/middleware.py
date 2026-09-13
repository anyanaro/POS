# accounts/middleware.py
from accounts.models.org import Branch, UserBranch

class ActiveBranchMiddleware:
    """
    Sets request.active_branch from (in order of priority):
    1. X-Branch-Code header
    2. session["active_branch_code"]
    3. user's default branch

    If nothing found → request.active_branch = None
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        branch_code = (
            request.headers.get("X-Branch-Code")
            or request.session.get("active_branch_code")
        )

        request.active_branch = None

        if branch_code:
            try:
                request.active_branch = Branch.objects.get(
                    code=branch_code, active=True
                )
            except Branch.DoesNotExist:
                request.active_branch = None

        # fallback: user default branch
        if request.user.is_authenticated and request.active_branch is None:
            default = UserBranch.objects.filter(
                user=request.user, is_default=True
            ).first()
            if default:
                request.active_branch = default.branch

        return self.get_response(request)