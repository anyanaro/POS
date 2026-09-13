from django import forms
from accounts.models.Insurance import (
    Insurance,
    InsuranceScheme
)

class InsuranceSchemeForm(forms.ModelForm):
    class Meta:
        model = InsuranceScheme
        fields = "__all__"
        widgets = {
            "insurance": forms.Select(attrs={"class": "form-select"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
        }