def can_view_cost(user):

    return (
        user.is_superuser
        or user.groups.filter(
            name__in=[
                "Finance",
                "Procurement"
            ]
        ).exists()
    )