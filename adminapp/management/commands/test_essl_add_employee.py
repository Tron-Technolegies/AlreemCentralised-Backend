from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from adminapp.essl_service import add_essl_employee


class Command(BaseCommand):
    help = "Test adding an employee to eSSL"

    def add_arguments(self, parser):
        parser.add_argument("--code", required=True)
        parser.add_argument("--name", default="API TEST USER")
        parser.add_argument("--location", default=None)

    def handle(self, *args, **options):
        code = options["code"].strip()
        name = options["name"].strip()
        location = (
            options["location"]
            or settings.ESSL_EMPLOYEE_LOCATION
        )

        if not code or not name or not location:
            raise CommandError(
                "Employee code, name and location are required."
            )

        self.stdout.write(
            f"Testing eSSL employee creation: {code}"
        )

        try:
            result = add_essl_employee(
                employee_code=code,
                employee_name=name,
                employee_location=location,
            )
        except Exception as exc:
            raise CommandError(
                f"eSSL request failed: {exc}"
            ) from exc

        self.stdout.write(
            self.style.WARNING(
                f"Raw eSSL response: {result!r}"
            )
        )
        self.stdout.write(
            "Verify this employee in eBioServer and on the device."
        )