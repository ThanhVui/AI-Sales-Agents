"""
CLI Script to Backup and Restore Zalo Session to/from Supabase Storage
Usage:
    python sync_session.py --backup     # Backup local .zalo_profile to Supabase Storage
    python sync_session.py --restore    # Restore .zalo_profile from Supabase Storage
"""
import sys
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from src.database.session_sync import upload_session_to_cloud, download_session_from_cloud

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage:")
        print("  python sync_session.py --backup     # Sao lưu .zalo_profile lên Supabase Storage")
        print("  python sync_session.py --restore    # Khôi phục .zalo_profile từ Supabase Storage")
        return

    arg = sys.argv[1]
    if arg == "--backup":
        print("🚀 Bắt đầu sao lưu phiên Zalo lên Supabase Storage...")
        success = upload_session_to_cloud()
        if success:
            print("🎉 Hoàn tất! Phiên đăng nhập Zalo đã được lưu vĩnh viễn trên Supabase.")
            print("👉 Khi bạn deploy lên Render, máy chủ Render sẽ tự động nhận diện và đăng nhập!")
        else:
            print("❌ Sao lưu thất bại. Vui lòng kiểm tra lại kết nối Supabase.")
    elif arg == "--restore":
        print("🚀 Bắt đầu khôi phục phiên Zalo từ Supabase Storage...")
        success = download_session_from_cloud(force=True)
        if success:
            print("🎉 Hoàn tất! Phiên đăng nhập Zalo đã được khôi phục thành công.")
        else:
            print("❌ Khôi phục thất bại.")
    else:
        print(f"Lệnh không xác định: {arg}")

if __name__ == "__main__":
    main()
