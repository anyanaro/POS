# accounts/views/branch_views.py
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.serializers.branch_serializers import (
    BranchSerializer,
    UserBranchSerializer,
    SwitchBranchSerializer
)
from accounts.models.org import Branch, UserBranch

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

@login_required
def returns_list(request):

    return render(
        request,
        "accounts/branch/returns.html"
    )

@login_required
def stock_receipts(request):

    from accounts.models.procurement_execution import GoodsReceipt

    receipts = GoodsReceipt.objects.select_related(
        "branch"
    ).order_by("-received_at")

    return render(
        request,
        "accounts/branch/stock_receipts.html",
        {
            "receipts": receipts
        }
    )
    
class UserBranchesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_branches = UserBranch.objects.filter(user=request.user).select_related("branch")
        return Response(UserBranchSerializer(user_branches, many=True).data)


class SwitchBranchView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = SwitchBranchSerializer(data=request.data)
        data.is_valid(raise_exception=True)

        code = data.validated_data["branch_code"]

        try:
            branch = Branch.objects.get(code=code, active=True)
        except Branch.DoesNotExist:
            return Response({"detail": "Branch not found"}, status=404)

        # Ensure user allowed
        if not UserBranch.objects.filter(user=request.user, branch=branch).exists():
            return Response({"detail": "Not allowed"}, status=403)

        request.session["active_branch_code"] = branch.code

        return Response({"active_branch": branch.code})