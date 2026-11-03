import asyncio
import random
from datetime import datetime, time
from typing import List, Dict, Any, Optional
from src.ai.factory import get_advisor
from src.automation.zalo_agent import zalo_agent
from src.database.supabase_client import supabase_db

class BatchWorker:
    """
    Background batch processor that executes independently of user browser connections.
    Includes Smart Anti-Spam Scheduling (Morning, Afternoon, Evening quotas)
    and randomized delay jitter to protect Zalo accounts.
    """

    def __init__(self):
        self.status = "IDLE"  # IDLE, RUNNING, PAUSED, STOPPED, COMPLETED, WAITING_SCHEDULE
        self.customers: List[Dict[str, Any]] = []
        self.template: str = ""
        self.current_index: int = 0
        self.total_count: int = 0
        self.sent_count: int = 0
        self.not_registered_count: int = 0
        self.error_count: int = 0
        self.logs: List[Dict[str, str]] = []
        self._task: Optional[asyncio.Task] = None
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self.advisor = get_advisor("real_estate")

        # Anti-spam schedule configuration
        self.schedule_config = {
            "mode": "schedule",  # "schedule" or "continuous"
            "min_delay": 300,    # 5 minutes
            "max_delay": 600,    # 10 minutes
            "morning": {"enabled": True, "start": "09:00", "end": "11:00", "limit": 15},
            "afternoon": {"enabled": True, "start": "14:00", "end": "16:00", "limit": 15},
            "evening": {"enabled": True, "start": "19:00", "end": "20:00", "limit": 10}
        }
        self.session_sent = {"morning": 0, "afternoon": 0, "evening": 0}
        self.last_sent_date = datetime.now().date()
        self.current_session_name = "Chờ lịch"
        self.next_action_time = ""

    def add_log(self, text: str):
        now_str = datetime.now().strftime("%H:%M:%S")
        entry = {"time": now_str, "text": text}
        self.logs.append(entry)
        if len(self.logs) > 200:
            self.logs = self.logs[-200:]
        print(f"[{now_str}] {text}")

    def get_state(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "current_index": self.current_index,
            "total_count": self.total_count,
            "sent_count": self.sent_count,
            "not_registered_count": self.not_registered_count,
            "error_count": self.error_count,
            "schedule_config": self.schedule_config,
            "session_sent": self.session_sent,
            "current_session_name": self.current_session_name,
            "next_action_time": self.next_action_time,
            "logs": self.logs[-50:]
        }

    def _parse_time(self, time_str: str) -> time:
        parts = time_str.split(":")
        return time(int(parts[0]), int(parts[1]))

    def _get_active_session(self) -> Optional[str]:
        """Check if current wall clock time is in morning, afternoon, or evening window."""
        now = datetime.now().time()
        for session_name in ["morning", "afternoon", "evening"]:
            cfg = self.schedule_config.get(session_name, {})
            if cfg.get("enabled", True):
                start = self._parse_time(cfg.get("start", "00:00"))
                end = self._parse_time(cfg.get("end", "23:59"))
                if start <= now <= end:
                    return session_name
        return None

    def _reset_daily_quota_if_needed(self):
        today = datetime.now().date()
        if today != self.last_sent_date:
            self.last_sent_date = today
            self.session_sent = {"morning": 0, "afternoon": 0, "evening": 0}
            self.add_log("🔄 Bắt đầu ngày mới: Đã đặt lại hạn mức gửi tin 3 ca.")

    async def start(
        self,
        customers: List[Dict[str, Any]],
        template: str,
        schedule_config: Optional[Dict[str, Any]] = None,
        test_only: bool = False
    ):
        if self.status in ("RUNNING", "WAITING_SCHEDULE"):
            return False

        self.customers = customers
        self.template = template
        if schedule_config:
            self.schedule_config.update(schedule_config)

        mode = self.schedule_config.get("mode", "schedule")
        max_cust = self.schedule_config.get("max_customers")
        if max_cust is not None:
            try:
                max_cust_int = int(max_cust)
                if max_cust_int > 0:
                    self.total_count = min(len(customers), max_cust_int)
                else:
                    self.total_count = len(customers)
                    self.schedule_config["max_customers"] = None
            except (ValueError, TypeError):
                self.total_count = len(customers)
                self.schedule_config["max_customers"] = None
        else:
            self.total_count = len(customers)

        self.current_index = 0
        self.sent_count = 0
        self.not_registered_count = 0
        self.error_count = 0
        self.status = "RUNNING"
        self._pause_event.set()
        self._reset_daily_quota_if_needed()

        # Load all phones that were ever marked 'Đã gửi' in campaign_logs to prevent ANY duplicate sends
        try:
            sent_records = supabase_db.client.table("campaign_logs").select("phone").eq("status", "Đã gửi").execute()
            self.sent_phones_history = set("".join(filter(str.isdigit, str(r.get("phone", "")))) for r in (sent_records.data or []))
        except Exception as e:
            self.sent_phones_history = set()

        min_d = self.schedule_config.get("min_delay", 300)
        max_d = self.schedule_config.get("max_delay", 600)

        if mode == "schedule":
            self.add_log(f"🛡️ Kích hoạt chiến dịch Lịch Trình Chống Khóa Zalo: Sáng/Chiều/Tối (Giãn cách: {min_d}s - {max_d}s).")
        else:
            max_c = self.schedule_config.get("max_customers")
            lim_text = f"Tối đa {max_c} khách" if max_c else f"Toàn bộ {len(customers)} khách"
            self.add_log(f"⚡ Kích hoạt chế độ Tự Chạy (Tùy Chỉnh): {lim_text} (Giãn cách ngẫu nhiên: {min_d}s - {max_d}s). Không theo ca.")

        self._task = asyncio.create_task(self._run_loop(test_only=test_only))
        return True

    async def _run_loop(self, test_only: bool = False):
        try:
            mode = self.schedule_config.get("mode", "schedule")
            min_delay = max(5, int(self.schedule_config.get("min_delay", 300)))
            max_delay = max(min_delay, int(self.schedule_config.get("max_delay", 600)))
            max_customers = self.schedule_config.get("max_customers")
            if max_customers is not None:
                try:
                    max_customers = int(max_customers)
                    if max_customers <= 0:
                        max_customers = None
                except (ValueError, TypeError):
                    max_customers = None

            cust_idx = 0
            while cust_idx < len(self.customers):
                await self._pause_event.wait()
                if self.status in ("STOPPED", "IDLE"):
                    break

                # If in continuous/custom mode and target limit reached, finish batch
                if max_customers and self.sent_count >= max_customers:
                    self.status = "COMPLETED"
                    self.current_session_name = f"Đã hoàn thành {self.sent_count}/{max_customers} khách"
                    self.add_log(f"🏁 Đã gửi đủ chỉ tiêu {self.sent_count}/{max_customers} khách! Chiến dịch tự do kết thúc.")
                    break

                self._reset_daily_quota_if_needed()

                # If in schedule mode, verify if currently allowed to send
                if mode == "schedule":
                    active_session = self._get_active_session()
                    if not active_session:
                        self.status = "WAITING_SCHEDULE"
                        self.current_session_name = "Ngoài khung giờ (Nghỉ)"
                        self.add_log("⏳ Hiện tại đang ngoài khung giờ gửi an toàn (Sáng 9-11h, Chiều 14-16h, Tối 19-20h). Đang chờ ca tiếp theo...")
                        while not self._get_active_session() and self.status in ("RUNNING", "WAITING_SCHEDULE"):
                            await asyncio.sleep(20)
                            await self._pause_event.wait()
                        if self.status in ("STOPPED", "IDLE"):
                            break
                        active_session = self._get_active_session()

                    session_cfg = self.schedule_config.get(active_session, {})
                    session_limit = session_cfg.get("limit", 15)
                    sent_this_session = self.session_sent.get(active_session, 0)

                    session_labels = {"morning": "Sáng (9h-11h)", "afternoon": "Chiều (14h-16h)", "evening": "Tối (19h-20h)"}
                    self.current_session_name = session_labels.get(active_session, active_session)

                    if sent_this_session >= session_limit:
                        self.status = "WAITING_SCHEDULE"
                        self.add_log(f"✅ Ca {self.current_session_name} đã gửi đủ hạn mức an toàn ({sent_this_session}/{session_limit} khách). Đang nghỉ chờ ca sau...")
                        # Wait until this session ends
                        while self._get_active_session() == active_session and self.status in ("RUNNING", "WAITING_SCHEDULE"):
                            await asyncio.sleep(20)
                            await self._pause_event.wait()
                        continue

                self.status = "RUNNING"
                c = self.customers[cust_idx]
                self.current_index = cust_idx + 1

                phone = str(c.get("phone") or c.get("Điện Thoại") or "").strip()
                name = c.get("name") or c.get("Tên Khách Hàng") or "Khách hàng"
                apt = c.get("apartment") or c.get("Tên Căn Hộ") or ""
                current_status = c.get("status") or c.get("Trạng Thái") or ""

                clean_phone = "".join(filter(str.isdigit, phone))
                if not clean_phone:
                    cust_idx += 1
                    continue

                # STRICT DUPLICATE PREVENTION:
                # If already sent in this batch OR in any past campaign log, skip immediately!
                if clean_phone in self.sent_phones_history or current_status in ("Đã gửi", "Chưa đăng ký Zalo", "Chặn người lạ"):
                    self.add_log(f"⏭️ Bỏ qua {name} ({clean_phone}) - Căn {apt} vì đã gửi hoặc đã xử lý trước đó.")
                    if clean_phone in self.sent_phones_history:
                        c["status"] = "Đã gửi"
                        c["Trạng Thái"] = "Đã gửi"
                    cust_idx += 1
                    continue

                # Safety constraint: if test_only is enabled, skip numbers other than 0901514312
                if test_only and clean_phone != "0901514312":
                    cust_idx += 1
                    continue

                # Personalize message using Domain AI Advisor
                msg = self.advisor.generate_outreach_message(c, self.template)
                self.add_log(f"🎯 [{cust_idx+1}/{self.total_count}] Đang xử lý: {name} ({clean_phone}) - Căn {apt}...")

                # Send via Playwright
                result = await zalo_agent.search_and_send_message(phone, msg, log_callback=self.add_log)
                new_status = result.get("status", "Lỗi")
                note = result.get("note", "")

                # Update in memory
                c["status"] = new_status
                c["Trạng Thái"] = new_status
                c["note"] = note
                c["Ghi Chú"] = note

                if result.get("success"):
                    self.sent_count += 1
                    self.sent_phones_history.add(clean_phone)
                    if mode == "schedule":
                        act = self._get_active_session()
                        if act:
                            self.session_sent[act] = self.session_sent.get(act, 0) + 1
                    else:
                        target_str = f"/{max_customers}" if max_customers else ""
                        self.current_session_name = f"Tự chạy: Đã gửi {self.sent_count}{target_str}"
                elif new_status == "Chưa đăng ký Zalo":
                    self.not_registered_count += 1
                else:
                    self.error_count += 1

                # Update in Supabase
                supabase_db.update_customer_status(phone, new_status, note)
                supabase_db.log_campaign(phone, name, apt, msg, new_status, note)

                cust_idx += 1

                # If reached target limit, end campaign immediately without extra waiting
                if max_customers and self.sent_count >= max_customers:
                    self.status = "COMPLETED"
                    self.current_session_name = f"Đã hoàn thành {self.sent_count}/{max_customers} khách"
                    self.add_log(f"🏁 Đã gửi đủ chỉ tiêu {self.sent_count}/{max_customers} khách! Chiến dịch tự chạy hoàn thành.")
                    break

                # Randomized Delay Jitter before next customer
                if cust_idx < len(self.customers) and self.status in ("RUNNING", "WAITING_SCHEDULE"):
                    sleep_delay = random.randint(min_delay, max_delay)
                    delay_min = round(sleep_delay / 60, 1)
                    self.next_action_time = f"Sau ~{delay_min} phút ({sleep_delay}s)"
                    self.add_log(f"☕ Giãn cách: Nghỉ {sleep_delay} giây (~{delay_min} phút) trước khi gửi khách tiếp theo...")
                    
                    # Sleep in small slices to be responsive to Pause / Stop
                    for _ in range(sleep_delay):
                        if self.status in ("STOPPED", "IDLE"):
                            break
                        await self._pause_event.wait()
                        await asyncio.sleep(1)

            self.status = "COMPLETED"
            self.add_log(f"🏁 Chiến dịch hoàn thành! Đã gửi: {self.sent_count}, Chưa có Zalo: {self.not_registered_count}, Lỗi: {self.error_count}.")
        except asyncio.CancelledError:
            self.status = "STOPPED"
            self.add_log("⏹️ Chiến dịch đã dừng.")
        except Exception as e:
            self.status = "ERROR"
            self.add_log(f"❌ Lỗi trong hàng đợi: {e}")

    def pause(self):
        if self.status in ("RUNNING", "WAITING_SCHEDULE"):
            self.status = "PAUSED"
            self._pause_event.clear()
            self.add_log("⏸️ Đã tạm dừng chiến dịch.")
            return True
        return False

    def resume(self):
        if self.status == "PAUSED":
            self.status = "RUNNING"
            self._pause_event.set()
            self.add_log("▶️ Tiếp tục chiến dịch.")
            return True
        return False

    def stop(self):
        if self._task and not self._task.done():
            self._task.cancel()
        self.status = "STOPPED"
        self._pause_event.set()
        self.add_log("⏹️ Đã yêu cầu dừng toàn bộ chiến dịch.")
        return True

batch_worker = BatchWorker()
