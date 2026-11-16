
import pandas as pd
import binascii
from io import BytesIO
from PIL import Image
from collections import Counter
import hashlib

df = pd.read_excel("project/members.xlsx")

images = []

for _, row in df.iterrows():
    value = row["MBPHOTO"]

    if pd.isna(value):
        continue

    try:
        hex_data = str(value).strip()

        if hex_data.lower().startswith("0x"):
            hex_data = hex_data[2:]

        image_bytes = binascii.unhexlify(hex_data)

        img = Image.open(BytesIO(image_bytes))
        img.verify()

        img = Image.open(BytesIO(image_bytes))

        images.append({
            "size": img.size,
            "bytes": len(image_bytes),
            "hash": hashlib.md5(image_bytes).hexdigest()
        })

    except Exception:
        pass

print("Valid images:", len(images))
print("Unique images:", len(set(x["hash"] for x in images)))
print("Dimensions:", Counter(x["size"] for x in images))
