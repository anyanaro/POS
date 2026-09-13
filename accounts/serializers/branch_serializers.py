from rest_framework import serializers
from accounts.models.org import Branch, UserBranch

class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ["id", "code", "name", "address", "active"]

class UserBranchSerializer(serializers.ModelSerializer):
    branch = BranchSerializer(read_only=True)

    class Meta:
        model = UserBranch
        fields = ["id", "branch", "is_default"]

class SwitchBranchSerializer(serializers.Serializer):
    branch_code = serializers.CharField(max_length=10)