from django.db import models
from django.contrib.auth.models import User

class Profile(models.Model):
    EXEC = "EXECUTIVE"
    MGR = "MANAGER"
    SPA = "SUPER_ADMIN"
    PRC = "PROCUREMENT"
    FN = "FINANCE"
    STU  = "STORE_USER"

    ROLE_CHOICES = [
        (EXEC, "Executive"),
        (MGR,  "Store Manager"),
        (SPA,  "Super_Admin"),
        (PRC,  "Procurement"),
        (FN,  "Finance"),
        (STU,  "Store_User"),        

    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile"
    )

    # Personal fields
    full_name = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)

    # Role field (merged from UserProfile)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=MGR)

    def __str__(self):
        return f"{self.user.username} ({self.role})"