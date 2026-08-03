# Uploads raw resume files to Cloudinary so the original document (not just
# the parsed data) can be viewed later. Free tier is plenty for this.
import cloudinary
import cloudinary.uploader
from app.core.config import settings

cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True,
)


class CloudinaryClient:

    def upload_resume_file(self, file_bytes: bytes, filename: str) -> str | None:
        """
        Uploads a resume file (PDF/DOCX) and returns its permanent URL.
        Returns None (doesn't raise) if Cloudinary isn't configured or the
        upload fails — a resume upload should still succeed even if file
        storage is unavailable, it just won't have a viewable original.
        resource_type="raw" is required for non-image files like PDF/DOCX;
        Cloudinary defaults to expecting images otherwise.
        """
        if not settings.CLOUDINARY_CLOUD_NAME:
            print("[Cloudinary] Not configured (CLOUDINARY_CLOUD_NAME unset) — skipping file upload.")
            return None
        try:
            result = cloudinary.uploader.upload(
                file_bytes,
                resource_type="raw",
                folder="resumes",
                public_id=filename,
                overwrite=True,
                unique_filename=True,
            )
            return result.get("secure_url")
        except Exception as e:
            print(f"[Cloudinary] Upload failed for {filename!r}: {e}")
            return None


cloudinary_client = CloudinaryClient()
