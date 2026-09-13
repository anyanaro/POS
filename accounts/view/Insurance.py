
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from accounts.models.Insurance import (
    Insurance,
    InsuranceScheme
)

from accounts.form.Insurance import InsuranceForm
from accounts.form.InsuranceScheme import InsuranceSchemeForm

@login_required
def insurance_schemes_by_insurance(request):
    insurance_id = request.GET.get("insurance_id")
    schemes = InsuranceScheme.objects.filter(
        insurance_id=insurance_id,
        is_active=True
    ).values("id", "name")

    return JsonResponse(list(schemes), safe=False)

@login_required
def insurance_list(request):
    insurances = Insurance.objects.order_by("name")
    return render(
        request,
        "accounts/insurance/insurance_list.html",
        {
            "insurances": insurances
        }
    )

@login_required
def insurance_create(request):
    if request.method == "POST":
        form = InsuranceForm(request.POST)
        if form.is_valid():
            form.save()  # ✅ clean and safe
            return redirect("accounts:insurance_list")
        else:
            print(form.errors)  # ✅ DEBUG
    else:
        form = InsuranceForm()

    return render(
        request,
        "accounts/insurance/forms/insurance_form.html",
        {
            "form": form,
            "mode": "create",
        }
    )

    
@login_required
def insurance_edit(request, pk):
    insurance = get_object_or_404(Insurance, pk=pk)

    if request.method == "POST":
        form = InsuranceForm(request.POST, instance=insurance)
        if form.is_valid():
            print("POST DATA2:", request.POST)
            form.save()
            return redirect("accounts:insurance_list")
        else:
            print(form.errors)  # ✅ DEBUG
    else:
        form = InsuranceForm(instance=insurance)

    return render(
        request,
        "accounts/insurance/forms/insurance_form.html",
        {
            "form": form,
            "mode": "edit",
        }
    )
    

    
@login_required
def insurance_scheme_list(request):
    schemes = (
        InsuranceScheme.objects
        .select_related("insurance")
        .order_by("insurance__name", "name")
    )

    return render(
        request,
        "accounts/insurance/insurance_scheme_list.html",
        {
            "schemes": schemes
        }
    )
    
    
@login_required
def insurance_scheme_create(request):
    if request.method == "POST":
        form = InsuranceSchemeForm(request.POST)
        if form.is_valid():
            scheme = form.save(commit=False)
            scheme.is_active = True  # ✅ CRITICAL
            scheme.save()
            return redirect("accounts:insurance_scheme_list")
    else:
        form = InsuranceSchemeForm()

    return render(
        request,
        "accounts/insurance/forms/insurance_scheme_form.html",
        {
            "form": form,
            "mode": "create",
        }
    )



@login_required
def insurance_scheme_edit(request, pk):
    scheme = get_object_or_404(InsuranceScheme, pk=pk)

    if request.method == "POST":
        form = InsuranceSchemeForm(request.POST, instance=scheme)
        if form.is_valid():
            form.save()
            return redirect("accounts:insurance_scheme_list")
    else:
        form = InsuranceSchemeForm(instance=scheme)

    return render(
        request,
        "accounts/insurance/forms/insurance_scheme_form.html",
        {
            "form": form,
            "mode": "edit",
        }
    )