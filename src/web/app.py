import os
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, BackgroundTasks, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, Response
from pydantic import BaseModel
import openpyxl

from src.config import settings
from src.automation.zalo_agent import zalo_agent
from src.database.supabase_client import supabase_db
from src.queue.batch_worker import batch_worker
from src.ai.factory import get_advisor

app = FastAPI(
    title="Synexan AI Sales Real Estate",
    description="Multi-domain AI Sales Assistant with Zalo Web Automation & Supabase Sync"
)

# In-memory customer cache for high performance
_cached_customers: List[Dict[str, Any]] = []

# Pydantic schemas
class SingleSendRequest(BaseModel):
    phone: str
    message: str
    name: Optional[str] = "Khách Hàng"
    apartment: Optional[str] = ""

class AddCustomerRequest(BaseModel):
    stt: Optional[int] = 1
    name: str
    apartment: Optional[str] = ""
    block: Optional[str] = ""
    axis: Optional[str] = ""
    phone: str
    price: Optional[str] = ""
    email: Optional[str] = ""
    note: Optional[str] = ""
    status: Optional[str] = "Chưa gửi"

class UpdateCustomerRequest(BaseModel):
    phone: str
    name: Optional[str] = None
    apartment: Optional[str] = None
    block: Optional[str] = None
    axis: Optional[str] = None
    price: Optional[str] = None
    email: Optional[str] = None
    note: Optional[str] = None
    status: Optional[str] = None

class UpdateNoteRequest(BaseModel):
    phone: str
    note: str

class DeleteCustomerRequest(BaseModel):
    phone: str

class SyncCustomersRequest(BaseModel):
    customers: List[Dict[str, Any]]

class BatchStartRequest(BaseModel):
    customers: List[Dict[str, Any]]
    template: str
    schedule_config: Optional[Dict[str, Any]] = None
    delay: Optional[int] = 15
    test_only: Optional[bool] = False


@app.on_event("startup")
async def startup_event():
    """Start headless browser context on server boot if needed."""
    # Auto-restore Zalo session from Supabase Storage if local profile is missing (e.g. on fresh Render container)
    try:
        from src.database.session_sync import download_session_from_cloud
        download_session_from_cloud(force=False)
    except Exception as e:
        print(f"[Startup] Error checking cloud session: {e}")

    print("[Startup] Initializing Zalo Browser Agent in background...")
    asyncio.create_task(zalo_agent.initialize())

    async def _periodic_check():
        while True:
            await asyncio.sleep(25)
            try:
                if zalo_agent.page and not zalo_agent.page.is_closed() and not zalo_agent._lock.locked():
                    await zalo_agent.check_login_status()
            except Exception:
                pass

    asyncio.create_task(_periodic_check())


@app.post("/api/session/backup")
async def backup_session(background_tasks: BackgroundTasks):
    """
    Backup current Zalo session (.zalo_profile) to Supabase Storage.
    """
    from src.database.session_sync import upload_session_to_cloud
    background_tasks.add_task(upload_session_to_cloud)
    return {"success": True, "message": "Đang sao lưu phiên Zalo lên Supabase Storage trong nền..."}


@app.post("/api/session/restore")
async def restore_session():
    """
    Force restore Zalo session from Supabase Storage and re-initialize agent.
    """
    from src.database.session_sync import download_session_from_cloud
    ok = download_session_from_cloud(force=True)
    if ok:
        await zalo_agent.initialize()
    return {"success": ok, "message": "Đã khôi phục phiên Zalo từ Supabase Storage!" if ok else "Khôi phục thất bại"}


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanly close browser on shutdown."""
    await zalo_agent.close()


@app.get("/", response_class=HTMLResponse)
async def serve_home():
    html_path = settings.BASE_DIR / "src" / "web" / "templates" / "index.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Template not found")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/status")
async def get_system_status(check: bool = False):
    # If explicit check requested, check live status
    if check:
        await zalo_agent.check_login_status()
    return {
        "is_zalo_logged_in": zalo_agent.is_logged_in,
        "supabase_connected": supabase_db.is_connected,
        "batch_state": batch_worker.get_state()
    }


@app.get("/api/qr-image")
async def get_qr_image():
    qr_path = zalo_agent.qr_path

    # Check if existing QR file is valid and fresh (less than 35 seconds old)
    file_is_fresh = False
    if qr_path.exists() and qr_path.stat().st_size > 500:
        file_age = asyncio.get_event_loop().time() - os.path.getmtime(qr_path)
        if file_age < 35.0:
            file_is_fresh = True

    if file_is_fresh:
        return FileResponse(
            str(qr_path),
            media_type="image/png",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )

    # If QR is missing or older than 35s, trigger capture in background without blocking
    if not zalo_agent._lock.locked():
        asyncio.create_task(zalo_agent.capture_qr())

    # Return clean, lightweight SVG placeholder instantly
    svg_fallback = """<svg xmlns="http://www.w3.org/2000/svg" width="220" height="220" viewBox="0 0 220 220">
      <rect width="220" height="220" fill="#f8fafc" rx="8" stroke="#cbd5e1" stroke-width="1.5"/>
      <circle cx="110" cy="85" r="26" fill="none" stroke="#2563eb" stroke-width="3" stroke-dasharray="75 35" stroke-linecap="round">
        <animateTransform attributeName="transform" type="rotate" from="0 110 85" to="360 110 85" dur="1s" repeatCount="indefinite"/>
      </circle>
      <text x="110" y="140" text-anchor="middle" font-family="system-ui, -apple-system, sans-serif" font-size="12" font-weight="600" fill="#1e293b">Dang tao ma QR Zalo...</text>
      <text x="110" y="160" text-anchor="middle" font-family="system-ui, -apple-system, sans-serif" font-size="11" fill="#64748b">Vui long cho 3-5 giay</text>
    </svg>"""
    return Response(
        content=svg_fallback,
        media_type="image/svg+xml; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@app.post("/api/login-browser")
async def login_browser(background_tasks: BackgroundTasks):
    async def _init_and_capture():
        await zalo_agent.initialize()
        await zalo_agent.capture_qr()

    background_tasks.add_task(_init_and_capture)
    return {"status": "ok", "message": "Đang khởi động trình duyệt đăng nhập Zalo..."}


@app.post("/api/refresh-qr")
async def refresh_qr_endpoint(background_tasks: BackgroundTasks):
    background_tasks.add_task(zalo_agent.refresh_qr)
    return {"status": "ok", "message": "Đang lấy mã QR mới..."}


@app.post("/api/dismiss-popup")
async def dismiss_popup():
    """Explicitly dismiss Zalo 'Đổi thiết bị' / 'Đã hiểu' popup and check login status."""
    clicked = await zalo_agent.dismiss_popups()
    logged = await zalo_agent.check_login_status()
    return {"success": True, "clicked": clicked, "is_logged_in": logged}


@app.post("/api/logout")
async def logout_zalo(background_tasks: BackgroundTasks):
    background_tasks.add_task(zalo_agent.logout)
    return {"success": True, "message": "Đang đăng xuất và tạo mã QR mới trong nền..."}


@app.post("/api/send-single")
async def send_single_message(req: SingleSendRequest):
    """
    Send an outreach message to an individual phone number directly.
    """
    clean_phone = "".join(filter(str.isdigit, req.phone))
    if not clean_phone:
        raise HTTPException(status_code=400, detail="Số điện thoại không hợp lệ")

    # Send via Zalo Agent
    res = await zalo_agent.search_and_send_message(
        phone=clean_phone,
        message=req.message,
        log_callback=batch_worker.add_log
    )

    status = res.get("status", "Lỗi")
    note = res.get("note", "")

    # Log to Supabase
    supabase_db.log_campaign(
        phone=clean_phone,
        name=req.name or "Khách Hàng",
        apartment=req.apartment or "",
        message=req.message,
        status=status,
        note=note
    )
    supabase_db.update_customer_status(clean_phone, status, note)

    return res


@app.get("/api/customers")
async def get_all_customers(background_tasks: BackgroundTasks):
    """
    Get customer list. Automatically loads Masteri dataset and merges latest statuses from Supabase.
    """
    global _cached_customers
    if not _cached_customers:
        excel_path = settings.DATA_DIR / "Masteri Centre Point 2024.xlsx"
        if excel_path.exists():
            await load_masteri_dataset(background_tasks)

    # Sync latest statuses from Supabase
    if supabase_db.is_connected:
        try:
            db_records = supabase_db.get_customers(limit=3000)
            status_map = {"".join(filter(str.isdigit, str(r.get("phone", "")))): r for r in db_records if r.get("phone")}
            
            # Update existing cached customers
            matched_phones = set()
            for c in _cached_customers:
                clean_p = "".join(filter(str.isdigit, str(c.get("phone", ""))))
                if clean_p in status_map:
                    matched_phones.add(clean_p)
                    db_item = status_map[clean_p]
                    if db_item.get("status"):
                        c["status"] = db_item.get("status")
                    if db_item.get("note"):
                        c["note"] = db_item.get("note")

            # Add any DB customers that weren't in the initial file
            for clean_p, db_item in status_map.items():
                if clean_p not in matched_phones and clean_p:
                    _cached_customers.insert(0, {
                        "stt": db_item.get("stt") or 1,
                        "name": db_item.get("name") or "Khách Hàng",
                        "apartment": db_item.get("apartment") or "",
                        "block": db_item.get("block") or "",
                        "axis": db_item.get("axis") or "",
                        "phone": db_item.get("phone") or clean_p,
                        "price": db_item.get("price") or "",
                        "note": db_item.get("note") or "",
                        "status": db_item.get("status") or "Chưa gửi"
                    })
        except Exception as e:
            print(f"[Supabase Status Merge] Error: {e}")

    return {"success": True, "customers": _cached_customers}


@app.post("/api/customers/add")
async def add_customer(cust: AddCustomerRequest):
    """
    Add a single customer to active memory and Supabase.
    """
    data = cust.dict()
    _cached_customers.insert(0, data)
    supabase_res = supabase_db.add_customer(data)
    return {"success": True, "customer": supabase_res or data}


@app.post("/api/customers/update")
async def update_customer(req: UpdateCustomerRequest):
    """
    Update customer information in memory and Supabase.
    """
    clean_phone = "".join(filter(str.isdigit, req.phone))
    updates = {k: v for k, v in req.dict().items() if v is not None and k != "phone"}
    
    # Update cache
    global _cached_customers
    found = False
    for c in _cached_customers:
        p = "".join(filter(str.isdigit, str(c.get("phone", ""))))
        if p == clean_phone:
            c.update(updates)
            found = True
            break
            
    # Update Supabase
    supabase_db.update_customer(clean_phone, updates)
    return {"success": True, "updated": found}


@app.post("/api/customers/update-note")
async def update_customer_note(req: UpdateNoteRequest):
    """
    Quickly update customer note.
    """
    clean_phone = "".join(filter(str.isdigit, req.phone))
    global _cached_customers
    for c in _cached_customers:
        p = "".join(filter(str.isdigit, str(c.get("phone", ""))))
        if p == clean_phone:
            c["note"] = req.note
            c["Ghi Chú"] = req.note
            break
            
    supabase_db.update_customer_note(clean_phone, req.note)
    return {"success": True}


@app.post("/api/customers/delete")
async def delete_customer(req: DeleteCustomerRequest):
    """
    Delete a customer from memory and Supabase.
    """
    clean_phone = "".join(filter(str.isdigit, req.phone))
    global _cached_customers
    _cached_customers = [c for c in _cached_customers if "".join(filter(str.isdigit, str(c.get("phone", "")))) != clean_phone]
    supabase_db.delete_customer(clean_phone)
    return {"success": True}


@app.post("/api/customers/delete-all")
async def delete_all_customers():
    """
    Delete all customers from memory and Supabase.
    """
    global _cached_customers
    _cached_customers = []
    supabase_db.delete_all_customers()
    return {"success": True, "message": "Đã xóa toàn bộ khách hàng"}


@app.get("/api/customers/detail")
async def get_customer_detail(phone: str):
    """
    Get customer detail along with their conversation / outreach history.
    """
    clean_phone = "".join(filter(str.isdigit, phone))
    customer = None
    for c in _cached_customers:
        p = "".join(filter(str.isdigit, str(c.get("phone", ""))))
        if p == clean_phone:
            customer = c
            break
            
    logs = supabase_db.get_customer_logs(clean_phone)
    return {"success": True, "customer": customer, "logs": logs}


@app.post("/api/customers/sync-to-db")
async def sync_customers_to_db(req: SyncCustomersRequest):
    """
    Persist the active customer list into Supabase.
    """
    count = supabase_db.upsert_customers(req.customers)
    return {"success": True, "count": count}


@app.get("/api/customers/load-from-db")
async def load_customers_from_db():
    """
    Retrieve customer list from Supabase.
    """
    data = supabase_db.get_customers()
    return {"success": True, "customers": data}


@app.post("/api/load-masteri")
async def load_masteri_dataset(background_tasks: BackgroundTasks):
    """
    Fast loader for Masteri Centre Point 2024 (2,290 records).
    Automatically syncs to Supabase in background.
    """
    global _cached_customers
    excel_path = settings.DATA_DIR / "Masteri Centre Point 2024.xlsx"
    if not excel_path.exists():
        raise HTTPException(status_code=404, detail="Không tìm thấy file Masteri Centre Point 2024.xlsx")

    wb = openpyxl.load_workbook(str(excel_path), read_only=True, data_only=True)
    ws = wb.active

    headers = []
    customers = []
    for r_idx, row in enumerate(ws.iter_rows(values_only=True)):
        if r_idx == 0:
            headers = [str(c or "").strip() for c in row]
            continue

        stt, name, apt, block, axis, phone, price, email, note = "", "", "", "", "", "", "", "", ""
        if len(row) > 0 and row[0] is not None: stt = row[0]
        if len(row) > 1 and row[1] is not None: name = str(row[1]).strip()
        if len(row) > 2 and row[2] is not None: apt = str(row[2]).strip()
        if len(row) > 3 and row[3] is not None: block = str(row[3]).strip()
        if len(row) > 4 and row[4] is not None: axis = str(row[4]).strip()
        if len(row) > 5 and row[5] is not None: phone = str(row[5]).strip()
        if len(row) > 6 and row[6] is not None: price = str(row[6]).strip()
        if len(row) > 7 and row[7] is not None: email = str(row[7]).strip()
        if len(row) > 8 and row[8] is not None: note = str(row[8]).strip()

        if phone:
            customers.append({
                "stt": stt or len(customers) + 1,
                "name": name,
                "apartment": apt,
                "block": block,
                "axis": axis,
                "phone": phone,
                "price": price,
                "email": email,
                "note": note,
                "status": "Chưa gửi"
            })

    wb.close()
    _cached_customers = customers
    # Auto sync to Supabase in background
    if supabase_db.is_connected:
        background_tasks.add_task(supabase_db.upsert_customers, customers)
        
    return {"success": True, "count": len(customers), "customers": customers, "auto_synced": True}


# Batch background endpoints
@app.post("/api/batch/start")
async def start_batch(req: BatchStartRequest):
    ok = await batch_worker.start(
        customers=req.customers,
        template=req.template,
        schedule_config=req.schedule_config,
        test_only=bool(req.test_only)
    )
    return {"success": ok, "message": "Chiến dịch đã bắt đầu" if ok else "Chiến dịch đang chạy sẵn"}


@app.post("/api/batch/pause")
async def pause_batch():
    return {"success": batch_worker.pause()}


@app.post("/api/batch/resume")
async def resume_batch():
    return {"success": batch_worker.resume()}


@app.post("/api/batch/stop")
async def stop_batch():
    return {"success": batch_worker.stop()}


@app.get("/api/batch/state")
async def get_batch_state():
    return batch_worker.get_state()

