
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand

from adminapp.models import Member


class Command(BaseCommand):
    help = "Upload converted Excel member photos to Cloudinary"

    def add_arguments(self, parser):
        parser.add_argument("--tenant-id", type=int, required=True)
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Replace existing member photos"
        )

    def handle(self, *args, **options):
        base_dir = Path(__file__).resolve().parents[3]
        photo_dir = base_dir / "converted_photos"

        tenant_id = options["tenant_id"]
        overwrite = options["overwrite"]

        if not photo_dir.exists():
            self.stderr.write(f"Photo folder not found: {photo_dir}")
            return

        uploaded = 0
        skipped = 0
        not_found = 0
        failed = 0

        for image_path in photo_dir.iterdir():

            if image_path.suffix.lower() not in [".jpg", ".jpeg"]:
                continue

            member_id = image_path.stem

            try:
                member = Member.objects.filter(
                    id=member_id,
                    tenant_id=tenant_id
                ).first()

                if not member:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Member not found: {member_id}"
                        )
                    )
                    not_found += 1
                    continue

                if member.photo and not overwrite:
                    skipped += 1
                    continue

                with image_path.open("rb") as image_file:
                    uploaded_file = SimpleUploadedFile(
                        name=image_path.name,
                        content=image_file.read(),
                        content_type="image/jpeg"
                    )

                    member.photo = uploaded_file
                    member.save(update_fields=["photo"])

                uploaded += 1

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Uploaded photo for member: {member_id}"
                    )
                )

            except Exception as error:
                failed += 1
                self.stderr.write(
                    f"Failed for {member_id}: {error}"
                )

        self.stdout.write("\nUpload completed")
        self.stdout.write(f"Uploaded: {uploaded}")
        self.stdout.write(f"Already had photos: {skipped}")
        self.stdout.write(f"Members not found: {not_found}")
        self.stdout.write(f"Failed: {failed}")
