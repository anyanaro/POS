from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .forms import CustomUserCreationForm, CustomAuthenticationForm
from django.utils.http import url_has_allowed_host_and_scheme
from django import template
from accounts.models.org import Branch

register = template.Library()




def home_redirect(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    else:
        return redirect("login")


@login_required
def home_view(request):
    return render(request, "accounts/home.html")


# ❌ Do NOT protect register
def register_view(request):
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Registration received. An administrator must approve your account before you can sign in.")
            return redirect("accounts:login")
    else:
        form = CustomUserCreationForm()
    return render(request, "accounts/register.html", {"form": form})


# ❌ Do NOT protect login
def login_view(request):

    # If already authenticated, go to dashboard
    if request.user.is_authenticated:
        branch = get_user_default_branch(request.user)
        if branch:
            request.session["active_branch_id"] = branch.id
        else:
            messages.warning(request, "Your account has no branch assigned. Please contact admin.")
        return redirect("accounts:dashboard")

    if request.method == "POST":
        form = CustomAuthenticationForm(data=request.POST)

        if form.is_valid():
            user = form.get_user()
            login(request, user)

            # --- Set active branch after login ---
            branch = get_user_default_branch(user)
            if branch:
                request.session["active_branch_id"] = branch.id
            else:
                # user has no branches; block selling
                messages.warning(request, "Your account has no branch assigned. Please contact admin.")
                return redirect("accounts:dashboard")

            # Handle ?next= redirect
            next_url = request.GET.get("next")
            if next_url and url_has_allowed_host_and_scheme(
                url=next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                if next_url.startswith("/login"):
                    return redirect("accounts:dashboard")
                return redirect(next_url)

            return redirect("accounts:dashboard")

        messages.error(request, "Invalid username or password.")

    else:
        form = CustomAuthenticationForm()

    return render(request, "accounts/login.html", {"form": form})



@login_required
def logout_view(request):
    logout(request)
    return redirect("accounts:login")

@login_required
def dashboard_view(request):
    # You can pass context if needed
    return render(request, "dashboard.html")

def get_user_default_branch(user):
    # Try default
    default_link = user.branch_links.filter(is_default=True).select_related("branch").first()
    if default_link:
        return default_link.branch

    # Fallback: use the first assigned branch
    any_link = user.branch_links.select_related("branch").first()
    if any_link:
        return any_link.branch

    # User has no branches
    return None


@register.filter
def branch_name(branch_id):
    try:
        return Branch.objects.get(pk=branch_id).name
    except Branch.DoesNotExist:
        return "Unknown"


