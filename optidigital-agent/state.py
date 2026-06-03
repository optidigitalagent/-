from datetime import datetime
from typing import Optional

start_time: datetime = datetime.utcnow()
last_scan_time: Optional[datetime] = None
scheduler = None  # AsyncIOScheduler — set by bot/main.py on startup
playwright_ok: bool = False

# Auto-scan diagnostics (updated only on scheduler-triggered runs)
last_auto_scan_time: Optional[datetime] = None
last_auto_found_total: Optional[int] = None
last_auto_new_saved: Optional[int] = None
last_auto_notified: Optional[int] = None
last_auto_duplicates: Optional[int] = None
last_auto_below_min: Optional[int] = None
last_auto_errors: Optional[int] = None
last_auto_error: Optional[str] = None

# Daily accumulators — reset after daily_report is sent
daily_found_total: int = 0
daily_new_saved: int = 0
daily_notified: int = 0
daily_duplicates: int = 0
daily_below_min: int = 0
daily_errors: int = 0
