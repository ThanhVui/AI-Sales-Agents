import os
from typing import List, Dict, Any, Optional
from datetime import datetime
from supabase import create_client, Client
from src.config import settings

class SupabaseManager:
    def __init__(self):
        self.url = settings.SUPABASE_URL
        self.key = settings.SUPABASE_API_KEY_SERVICE_ROLE or settings.SUPABASE_SECRET_KEY or settings.SUPABASE_PUBLISHABLE_KEY
        self.client: Optional[Client] = None
        self._connected = False
        
        if self.url and self.key:
            try:
                self.client = create_client(self.url, self.key)
                self._connected = True
            except Exception as e:
                print(f"[SupabaseManager] Init failed: {e}")

    @property
    def is_connected(self) -> bool:
        return self._connected and self.client is not None

    def get_customers(self, limit: int = 5000) -> List[Dict[str, Any]]:
        """Fetch customers from Supabase with automatic pagination past 1,000 row limits."""
        if not self.is_connected:
            return []
        all_data = []
        page_size = 1000
        offset = 0
        while len(all_data) < limit:
            try:
                chunk_limit = min(page_size, limit - len(all_data))
                res = self.client.table("customers").select("*").order("id", desc=False).range(offset, offset + chunk_limit - 1).execute()
                data = res.data or []
                if not data:
                    break
                all_data.extend(data)
                if len(data) < chunk_limit:
                    break
                offset += len(data)
            except Exception as e:
                print(f"[SupabaseManager] Error fetching customers range {offset}: {e}")
                break
        return all_data

    def add_customer(self, customer: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Insert a single customer into Supabase."""
        if not self.is_connected:
            return None
        try:
            record = {
                "stt": customer.get("stt") or customer.get("STT") or 1,
                "name": customer.get("name") or customer.get("Tên Khách Hàng") or "",
                "apartment": customer.get("apartment") or customer.get("Tên Căn Hộ") or "",
                "block": customer.get("block") or customer.get("Mã Tòa") or "",
                "axis": customer.get("axis") or customer.get("Trục Căn") or "",
                "phone": str(customer.get("phone") or customer.get("Điện Thoại") or "").strip(),
                "price": str(customer.get("price") or customer.get("Giá Gốc") or ""),
                "email": customer.get("email") or customer.get("Email") or "",
                "note": customer.get("note") or customer.get("Ghi Chú") or "",
                "status": customer.get("status") or customer.get("Trạng Thái") or "Chưa gửi",
                "updated_at": datetime.utcnow().isoformat()
            }
            res = self.client.table("customers").upsert(record).execute()
            return res.data[0] if res.data else record
        except Exception as e:
            print(f"[SupabaseManager] Error adding customer: {e}")
            return None

    def upsert_customers(self, customers: List[Dict[str, Any]], batch_size: int = 100) -> int:
        """Batch upsert customers into Supabase with duplicate protection."""
        if not self.is_connected or not customers:
            return 0
        total_inserted = 0
        try:
            for i in range(0, len(customers), batch_size):
                batch = customers[i:i + batch_size]
                records = []
                for c in batch:
                    phone = str(c.get("phone") or c.get("Điện Thoại") or "").strip()
                    if not phone:
                        continue
                    records.append({
                        "stt": c.get("stt") or c.get("STT") or 0,
                        "name": c.get("name") or c.get("Tên Khách Hàng") or "",
                        "apartment": c.get("apartment") or c.get("Tên Căn Hộ") or "",
                        "block": c.get("block") or c.get("Mã Tòa") or "",
                        "axis": c.get("axis") or c.get("Trục Căn") or "",
                        "phone": phone,
                        "price": str(c.get("price") or c.get("Giá Gốc") or ""),
                        "email": c.get("email") or c.get("Email") or "",
                        "note": c.get("note") or c.get("Ghi Chú") or "",
                        "status": c.get("status") or c.get("Trạng Thái") or "Chưa gửi",
                        "updated_at": datetime.utcnow().isoformat()
                    })
                if records:
                    res = self.client.table("customers").upsert(records).execute()
                    if res.data:
                        total_inserted += len(res.data)
        except Exception as e:
            print(f"[SupabaseManager] Batch upsert error: {e}")
        return total_inserted

    def update_customer_status(self, phone: str, status: str, note: str = "") -> bool:
        """Update customer status by phone number."""
        if not self.is_connected:
            return False
        try:
            data = {
                "status": status,
                "updated_at": datetime.utcnow().isoformat()
            }
            if note:
                data["note"] = note
            self.client.table("customers").update(data).eq("phone", phone).execute()
            return True
        except Exception as e:
            print(f"[SupabaseManager] Error updating customer status: {e}")
            return False

    def update_customer(self, identifier: Any, updates: Dict[str, Any]) -> bool:
        """Update any customer attributes by id or phone."""
        if not self.is_connected:
            return False
        try:
            updates["updated_at"] = datetime.utcnow().isoformat()
            query = self.client.table("customers").update(updates)
            if isinstance(identifier, int) or (isinstance(identifier, str) and identifier.isdigit() and len(identifier) < 7):
                query.eq("id", int(identifier)).execute()
            else:
                query.eq("phone", str(identifier).strip()).execute()
            return True
        except Exception as e:
            print(f"[SupabaseManager] Error updating customer: {e}")
            return False

    def update_customer_note(self, phone: str, note: str) -> bool:
        """Quickly update customer note."""
        return self.update_customer(phone, {"note": note})

    def delete_customer(self, identifier: Any) -> bool:
        """Delete a single customer from Supabase by id or phone."""
        if not self.is_connected:
            return False
        try:
            query = self.client.table("customers").delete()
            if isinstance(identifier, int) or (isinstance(identifier, str) and identifier.isdigit() and len(identifier) < 7):
                query.eq("id", int(identifier)).execute()
            else:
                query.eq("phone", str(identifier).strip()).execute()
            return True
        except Exception as e:
            print(f"[SupabaseManager] Error deleting customer: {e}")
            return False

    def delete_all_customers(self) -> bool:
        """Delete all customers from Supabase."""
        if not self.is_connected:
            return False
        try:
            # Delete where id > 0
            self.client.table("customers").delete().gt("id", 0).execute()
            return True
        except Exception as e:
            print(f"[SupabaseManager] Error deleting all customers: {e}")
            return False

    def get_customer_logs(self, phone: str) -> List[Dict[str, Any]]:
        """Fetch logs specific to a phone number (matches both with/without leading zero)."""
        if not self.is_connected:
            return []
        try:
            raw_phone = str(phone).strip()
            clean_digits = "".join(filter(str.isdigit, raw_phone))
            phone_variants = {raw_phone, clean_digits}
            if clean_digits.startswith("0"):
                phone_variants.add(clean_digits[1:])
            else:
                phone_variants.add("0" + clean_digits)

            # Query using in_ filter across variants
            res = self.client.table("campaign_logs").select("*").in_("phone", list(phone_variants)).order("created_at", desc=True).execute()
            return res.data or []
        except Exception as e:
            print(f"[SupabaseManager] Error fetching customer logs: {e}")
            return []

    def log_campaign(self, phone: str, name: str, apartment: str, message: str, status: str, note: str = "") -> bool:
        """Append a log entry to campaign_logs."""
        if not self.is_connected:
            return False
        try:
            record = {
                "phone": phone,
                "customer_name": name,
                "apartment": apartment,
                "message": message,
                "status": status,
                "note": note,
                "created_at": datetime.utcnow().isoformat()
            }
            self.client.table("campaign_logs").insert(record).execute()
            return True
        except Exception as e:
            print(f"[SupabaseManager] Error logging campaign action: {e}")
            return False

    def get_campaign_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch latest campaign logs."""
        if not self.is_connected:
            return []
        try:
            res = self.client.table("campaign_logs").select("*").order("created_at", desc=True).limit(limit).execute()
            return res.data or []
        except Exception as e:
            print(f"[SupabaseManager] Error fetching campaign logs: {e}")
            return []

supabase_db = SupabaseManager()

