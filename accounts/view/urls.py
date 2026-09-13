# accounts/view/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = "accounts"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("sales/", views.sales, name="sales"),
    path("products/", views.products, name="products"),
    path("inventory/", views.inventory, name="inventory"),
    path("reports/", views.reports, name="reports"),
    

    # Auth (built-in)
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="accounts/login.html"),
        name="login",
    ),
    path(
        "logout/",
        auth_views.LogoutView.as_view(next_page="accounts:login"),
        name="logout",
    ),
]
