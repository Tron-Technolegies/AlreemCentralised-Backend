
from pathlib import Path
from datetime import datetime, date
from uuid import uuid4
import re

from openpyxl import load_workbook

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from adminapp.models import Member


# Excel column name : Django model field name
# Excel MBID is stored in Member.mbid, NOT Member.id.
COLUMN_MAPPING = {
    "MBID": "mbid",
    "MBNAME": "name",
    "MBPHONE1": "phone",
    "MBEMAIL": "email",
    "MBGENDER": "gender",
    "MBAGE": "age",
    "MBJOINDT": "join_date",
    "MBDUEDT": "expiry_date",  # NEW FIELD
    "MBADDR1": "location",
}


def normalize_id(value):
    if value is None:
        return None

    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    return str(value).strip()


def normalize_phone(value):
    """Normalize phone numbers for matching."""
    if value is None:
        return ""

    if isinstance(value, float) and value.is_integer():
        value = str(int(value))

    digits = re.sub(r"\D", "", str(value))

    # Handle Indian numbers with country code.
    if len(digits) >= 10:
        return digits[-10:]

    return digits


def normalize_name(value):
    """Ignore spaces, dots and other punctuation while matching names."""
    if value is None:
        return ""

    return re.sub(
        r"[^a-z0-9]",
        "",
        str(value).strip().lower()
    )


def convert_value(value, field):
    if value is None or str(value).strip() == "":
        return None

    field_type = field.get_internal_type()

    # UPDATED: Handle both join_date and expiry_date.
    if field.name in ("join_date", "expiry_date"):
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d")

        if isinstance(value, date):
            return value.strftime("%Y-%m-%d")

        return str(value).strip()

    if field.name == "age":
        return int(float(value))

    if field.name == "phone":
        if isinstance(value, float) and value.is_integer():
            return str(int(value))

        return str(value).strip()

    if field_type in ("IntegerField", "BigIntegerField"):
        return int(float(value))

    if field_type == "FloatField":
        return float(value)

    if field_type == "BooleanField":
        return str(value).strip().lower() in (
            "true", "1", "yes"
        )

    if field_type == "DateField":
        if isinstance(value, datetime):
            return value.date()

        if isinstance(value, date):
            return value

        return value

    if field_type == "DateTimeField":
        return value

    return str(value).strip()


class Command(BaseCommand):

    help = "Import members from Excel using MBID as the external member ID"

    def add_arguments(self, parser):
        parser.add_argument(
            "excel_file",
            type=str,
            help="Path to the Excel file"
        )

        parser.add_argument(
            "--tenant-id",
            type=int,
            required=True,
            help="Tenant ID"
        )

    @transaction.atomic
    def handle(self, *args, **options):

        excel_file = Path(options["excel_file"])
        tenant_id = options["tenant_id"]

        if not excel_file.exists():
            raise CommandError(
                f"Excel file not found: {excel_file}"
            )

        # Validate tenant
        try:
            tenant_field = Member._meta.get_field("tenant")
            tenant_model = tenant_field.remote_field.model
            tenant = tenant_model.objects.get(pk=tenant_id)

        except Exception as e:
            raise CommandError(
                f"Invalid tenant ID {tenant_id}: {e}"
            )

        # Validate MBID field
        try:
            Member._meta.get_field("mbid")
        except Exception:
            raise CommandError(
                "Member model does not contain the mbid field. "
                "Check your migration."
            )

        workbook = load_workbook(
            filename=excel_file,
            data_only=True
        )

        worksheet = workbook.active

        # Read Excel headers
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

        self.stdout.write(
            self.style.SUCCESS(
                f"Excel headers: {headers}"
            )
        )

        required_columns = [
            "MBID",
            "MBNAME",
            "MBPHONE1"
        ]

        for column in required_columns:
            if column not in headers:
                raise CommandError(
                    f"Required Excel column missing: {column}"
                )

        # Prepare model field mapping
        field_mapping = {}

        for excel_column, model_field in COLUMN_MAPPING.items():

            if excel_column in headers:
                field_mapping[model_field] = (
                    excel_column,
                    Member._meta.get_field(model_field)
                )

        # Load existing members for this tenant once.
        # This avoids repeatedly querying the database.
        existing_members = list(
            Member.objects.filter(tenant=tenant)
        )

        # Build lookup dictionaries.
        mbid_lookup = {}
        identity_lookup = {}

        for member in existing_members:

            if member.mbid:
                key = str(member.mbid).strip()
                mbid_lookup.setdefault(key, []).append(member)

            phone_key = normalize_phone(member.phone)
            name_key = normalize_name(member.name)

            if phone_key and name_key:
                identity_key = (name_key, phone_key)

                identity_lookup.setdefault(
                    identity_key, []
                ).append(member)

        imported_count = 0
        updated_count = 0
        skipped_count = 0

        processed_ids = set()

        self.stdout.write(
            self.style.WARNING(
                f"Starting import for Tenant {tenant_id}"
            )
        )

        for row_number, row in enumerate(
            worksheet.iter_rows(
                min_row=2,
                values_only=True
            ),
            start=2
        ):

            if not any(
                value is not None and str(value).strip()
                for value in row
            ):
                continue

            excel_data = dict(zip(headers, row))

            # Excel MBID is the external member ID.
            excel_id = normalize_id(
                excel_data.get("MBID")
            )

            name = str(
                excel_data.get("MBNAME") or ""
            ).strip()

            phone = normalize_phone(
                excel_data.get("MBPHONE1")
            )

            if not excel_id:
                skipped_count += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Row {row_number}: MBID missing"
                    )
                )
                continue

            if excel_id in processed_ids:
                skipped_count += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Row {row_number}: Duplicate MBID "
                        f"{excel_id} in Excel"
                    )
                )
                continue

            processed_ids.add(excel_id)

            if not name or not phone:
                skipped_count += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Row {row_number}: Name or phone missing"
                    )
                )
                continue

            # ---------------------------------------------
            # STEP 1: Find member using existing MBID
            # ---------------------------------------------
            mbid_matches = mbid_lookup.get(
                excel_id, []
            )

            if len(mbid_matches) > 1:
                skipped_count += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Row {row_number}: Multiple members "
                        f"already have MBID {excel_id}"
                    )
                )
                continue

            member = (
                mbid_matches[0]
                if mbid_matches
                else None
            )

            # ---------------------------------------------
            # STEP 2: Match existing member by name + phone
            # ---------------------------------------------
            if member is None:

                identity_key = (
                    normalize_name(name),
                    phone
                )

                matching_members = identity_lookup.get(
                    identity_key, []
                )

                if len(matching_members) > 1:
                    skipped_count += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"Row {row_number}: Multiple existing "
                            f"members match {name} - {phone}"
                        )
                    )
                    continue

                if len(matching_members) == 1:
                    member = matching_members[0]

            # ---------------------------------------------
            # STEP 3: Update existing member MBID only
            # ---------------------------------------------
            if member is not None:

                if member.mbid and str(
                    member.mbid
                ).strip() != excel_id:

                    skipped_count += 1

                    self.stdout.write(
                        self.style.WARNING(
                            f"Row {row_number}: MBID conflict "
                            f"for {member.name}. "
                            f"Existing: {member.mbid}, "
                            f"Excel: {excel_id}"
                        )
                    )
                    continue

                if not member.mbid:

                    member.mbid = excel_id

                    member.save(
                        update_fields=["mbid"]
                    )

                    updated_count += 1

                    mbid_lookup.setdefault(
                        excel_id, []
                    ).append(member)

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Updated MBID: {member.name} | "
                            f"Django ID: {member.id} | "
                            f"Excel MBID: {excel_id}"
                        )
                    )

                else:
                    skipped_count += 1

                    self.stdout.write(
                        f"Already linked: {member.name} | "
                        f"MBID: {excel_id}"
                    )

                continue

            # ---------------------------------------------
            # STEP 4: Create new member if no match exists
            # ---------------------------------------------
            member_data = {
                "id": str(uuid4()),
                "tenant_id": tenant.pk,
            }

            for model_field, (
                excel_column,
                field
            ) in field_mapping.items():

                value = convert_value(
                    excel_data.get(excel_column),
                    field
                )

                # Skip missing values for non-null fields.
                # Model defaults will apply where available.
                if value is None and not field.null:
                    continue

                member_data[field.attname] = value

            try:
                new_member = Member.objects.create(
                    **member_data
                )

                imported_count += 1

                # Add newly created member to lookups.
                mbid_lookup.setdefault(
                    excel_id, []
                ).append(new_member)

                identity_key = (
                    normalize_name(name),
                    phone
                )

                identity_lookup.setdefault(
                    identity_key, []
                ).append(new_member)

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Imported: {name} | "
                        f"Django ID: {new_member.id} | "
                        f"Excel MBID: {excel_id}"
                    )
                )

            except Exception as e:
                raise CommandError(
                    f"Error importing row {row_number}, "
                    f"MBID {excel_id}: {e}"
                )

        workbook.close()

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "Member import completed!"
            )
        )

        self.stdout.write(
            f"New members imported: {imported_count}"
        )

        self.stdout.write(
            f"Existing members updated with MBID: {updated_count}"
        )

        self.stdout.write(
            f"Skipped: {skipped_count}"
        )
