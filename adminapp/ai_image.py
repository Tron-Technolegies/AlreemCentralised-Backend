from django.conf import settings

from huggingface_hub import InferenceClient

from cloudinary import uploader

from io import BytesIO


def generate_exercise_image(exercise):

    # =========================================
    # Hugging Face client
    # =========================================

    client = InferenceClient(
        provider="auto",
        api_key=settings.HF_TOKEN
    )

    # =========================================
    # Equipment
    # =========================================

    equipment = (
        exercise.equipment
        if exercise.equipment
        else "bodyweight"
    )

    # =========================================
    # AI PROMPT
    # =========================================

    prompt = f"""
Create a realistic professional fitness
instructional photograph showing the exercise:

{exercise.name}

Target body part:
{exercise.body_part}

Equipment:
{equipment}

The person must clearly perform the exact exercise:
{exercise.name}

Requirements:

- One adult athlete
- Correct exercise form
- Correct body position
- Correct use of the equipment
- Full exercise movement should be visually understandable
- Professional modern gym
- Realistic human anatomy
- Realistic gym equipment
- Fitness photography style
- Clean background
- High quality
- No text
- No captions
- No labels
- No watermark
- No logos
- No brand names
- No extra people
"""

    negative_prompt = """
text,
words,
letters,
caption,
logo,
watermark,
extra people,
extra arms,
extra legs,
deformed hands,
bad anatomy,
incorrect equipment,
duplicate person
"""

    # =========================================
    # GENERATE IMAGE
    # =========================================

    image = client.text_to_image(
        prompt=prompt,
        negative_prompt=negative_prompt,
        model="black-forest-labs/FLUX.1-schnell",
        width=768,
        height=768
    )

    if image is None:

        raise Exception(
            "Hugging Face did not return an image"
        )

    # =========================================
    # Convert PIL image to bytes
    # =========================================

    image_file = BytesIO()

    image.save(
        image_file,
        format="WEBP",
        quality=85
    )

    image_file.seek(0)

    image_file.name = (
        f"exercise_{exercise.id}.webp"
    )

    # =========================================
    # Upload to Cloudinary
    # =========================================

    upload_result = uploader.upload(
        image_file,
        folder="gym/exercises",
        resource_type="image",
        public_id=f"exercise_{exercise.id}",
        overwrite=True
    )

    # =========================================
    # Return Cloudinary public ID
    # =========================================

    return upload_result["public_id"]