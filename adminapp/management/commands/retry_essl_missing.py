import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from adminapp.models import Tenant, BiometricEmployeeMapping
from adminapp.essl_service import get_employee_codes, get_employee_details


class Command(BaseCommand):
    help = "Retry missing eSSL employee mappings"

    def handle(self, *args, **options):
        tenant = Tenant.objects.get(pk=1)

        all_codes = set(get_employee_codes())

        saved_codes = set(
            BiometricEmployeeMapping.objects.filter(
                tenant=tenant
            ).values_list("essl_employee_code", flat=True)
        )

        missing_codes = sorted(all_codes - saved_codes)

        self.stdout.write(
            f"Total codes: {len(all_codes)} | Missing: {len(missing_codes)}"
        )

        failed_codes = []

        for index, code in enumerate(missing_codes, start=1):
            success = False

            for attempt in range(1, 4):
                try:
                    details = get_employee_details(code)

                    BiometricEmployeeMapping.objects.update_or_create(
                        tenant=tenant,
                        essl_employee_code=str(code),
                        defaults={
                            "essl_employee_name": details.get("name", "").strip(),
                            "last_synced_at": timezone.now(),
                            "is_active": True,
                        },
                    )

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"[{index}/{len(missing_codes)}] Synced {code}"
                        )
                    )
                    success = True
                    break

                except Exception as exc:
                    self.stderr.write(
                        f"Code {code}, attempt {attempt}/3: {exc}"
                    )
                    if attempt < 3:
                        time.sleep(2)

            if not success:
                failed_codes.append(str(code))

            time.sleep(0.2)

        self.stdout.write("")
        self.stdout.write(f"Retry complete. Failed: {len(failed_codes)}")
        self.stdout.write(f"Failed codes: {failed_codes}")

        count = BiometricEmployeeMapping.objects.filter(
            tenant=tenant
        ).count()
        self.stdout.write(f"Total mappings now: {count}")