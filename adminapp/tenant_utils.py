from .models import Tenant


def get_tenant(request):
    user = request.user

    if user.role == "SUPER_ADMIN":

        tenant_id = (
            request.data.get("tenant_id")
            or request.query_params.get("tenant_id")
        )

        if tenant_id:

            try:
                return Tenant.objects.get(
                    id=tenant_id,
                    is_active=True
                )

            except Tenant.DoesNotExist:
                return None

        return None

    if not user.tenant_id:
        return None

    if not user.tenant.is_active:
        return None

    return user.tenant


def get_branch_filter(request, tenant):

    user = request.user

    if user.role in [
        "SUPER_ADMIN",
        "TENANT_ADMIN"
    ]:
        return {}

    if user.role in [
        "BRANCH_ADMIN",
        "STAFF"
    ]:

        if not user.branch_id:
            return {
                "branch_id": -1
            }

        return {
            "branch_id": user.branch_id
        }

    return {
        "branch_id": -1
    }