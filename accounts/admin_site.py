# accounts/admin_site.py
from django.contrib.admin import AdminSite

class MyAdminSite(AdminSite):
    site_header = "POS Admin"
    site_title = "POS Admin"
    index_title = "Dashboard"

    def index(self, request, extra_context=None):
        extra_context = extra_context or {}
        from accounts import admin_dashboard
        extra_context.update(admin_dashboard.pos_dashboard(request))
        return super().index(request, extra_context=extra_context)

# Create a singleton instance you can use in urls
my_admin_site = MyAdminSite(name="my_admin")