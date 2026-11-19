
import os
import re
import pandas as pd

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from adminapp.models import Plan, Tenant


class Command(BaseCommand):
    help = "Import GymCare schemes into Django Plan model"

    def add_arguments(self, parser):
        parser.add_argument("file_path", type=str)
        parser.add_argument("--tenant-id", type=int, required=True)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):

        file_path = options["file_path"]
        tenant_id = options["tenant_id"]
        dry_run = options["dry_run"]

        if not os.path.exists(file_path):
            raise CommandError(f"File not found: {file_path}")

        if not Tenant.objects.filter(id=tenant_id).exists():
            raise CommandError(f"Tenant {tenant_id} does not exist")

        # Read Excel without headers
        df = pd.read_excel(
            file_path,
            engine="xlrd",
            header=None
        )

        # Excel column mapping
        NAME_COL = 1
        DURATION_COL = 2
        PRICE_COL = 4
        UNIT_COL = 7

        created = 0
        skipped = 0

        with transaction.atomic():

            for _, row in df.iterrows():

                if pd.isna(row[NAME_COL]) or pd.isna(row[DURATION_COL]):
                    skipped += 1
                    continue

                name = str(row[NAME_COL]).strip()

                try:
                    duration = int(row[DURATION_COL])
                    price = float(row[PRICE_COL]) if pd.notna(row[PRICE_COL]) else 0
                except (ValueError, TypeError):
                    skipped += 1
                    continue

                unit = (
                    str(row[UNIT_COL]).strip().lower()
                    if pd.notna(row[UNIT_COL])
                    else ""
                )

                # Infer unit from scheme name if Excel unit is empty
                if not unit:
                    name_lower = name.lower()

                    if "hour" in name_lower:
                        unit = "hour"
                    elif "day" in name_lower:
                        unit = "day"
                    elif "year" in name_lower:
                        unit = "year"
                    elif "month" in name_lower:
                        unit = "month"

                # Convert duration into days
                if unit in ["day", "days"]:
                    pass
                elif unit in ["month", "months"]:
                    duration *= 30
                elif unit in ["year", "years"]:
                    duration *= 365
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Skipped unsupported duration: {name} ({unit})"
                        )
                    )
                    skipped += 1
                    continue

                # Avoid duplicate plans for the same tenant
                exists = Plan.objects.filter(
                    tenant_id=tenant_id,
                    name__iexact=name
                ).exists()

                if exists:
                    self.stdout.write(f"Already exists: {name}")
                    skipped += 1
                    continue

                if not dry_run:
                    Plan.objects.create(
                        tenant_id=tenant_id,
                        name=name,
                        duration=duration,
                        price=price
                    )

                self.stdout.write(
                    f"{'[PREVIEW] ' if dry_run else ''}"
                    f"{name} | {duration} days | ₹{price}"
                )

                created += 1

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(
            f"\nImport completed!"
            f"\nCreated: {created}"
            f"\nSkipped: {skipped}"
        ))
