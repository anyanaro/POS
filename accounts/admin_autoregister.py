# accounts/admin_autoregister.py  (optional helper)
from django.apps import apps
from django.contrib import admin
from accounts.admin_site import my_admin_site

def autoregister_all_models():
    for model in apps.get_models():
        try:
            my_admin_site.register(model)
        except admin.sites.AlreadyRegistered:
            pass