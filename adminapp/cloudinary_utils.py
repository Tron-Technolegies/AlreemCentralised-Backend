# import cloudinary.uploader


# def upload_exercise_gif(
#     file_path,
#     exercise_name
# ):

#     safe_name = (
#         exercise_name
#         .lower()
#         .replace(" ", "_")
#         # .replace("/", "_")
#     )

#     result = cloudinary.uploader.upload(
#         file_path,
#         resource_type="video",
#         public_id=f"exercise_gifs/{safe_name}",
#         overwrite=True
#     )

#     return result.get("secure_url")