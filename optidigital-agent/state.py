from datetime import datetime
from typing import Optional

start_time: datetime = datetime.utcnow()
last_scan_time: Optional[datetime] = None
scheduler = None  # AsyncIOScheduler — set by bot/main.py on startup
playwright_ok: bool = False

# Auto-scan diagnostics (updated only on scheduler-triggered runs)
last_auto_scan_time: Optional[datetime] = None
last_auto_found_total: Optional[int] = None
last_auto_notified: Optional[int] = None
last_auto_error: Optional[str] = None
