from django.core.management.base import BaseCommand
from adminapp.views import retry_pending_essl_registrations
from adminapp.models import Tenant


class Command(BaseCommand):
    help = "Retry pending eSSL employee registrations"

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant-id",
            type=int,
            required=True,
            help="Tenant ID to process",
        )

    def handle(self, *args, **options):
        tenant_id = options["tenant_id"]

        try:
            tenant = Tenant.objects.get(id=tenant_id)
        except Tenant.DoesNotExist:
            self.stderr.write(
                self.style.ERROR(f"Tenant {tenant_id} not found.")
            )
            return

        self.stdout.write(
            f"Retrying pending eSSL registrations for tenant {tenant_id}..."
        )

        results = retry_pending_essl_registrations(tenant=tenant)

        self.stdout.write(
            self.style.SUCCESS(
                f"Finished. Total pending: {results['total']}, "
                f"registered: {results['registered']}, "
                f"failed: {results['failed']}"
            )
        )