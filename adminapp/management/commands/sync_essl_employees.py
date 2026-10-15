import time
from django.core.management.base import BaseCommand, CommandError
from adminapp.models import Tenant
from adminapp.essl_service import sync_essl_employees


class Command(BaseCommand):
    help = "Synchronize employee details from eSSL into biometric mappings"

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant-id",
            required=True,
            help="ID of the gym tenant to sync employees into",
        )

    def handle(self, *args, **options):
        tenant_id = options["tenant_id"]

        try:
            tenant = Tenant.objects.get(pk=tenant_id)
        except (Tenant.DoesNotExist, ValueError, TypeError):
            raise CommandError(
                f"Tenant with ID {tenant_id} was not found."
            )

        self.stdout.write(
            f"Starting eSSL sync for tenant ID {tenant.pk}..."
        )

        start_time = time.monotonic()

        try:
            result = sync_essl_employees(tenant=tenant)
        except Exception as exc:
            raise CommandError(f"eSSL sync failed: {exc}") from exc

        elapsed = time.monotonic() - start_time

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("eSSL sync finished"))
        self.stdout.write(f"Total employee codes: {result['total_codes']}")
        self.stdout.write(f"Successfully synced: {result['synced']}")
        self.stdout.write(f"Failed: {result['failed_count']}")
        self.stdout.write(f"Duration: {elapsed:.2f} seconds")

        if result["failed"]:
            self.stdout.write(
                self.style.WARNING("Employees that failed to sync:")
            )
            for item in result["failed"]:
                self.stdout.write(
                    f"  {item['employee_code']}: {item['error']}"
                )