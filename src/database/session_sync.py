import os
import zipfile
import shutil
from pathlib import Path
from typing import Optional
from src.config import settings
from src.database.supabase_client import supabase_db

BUCKET_NAME = "zalo-sessions"
ZIP_FILENAME = "zalo_profile.zip"
EXCLUDE_DIRS = {"GrShaderCache", "ShaderCache", "Cache", "Code Cache", "Crashpad"}

def upload_session_to_cloud() -> bool:
    """
    Compress local .zalo_profile and upload to Supabase Storage.
    Enables zero-touch login on cloud deployments like Render.
    """
    if not supabase_db.is_connected:
        print("[SessionSync] Supabase is not connected!")
        return False

    profile_dir = settings.PROFILE_DIR
    if not profile_dir.exists():
        print(f"[SessionSync] Profile directory {profile_dir} does not exist!")
        return False

    temp_zip = settings.BASE_DIR / "temp_zalo_profile.zip"

    try:
        print("[SessionSync] Compressing .zalo_profile...")
        with zipfile.ZipFile(temp_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(profile_dir):
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
                for file in files:
                    if file.endswith(".log") or file.endswith(".tmp") or file == "LOCK":
                        continue
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, profile_dir)
                    try:
                        zipf.write(file_path, arcname)
                    except Exception:
                        pass

        file_size_mb = round(os.path.getsize(temp_zip) / (1024 * 1024), 2)
        print(f"[SessionSync] Uploading {ZIP_FILENAME} ({file_size_mb} MB) to Supabase Storage bucket '{BUCKET_NAME}'...")

        with open(temp_zip, "rb") as f:
            file_bytes = f.read()

        # Ensure bucket exists
        try:
            supabase_db.client.storage.create_bucket(BUCKET_NAME, options={"public": False})
        except Exception:
            pass

        # Upload or overwrite
        supabase_db.client.storage.from_(BUCKET_NAME).upload(
            path=ZIP_FILENAME,
            file=file_bytes,
            file_options={"upsert": "true"}
        )

        print("[SessionSync] ✅ Upload Zalo session to Supabase Storage successfully!")
        return True

    except Exception as e:
        print(f"[SessionSync] ❌ Upload failed: {e}")
        return False

    finally:
        if temp_zip.exists():
            try:
                os.remove(temp_zip)
            except Exception:
                pass


def download_session_from_cloud(force: bool = False) -> bool:
    """
    Download and extract .zalo_profile from Supabase Storage if local profile is missing or if force=True.
    """
    if not supabase_db.is_connected:
        print("[SessionSync] Supabase is not connected!")
        return False

    profile_dir = settings.PROFILE_DIR

    # Skip if profile already exists and not forced
    default_login_data = profile_dir / "Default" / "Login Data"
    if profile_dir.exists() and default_login_data.exists() and not force:
        print("[SessionSync] Local Zalo profile already exists. Skipping cloud download.")
        return True

    temp_zip = settings.BASE_DIR / "temp_download_profile.zip"

    try:
        print(f"[SessionSync] Checking '{BUCKET_NAME}' for {ZIP_FILENAME}...")
        files = supabase_db.client.storage.from_(BUCKET_NAME).list()
        file_names = [f["name"] for f in files if isinstance(f, dict) and "name" in f]

        if ZIP_FILENAME not in file_names:
            print(f"[SessionSync] No {ZIP_FILENAME} found in cloud storage.")
            return False

        print(f"[SessionSync] Downloading {ZIP_FILENAME} from Supabase Storage...")
        file_bytes = supabase_db.client.storage.from_(BUCKET_NAME).download(ZIP_FILENAME)

        with open(temp_zip, "wb") as f:
            f.write(file_bytes)

        print(f"[SessionSync] Extracting session into {profile_dir}...")
        os.makedirs(profile_dir, exist_ok=True)
        with zipfile.ZipFile(temp_zip, "r") as zipf:
            zipf.extractall(profile_dir)

        print("[SessionSync] ✅ Successfully restored Zalo session from Supabase Storage!")
        return True

    except Exception as e:
        print(f"[SessionSync] ❌ Failed to restore session from cloud: {e}")
        return False

    finally:
        if temp_zip.exists():
            try:
                os.remove(temp_zip)
            except Exception:
                pass
