"""
CLI Script to Login, Backup and Restore Zalo Session to/from Supabase Storage
Usage:
    python sync_session.py login       # Mở Chrome trên máy tính quét QR trực tiếp và tự động đồng bộ lên Cloud
    python sync_session.py upload      # Sao lưu .zalo_profile lên Supabase Storage
    python sync_session.py download    # Tải .zalo_profile từ Supabase Storage về máy
"""
import sys
import os
import asyncio
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from src.database.session_sync import upload_session_to_cloud, download_session_from_cloud


async def run_gui_login():
    """Launch visible browser on local Windows for instant QR scan without bot detection."""
    print("🚀 Đang khởi động trình duyệt Chrome trên máy tính của bạn...")
    try:
        from playwright.async_api import async_playwright
        from src.config import settings

        profile_path = str(settings.PROFILE_DIR)
        os.makedirs(profile_path, exist_ok=True)

        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=profile_path,
                headless=False,
                viewport={"width": 1280, "height": 850},
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )

            page = context.pages[0] if context.pages else await context.new_page()
            print("🌐 Đang truy cập chat.zalo.me...")
            await page.goto("https://chat.zalo.me")
            print("\n" + "="*60)
            print("👉 VUI LÒNG DÙNG ỨNG DỤNG ZALO TRÊN ĐIỆN THOẠI QUÉT MÃ QR TRÊN MÀN HÌNH")
            print("="*60 + "\n")

            # Polling to detect login success
            logged_in = False
            for _ in range(90):  # Wait up to 3 minutes
                await asyncio.sleep(2)
                try:
                    # Dismiss device change popup if any
                    elem_understood = await page.query_selector("button:has-text('Đã hiểu'), .btn:has-text('Đã hiểu')")
                    if elem_understood:
                        await elem_understood.click()

                    logged = await page.query_selector(
                        "#contact-search-input, .main-tab__item, .nav__tabs__top, .avatar, [data-id='avatar'], .chat-box"
                    )
                    if logged:
                        logged_in = True
                        print("\n🎉 ĐĂNG NHẬP ZALO THÀNH CÔNG TRÊN MÁY TÍNH!")
                        await asyncio.sleep(2)
                        break
                except Exception:
                    pass

            await context.close()

        if logged_in:
            print("\n☁️ Đang tự động nén và sao lưu phiên Zalo lên Supabase Storage...")
            success = upload_session_to_cloud()
            if success:
                print("\n" + "★"*60)
                print("✅ HOÀN TẤT XUẤT SẮC!")
                print("👉 Bây giờ bạn chỉ cần mở trang web Render, bấm nút:")
                print("   '📥 Tải phiên Zalo từ Cloud về máy'")
                print("   là Render sẽ tự động đăng nhập và kết nối Zalo vĩnh viễn!")
                print("★"*60)
            else:
                print("❌ Tải lên Cloud thất bại. Vui lòng kiểm tra lại cấu hình Supabase.")
        else:
            print("⚠️ Chưa phát hiện đăng nhập hoặc đã quá thời gian chờ (3 phút).")

    except Exception as e:
        print(f"❌ Lỗi: {e}")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Sử dụng:")
        print("  python sync_session.py login       # Mở Chrome trên máy tính để quét QR và tự đồng bộ lên Cloud")
        print("  python sync_session.py upload      # Sao lưu .zalo_profile lên Supabase Storage")
        print("  python sync_session.py download    # Tải .zalo_profile từ Supabase Storage về máy")
        return

    arg = sys.argv[1].lower().strip("-")
    if arg in ("login", "dangnhap"):
        asyncio.run(run_gui_login())
    elif arg in ("upload", "backup", "saoluu"):
        print("🚀 Bắt đầu sao lưu phiên Zalo lên Supabase Storage...")
        success = upload_session_to_cloud()
        if success:
            print("🎉 Hoàn tất! Phiên đăng nhập Zalo đã được lưu vĩnh viễn trên Supabase.")
            print("👉 Khi bạn deploy lên Render, máy chủ Render sẽ tự động nhận diện và đăng nhập!")
        else:
            print("❌ Sao lưu thất bại. Vui lòng kiểm tra lại kết nối Supabase.")
    elif arg in ("download", "restore", "khoiphuc"):
        print("🚀 Bắt đầu khôi phục phiên Zalo từ Supabase Storage...")
        success = download_session_from_cloud(force=True)
        if success:
            print("🎉 Hoàn tất! Phiên đăng nhập Zalo đã được khôi phục thành công.")
        else:
            print("❌ Khôi phục thất bại.")
    else:
        print(f"Lệnh không xác định: {sys.argv[1]}")
        print("Các lệnh hợp lệ: login, upload, download")


if __name__ == "__main__":
    main()

