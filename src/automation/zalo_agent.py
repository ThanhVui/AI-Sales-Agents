import os
import shutil
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
        self._last_capture_time: float = 0

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
                    "--no-zygote",
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--disable-renderer-backgrounding",
                    "--js-flags=--max-old-space-size=128",
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

    async def dismiss_popups(self) -> bool:
        """Automatically dismiss any Zalo confirmation popups like 'Đổi thiết bị', 'Đã hiểu', notifications."""
        if not self.page or self.page.is_closed():
            return False
        clicked = False
        try:
            # 1. "Đổi thiết bị" popup -> click "Đã hiểu"
            elem_understood = await self.page.query_selector(
                "button:has-text('Đã hiểu'), [role='button']:has-text('Đã hiểu'), .btn:has-text('Đã hiểu'), div[class*='btn']:has-text('Đã hiểu')"
            )
            if not elem_understood:
                try:
                    loc = self.page.locator("text='Đã hiểu'")
                    if await loc.count() > 0:
                        elem_understood = loc.last
                except Exception:
                    pass

            if elem_understood:
                print("[ZaloBrowserAgent] Detected 'Đổi thiết bị' popup! Clicking 'Đã hiểu'...")
                try:
                    await elem_understood.click()
                except Exception:
                    await elem_understood.dispatch_event("click")
                await asyncio.sleep(2)
                clicked = True

            # 2. Prompts like "Bỏ qua", "Để sau", "Không phải bây giờ"
            elem_skip = await self.page.query_selector(
                "button:has-text('Bỏ qua'), div:has-text('Bỏ qua'), button:has-text('Để sau'), button:has-text('Không phải bây giờ')"
            )
            if elem_skip:
                print("[ZaloBrowserAgent] Detected prompt. Dismissing...")
                await elem_skip.click()
                await asyncio.sleep(0.5)
                clicked = True
        except Exception as e:
            print(f"[ZaloBrowserAgent] Error in dismiss_popups: {e}")
        return clicked

    async def check_login_status(self) -> bool:
        """Check if currently logged into Zalo Web."""
        if not self.page or self.page.is_closed():
            self.is_logged_in = False
            return False

        try:
            url = self.page.url
            if "chat.zalo.me" in url:
                # First dismiss any blocking popups like 'Đổi thiết bị'
                await self.dismiss_popups()

                # Look for logged-in indicators
                logged_in_elem = await self.page.query_selector(
                    "#contact-search-input, .main-tab__item, .nav__tabs__top, .avatar, [data-id='avatar'], .chat-box"
                )
                if logged_in_elem:
                    self.is_logged_in = True
                    if self.qr_path.exists():
                        try:
                            self.qr_path.unlink()
                        except Exception:
                            pass
                    return True

            self.is_logged_in = False
            return False
        except Exception:
            self.is_logged_in = False
            return False

    async def capture_qr(self) -> Optional[str]:
        """Capture QR code from login screen and save to disk."""
        now = asyncio.get_event_loop().time()
        # Throttle: if already captured less than 5s ago and file exists, return immediately
        if (now - self._last_capture_time) < 5.0 and self.qr_path.exists() and self.qr_path.stat().st_size > 500:
            return str(self.qr_path)

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

            # Auto-click "Lấy mã mới" if QR is expired!
            try:
                btn_refresh_expired = await self.page.query_selector(
                    "button:has-text('Lấy mã mới'), a:has-text('Lấy mã mới'), div:has-text('Lấy mã mới'), [role='button']:has-text('Lấy mã mới')"
                )
                if not btn_refresh_expired:
                    loc = self.page.locator("text='Lấy mã mới'")
                    if await loc.count() > 0:
                        btn_refresh_expired = loc.last

                if btn_refresh_expired:
                    print("[ZaloBrowserAgent] Detected expired QR code. Clicking 'Lấy mã mới'...")
                    try:
                        await btn_refresh_expired.click()
                    except Exception:
                        await btn_refresh_expired.dispatch_event("click")
                    await asyncio.sleep(1.5)
            except Exception as e:
                print(f"[ZaloBrowserAgent] Note refreshing expired QR: {e}")

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
                self._last_capture_time = asyncio.get_event_loop().time()
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

    async def reset_session(self) -> bool:
        """
        Completely reset Zalo session:
        Close browser, wipe local profile and cached cookies,
        re-launch fresh browser on chat.zalo.me and generate a fresh QR code for a new account.
        """
        async with self._lock:
            try:
                print("[ZaloBrowserAgent] Completely wiping session to allow logging into a NEW Zalo account...")
                self.is_logged_in = False

                # 1. Close current page and context
                if self.page and not self.page.is_closed():
                    try:
                        await self.page.close()
                    except Exception:
                        pass
                self.page = None

                if self.context:
                    try:
                        await self.context.close()
                    except Exception:
                        pass
                    self.context = None

                # 2. Delete local profile directory completely so NO old account remains
                profile_path = settings.PROFILE_DIR
                if profile_path.exists():
                    try:
                        shutil.rmtree(profile_path, ignore_errors=True)
                        print("[ZaloBrowserAgent] Deleted old .zalo_profile successfully.")
                    except Exception as e:
                        print(f"[ZaloBrowserAgent] Note deleting profile: {e}")

                # 3. Delete existing QR file
                if self.qr_path.exists():
                    try:
                        self.qr_path.unlink()
                    except Exception:
                        pass

                # 4. Relaunch fresh Chromium context
                headless = settings.HEADLESS
                if not self.pw:
                    self.pw = await async_playwright().start()

                os.makedirs(str(profile_path), exist_ok=True)
                self.context = await self.pw.chromium.launch_persistent_context(
                    user_data_dir=str(profile_path),
                    headless=headless,
                    viewport={"width": 1280, "height": 850},
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--no-first-run",
                        "--no-zygote",
                        "--disable-extensions",
                        "--disable-background-networking",
                        "--disable-renderer-backgrounding",
                        "--js-flags=--max-old-space-size=128",
                        "--disable-blink-features=AutomationControlled",
                    ],
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )

                pages = self.context.pages
                self.page = pages[0] if pages else await self.context.new_page()

                # 5. Navigate to Zalo Web
                await self.page.goto("https://chat.zalo.me", wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2.5)

                # 6. Capture fresh QR code
                try:
                    qr_tab = await self.page.query_selector("a:has-text('VỚI MÃ QR'), div:has-text('VỚI MÃ QR'), .tab-item:has-text('QR')")
                    if qr_tab:
                        await qr_tab.click()
                        await asyncio.sleep(0.5)
                except Exception:
                    pass

                try:
                    qr_elem = await self.page.wait_for_selector(
                        ".qrcode, .qrcode-img, canvas, .qr-container, div[data-id='qrcode'], .content-qr",
                        timeout=10000
                    )
                    if qr_elem:
                        await qr_elem.screenshot(path=str(self.qr_path))
                    else:
                        await self.page.screenshot(path=str(self.qr_path))
                except Exception:
                    await self.page.screenshot(path=str(self.qr_path))

                print(f"[ZaloBrowserAgent] Brand new QR code ready: {self.qr_path}")
                return True
            except Exception as e:
                print(f"[ZaloBrowserAgent] Error resetting session: {e}")
                return False

    async def refresh_qr(self) -> Optional[str]:
        """Manually refresh QR code by clicking 'Lấy mã mới' or reloading page."""
        if not self.page or self.page.is_closed():
            await self.initialize()

        if not self.page or self.page.is_closed():
            return None

        try:
            btn_refresh = await self.page.query_selector(
                "button:has-text('Lấy mã mới'), a:has-text('Lấy mã mới'), div:has-text('Lấy mã mới'), [role='button']:has-text('Lấy mã mới')"
            )
            if not btn_refresh:
                loc = self.page.locator("text='Lấy mã mới'")
                if await loc.count() > 0:
                    btn_refresh = loc.last

            if btn_refresh:
                try:
                    await btn_refresh.click()
                except Exception:
                    await btn_refresh.dispatch_event("click")
                await asyncio.sleep(1.5)
            else:
                await self.page.reload(wait_until="domcontentloaded")
                await asyncio.sleep(2)

            self._last_capture_time = 0
            return await self.capture_qr()
        except Exception as e:
            print(f"[ZaloBrowserAgent] refresh_qr error: {e}")
            return None

    async def logout(self) -> bool:
        """Logout current Zalo session and prepare fresh QR code."""
        return await self.reset_session()

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
