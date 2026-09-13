# accounts/templatetags/branch_tags.py
from django import template
from accounts.models.org import Branch  # matches your project structure

register = template.Library()

@register.filter
def branch_name(branch_id):
    """
    Given a branch ID, return its name. If not found, return 'Unknown'.
    Usage: {{ request.session.active_branch_id|branch_name }}
    """
    if not branch_id:
        return "Unknown"
    try:
        return Branch.objects.get(pk=branch_id).name
    except Branch.DoesNotExist:
        return "Unknown"
