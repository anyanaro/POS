
def is_procurement(user):

    return user.groups.filter(
        name="PROCUREMENT"
    ).exists()
    
def is_finance(user):

    return user.groups.filter(
        name="FINANCE"
    ).exists()

def can_view_cost(user):

    if user.is_superuser:
        return True

    return (
        is_procurement(user)
        or is_finance(user)
    )