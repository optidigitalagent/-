from datetime import datetime
from typing import Optional

start_time: datetime = datetime.utcnow()
last_scan_time: Optional[datetime] = None
scheduler = None  # AsyncIOScheduler — set by bot/main.py on startup
playwright_ok: bool = False
