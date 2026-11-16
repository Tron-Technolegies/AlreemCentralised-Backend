
import re
from pathlib import Path

from openpyxl import load_workbook
from django.core.management.base import BaseCommand, CommandError
from django.core.files.base import ContentFile

from adminapp.models import Member


class Command(BaseCommand):
    help = "Import member photos from Excel and upload to Cloudinary"

    def add_arguments(self, parser):
        parser.add_argument("excel_file", type=str)
        parser.add_argument("--tenant-id", type=int, required=True)

    def handle(self, *args, **options):
        excel_file = Path(options["excel_file"])
        tenant_id = options["tenant_id"]

        if not excel_file.exists():
            raise CommandError(f"Excel file not found: {excel_file}")

        workbook = load_workbook(
            excel_file,
            read_only=True,
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

        if "MBID" not in headers or "MBPHOTO" not in headers:
            raise CommandError("MBID or MBPHOTO column is missing")

        mbid_index = headers.index("MBID")
        photo_index = headers.index("MBPHOTO")

        photo_count = 0
        skipped_count = 0

        for row_number, row in enumerate(
            worksheet.iter_rows(min_row=2, values_only=True),
            start=2
        ):
            raw_id = row[mbid_index] if mbid_index < len(row) else None
            raw_photo = row[photo_index] if photo_index < len(row) else None

            if raw_id is None or raw_photo is None:
                skipped_count += 1
                continue

            # Normalize Excel ID
            if isinstance(raw_id, float) and raw_id.is_integer():
                member_id = str(int(raw_id))
            else:
                member_id = str(raw_id).strip()

            try:
                # Decode hexadecimal JPEG data
                photo_hex = str(raw_photo).strip()

                if photo_hex.lower().startswith("0x"):
                    photo_hex = photo_hex[2:]

                photo_hex = re.sub(
                    r"[^0-9a-fA-F]",
                    "",
                    photo_hex
                )

                if len(photo_hex) % 2 != 0:
                    self.stdout.write(f"Excel row: {row_number}")
                    self.stdout.write(f"Member ID raw value: {repr(raw_id)}")
                    self.stdout.write(f"Photo raw type: {type(raw_photo)}")
                    self.stdout.write(f"Photo first 30: {photo_hex[:30]}")
                    self.stdout.write(f"Photo last 30: {photo_hex[-30:]}")
                    self.stdout.write(f"Photo hex length: {len(photo_hex)}")
                    raise ValueError(
                        f"Odd hexadecimal length: {len(photo_hex)}"
                    )

                photo_bytes = bytes.fromhex(photo_hex)

                if not (
                    photo_bytes.startswith(b"\xff\xd8")
                    and photo_bytes.endswith(b"\xff\xd9")
                ):
                    raise ValueError("Invalid or incomplete JPEG data")

                member = Member.objects.get(
                    id=member_id,
                    tenant_id=tenant_id
                )

                member.photo.save(
                    f"member_{member_id}.jpg",
                    ContentFile(photo_bytes),
                    save=True
                )

                photo_count += 1

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Uploaded photo for member {member_id}"
                    )
                )

            except Member.DoesNotExist:
                skipped_count += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Member {member_id} not found"
                    )
                )

            except Exception as e:
                workbook.close()
                raise CommandError(
                    f"Error at Excel row {row_number}, "
                    f"Member ID {member_id}: {e}"
                )

        workbook.close()

        self.stdout.write(
            self.style.SUCCESS(
                f"Photo upload completed! Uploaded: {photo_count}, "
                f"Skipped: {skipped_count}"
            )
        )
