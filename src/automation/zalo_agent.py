import os
import asyncio
import base64
from typing import Dict, Any, Optional, Callable
from playwright.async_api import async_playwright, BrowserContext, Page, Playwright
from src.config import settings

class ZaloBrowserAgent:
    """
    Playwright-based Browser Automation Agent for Zalo Web (chat.zalo.me).
    Handles persistent login sessions, QR code auth, phone search, registered/unregistered status detection, and sending.
    """

    def __init__(self):
        self.pw: Optional[Playwright] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.is_logged_in: bool = False
        self._lock = asyncio.Lock()
        self.qr_path = settings.BASE_DIR / "qr_code.png"

    async def initialize(self, headless: Optional[bool] = None) -> bool:
        """Initialize browser context with persistent profile directory."""
        async with self._lock:
            if self.page and not self.page.is_closed():
                return await self.check_login_status()

            if headless is None:
                headless = settings.HEADLESS

            if not self.pw:
                self.pw = await async_playwright().start()

            profile_path = str(settings.PROFILE_DIR)
            os.makedirs(profile_path, exist_ok=True)

            self.context = await self.pw.chromium.launch_persistent_context(
                user_data_dir=profile_path,
                headless=headless,
                viewport={"width": 1280, "height": 850},
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--no-first-run",
                    "--disable-blink-features=AutomationControlled",
                ],
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )

            pages = self.context.pages
            self.page = pages[0] if pages else await self.context.new_page()

            # Navigate to Zalo Web
            try:
                await self.page.goto("https://chat.zalo.me", wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)
            except Exception as e:
                print(f"[ZaloBrowserAgent] Navigation error: {e}")

            return await self.check_login_status()

    async def check_login_status(self) -> bool:
        """Check if currently logged into Zalo Web."""
        if not self.page or self.page.is_closed():
            self.is_logged_in = False
            return False

        try:
            url = self.page.url
            if "chat.zalo.me" in url:
                # Look for logged-in indicators
                logged_in_elem = await self.page.query_selector(
                    "#contact-search-input, .main-tab__item, .nav__tabs__top, .avatar, [data-id='avatar'], .chat-box"
                )
                if logged_in_elem:
                    self.is_logged_in = True
                    return True

            self.is_logged_in = False
            return False
        except Exception:
            self.is_logged_in = False
            return False

    async def capture_qr(self) -> Optional[str]:
        """Capture QR code from login screen and save to disk."""
        if not self.page or self.page.is_closed():
            if not self._lock.locked():
                await self.initialize()
            else:
                return None

        if not self.page or self.page.is_closed():
            return None

        try:
            # If already logged in, no need to show QR
            if await self.check_login_status():
                if self.qr_path.exists():
                    try:
                        self.qr_path.unlink()
                    except Exception:
                        pass
                return None

            # Ensure we are on chat.zalo.me
            current_url = self.page.url
            if "chat.zalo.me" not in current_url:
                await self.page.goto("https://chat.zalo.me", wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(2)

            # Switch to QR tab if available
            try:
                qr_tab = await self.page.query_selector("a:has-text('VỚI MÃ QR'), div:has-text('VỚI MÃ QR'), .tab-item:has-text('QR')")
                if qr_tab:
                    await qr_tab.click()
                    await asyncio.sleep(0.5)
            except Exception:
                pass

            # Wait for QR element with reasonable timeout
            qr_elem = None
            try:
                qr_elem = await self.page.wait_for_selector(
                    ".qrcode, .qrcode-img, canvas, .qr-container, div[data-id='qrcode'], .content-qr",
                    timeout=8000
                )
            except Exception:
                qr_elem = await self.page.query_selector(
                    ".qrcode, .qrcode-img, canvas, .qr-container, div[data-id='qrcode'], .content-qr"
                )

            if qr_elem:
                await qr_elem.screenshot(path=str(self.qr_path))
            else:
                # Fallback to screenshotting the main login box or viewport
                card_elem = await self.page.query_selector(".wrapper-page, .body-login, .banner-login, #app")
                if card_elem:
                    await card_elem.screenshot(path=str(self.qr_path))
                else:
                    await self.page.screenshot(path=str(self.qr_path))

            if self.qr_path.exists():
                print(f"[ZaloBrowserAgent] Captured QR screenshot successfully: {self.qr_path} ({os.path.getsize(self.qr_path)} bytes)")
                return str(self.qr_path)
            return None
        except Exception as e:
            print(f"[ZaloBrowserAgent] Failed to capture QR: {e}")
            return None

    async def search_and_send_message(
        self,
        phone: str,
        message: str,
        log_callback: Optional[Callable[[str], None]] = None
    ) -> Dict[str, Any]:
        """
        Search for a phone number on Zalo Web and send the outreach message.
        Detects if phone is registered on Zalo or not.
        """
        async with self._lock:
            def log(msg: str):
                print(f"[ZaloBrowserAgent] {msg}")
                if log_callback:
                    try:
                        log_callback(msg)
                    except Exception:
                        pass

            if not await self.check_login_status():
                log("❌ Chưa đăng nhập Zalo Web. Vui lòng quét mã QR trước!")
                return {"success": False, "status": "Chưa đăng nhập", "note": "Chưa đăng nhập Zalo Web"}

            clean_phone = "".join(filter(str.isdigit, str(phone).strip()))
            log(f"[*] Bắt đầu tìm kiếm SĐT: {clean_phone}...")

            page = self.page

            # Locate search input
            search_input = await page.wait_for_selector(
                "#contact-search-input, input[placeholder*='Tìm kiếm']",
                timeout=10000
            )
            if not search_input:
                log("❌ Không tìm thấy thanh tìm kiếm Zalo")
                return {"success": False, "status": "Lỗi giao diện", "note": "Không tìm thấy thanh tìm kiếm"}

            # Clear and type phone
            await search_input.click()
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await asyncio.sleep(0.3)
            await search_input.fill(clean_phone)
            log(f"[*] Đã nhập {clean_phone}, đang kiểm tra kết quả...")
            await asyncio.sleep(1.5)

            # Check if auto-complete item appeared
            search_items = await page.query_selector_all(".global-search__item, .search-result-item, .contact-item, div[id*='conv-item']")
            if search_items and len(search_items) > 0:
                log(f"[*] Tìm thấy mục liên hệ trong danh sách, đang chọn...")
                await search_items[0].click()
                await asyncio.sleep(1.5)
            else:
                # Press Enter to perform global search for phone number
                log(f"[*] Thử tìm kiếm số điện thoại bằng phím Enter...")
                await page.keyboard.press("Enter")
                await asyncio.sleep(2.5)

                # Check if item appeared after Enter
                post_items = await page.query_selector_all(".global-search__item, .search-result-item, .contact-item, div[id*='conv-item']")
                if post_items and len(post_items) > 0:
                    await post_items[0].click()
                    await asyncio.sleep(1.5)

            # Check if chat input is available
            chat_input = None
            try:
                chat_input = await page.wait_for_selector(
                    "#richInput, div[contenteditable='true'], div.chat-input__content, div.chat-input",
                    timeout=5000
                )
            except Exception:
                pass

            if not chat_input:
                log(f"⚠️ SĐT {clean_phone} CHƯA ĐĂNG KÝ ZALO hoặc không tìm thấy cuộc trò chuyện!")
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.3)
                await page.keyboard.press("Escape")
                return {
                    "success": False,
                    "status": "Chưa đăng ký Zalo",
                    "note": "Số điện thoại chưa đăng ký tài khoản Zalo hoặc bị ẩn"
                }

            log(f"✅ Đã mở khung chat thành công cho SĐT {clean_phone}!")
            await chat_input.click()
            await asyncio.sleep(0.3)

            # Fill message
            # For multiline messages, shift+enter or fill innerText
            lines = message.split("\n")
            for i, line in enumerate(lines):
                if line:
                    await page.keyboard.insert_text(line)
                if i < len(lines) - 1:
                    await page.keyboard.press("Shift+Enter")
                await asyncio.sleep(0.05)

            await asyncio.sleep(0.5)
            log("📤 Đang gửi tin nhắn...")
            await page.keyboard.press("Enter")
            await asyncio.sleep(1.5)

            log(f"🎉 Đã gửi tin nhắn thành công tới SĐT {clean_phone}!")
            return {
                "success": True,
                "status": "Đã gửi",
                "note": "Gửi thành công qua Zalo Web"
            }

    async def logout(self) -> bool:
        """Logout current Zalo session."""
        async with self._lock:
            try:
                if self.page and not self.page.is_closed():
                    try:
                        await self.page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
                    except Exception:
                        pass
                    await self.context.clear_cookies()
                    await self.page.goto("https://chat.zalo.me", wait_until="domcontentloaded")
                    await asyncio.sleep(2)
                    await self.capture_qr()
                self.is_logged_in = False
                return True
            except Exception as e:
                print(f"[ZaloBrowserAgent] Logout error: {e}")
                return False

    async def close(self):
        """Close browser context cleanly."""
        try:
            if self.context:
                await self.context.close()
            if self.pw:
                await self.pw.stop()
        except Exception as e:
            print(f"[ZaloBrowserAgent] Close error: {e}")
        finally:
            self.context = None
            self.page = None
            self.pw = None
            self.is_logged_in = False

zalo_agent = ZaloBrowserAgent()
