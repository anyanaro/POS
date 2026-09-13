from django import forms
from accounts.models.Insurance import (
    Insurance,
    InsuranceScheme
)

class InsuranceForm(forms.ModelForm):
    class Meta:
        model = Insurance
        fields = "__all__"
        widgets = {
            "bc_number": forms.TextInput(attrs={"class": "form-control"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "contact_person": forms.TextInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "address": forms.Textarea(attrs={"class": "form-control"}),
            "remarks": forms.Textarea(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # ✅ If creating new object → default to active
        if not self.instance.pk:
            self.fields["is_active"].initial = True