
from pathlib import Path
from datetime import datetime, date

from openpyxl import load_workbook

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from adminapp.models import Member


class Command(BaseCommand):

    help = "Update only expiry dates using MBID from Excel"

    def add_arguments(self, parser):
        parser.add_argument(
            "excel_file",
            type=str,
            help="Excel file path"
        )

        parser.add_argument(
            "--tenant-id",
            type=int,
            required=True
        )

    @transaction.atomic
    def handle(self, *args, **options):

        excel_file = Path(options["excel_file"])
        tenant_id = options["tenant_id"]

        if not excel_file.exists():
            raise CommandError(
                f"Excel file not found: {excel_file}"
            )

        try:
            tenant = Member._meta.get_field(
                "tenant"
            ).remote_field.model.objects.get(
                pk=tenant_id
            )
        except Exception as e:
            raise CommandError(
                f"Invalid tenant: {e}"
            )

        workbook = load_workbook(
            filename=excel_file,
            data_only=True
        )

        worksheet = workbook.active

        headers = [
            str(cell).strip() if cell is not None else ""
            for cell in next(
                worksheet.iter_rows(
                    min_row=1,
                    max_row=1,
                    values_only=True
                )
            )
        ]

        if "MBID" not in headers:
            raise CommandError("MBID column missing")

        if "MBDUEDT" not in headers:
            raise CommandError("MBDUEDT column missing")

        updated_count = 0
        skipped_count = 0
        not_found_count = 0

        mbid_index = headers.index("MBID")
        expiry_index = headers.index("MBDUEDT")

        self.stdout.write(
            self.style.WARNING(
                f"Updating expiry dates for tenant {tenant_id}"
            )
        )

        for row_number, row in enumerate(
            worksheet.iter_rows(
                min_row=2,
                values_only=True
            ),
            start=2
        ):

            mbid = row[mbid_index]
            expiry_value = row[expiry_index]

            if mbid is None or str(mbid).strip() == "":
                skipped_count += 1
                continue

            if isinstance(mbid, float) and mbid.is_integer():
                mbid = str(int(mbid))
            else:
                mbid = str(mbid).strip()

            if expiry_value is None or str(expiry_value).strip() == "":
                skipped_count += 1
                continue

            # Convert Excel expiry date
            if isinstance(expiry_value, datetime):
                expiry_date = expiry_value.date()

            elif isinstance(expiry_value, date):
                expiry_date = expiry_value

            elif isinstance(expiry_value, (int, float)):
                from openpyxl.utils.datetime import from_excel

                try:
                    expiry_date = from_excel(
                        expiry_value,
                        workbook.epoch
                    )

                    if isinstance(expiry_date, datetime):
                        expiry_date = expiry_date.date()

                except Exception:
                    raise CommandError(
                        f"Invalid Excel date at row {row_number}: {expiry_value}"
                    )

            else:
                try:
                    expiry_date = datetime.fromisoformat(
                        str(expiry_value).strip()
                    ).date()

                except ValueError:
                    raise CommandError(
                        f"Invalid expiry date at row {row_number}: {expiry_value}"
                    )
            # Find existing member using MBID and tenant
            member = Member.objects.filter(
                tenant=tenant,
                mbid=mbid
            ).first()

            if member is None:
                not_found_count += 1
                continue

            # Update ONLY expiry_date
            Member.objects.filter(
                pk=member.pk
            ).update(
                expiry_date=expiry_date
            )

            updated_count += 1

        workbook.close()

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS("Expiry date import completed!")
        )

        self.stdout.write(
            f"Expiry dates updated: {updated_count}"
        )

        self.stdout.write(
            f"Members not found: {not_found_count}"
        )

        self.stdout.write(
            f"Skipped: {skipped_count}"
        )
