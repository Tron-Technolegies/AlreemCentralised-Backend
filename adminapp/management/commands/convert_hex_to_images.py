import re
from pathlib import Path
from openpyxl import load_workbook

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]

EXCEL_FILE = BASE_DIR / "project" / "members.xlsx"
OUTPUT_DIR = BASE_DIR / "converted_photos"
OUTPUT_DIR = Path("converted_photos")

OUTPUT_DIR.mkdir(exist_ok=True)

workbook = load_workbook(EXCEL_FILE, read_only=True, data_only=True)
sheet = workbook.active

headers = [cell.value for cell in sheet[1]]

id_index = headers.index("MBID")
photo_index = headers.index("MBPHOTO")

converted = 0
failed = 0

for row_number, row in enumerate(
    sheet.iter_rows(min_row=2, values_only=True), start=2
):
    member_id = row[id_index]
    raw_photo = row[photo_index]

    if not member_id or not raw_photo:
        continue

    photo_hex = str(raw_photo).strip()

    if photo_hex.lower().startswith("0x"):
        photo_hex = photo_hex[2:]

    photo_hex = re.sub(r"\s+", "", photo_hex)

    try:
        if len(photo_hex) % 2 != 0:
            raise ValueError("Odd number of hexadecimal characters")

        photo_bytes = bytes.fromhex(photo_hex)

        if not photo_bytes.startswith(b"\xff\xd8"):
            raise ValueError("Not a JPEG image")

        if not photo_bytes.endswith(b"\xff\xd9"):
            raise ValueError("Incomplete JPEG image")

        filename = OUTPUT_DIR / f"{member_id}.jpg"
        filename.write_bytes(photo_bytes)

        converted += 1
        print(f"Converted: {member_id}")

    except ValueError as error:
        failed += 1
        print(f"Skipped Excel row {row_number}: {error}")

print("\nConversion completed")
print(f"Successfully converted: {converted}")
print(f"Failed/skipped: {failed}")