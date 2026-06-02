import asyncio
import logging
import random
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Awaitable

import httpx

USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

ALLOWED_KEYWORDS: list[str] = [
    # AI / ML / Voice AI
    "ai", "штучний інтелект", "machine learning", "нейронна мережа", "нейромережа",
    "gpt", "openai", "llm", "chatgpt", "gemini", "claude",
    "voice ai", "голосовий асистент", "голосовий бот", "розпізнавання мови",
    "speech recognition", "tts", "stt", "whisper",
    # Automation
    "автоматизація", "automation", "automate", "автоматично",
    # CRM
    "crm", "bitrix", "bitrix24", "salesforce", "hubspot", "zoho", "pipedrive",
    # ERP
    "erp", "1с", "sap", "управління підприємством",
    # Integrations
    "інтеграція", "інтегрувати", "integration", "api", "webhook",
    "zapier", "make.com", "n8n", "пайплайн",
    # Telegram Bots
    "telegram", "телеграм", "tg", "бот", " bot ", "telegram bot",
    # Web Development
    "сайт", "веб-сайт", "веб сайт", "веб-розробка", "web",
    "frontend", "backend", "fullstack", "full-stack",
    "react", "vue", "angular", "next.js", "nuxt",
    "django", "fastapi", "flask", "node.js", "nodejs", "laravel", "php",
    "wordpress", "розробка сайту",
    # SaaS / MVP
    "saas", "software as a service", "mvp", "мвп",
    # Landing Pages
    "лендінг", "landing page", "лендинг", "посадочна сторінка",
    # E-commerce
    "інтернет-магазин", "онлайн-магазин", "e-commerce", "ecommerce",
    "shopify", "woocommerce", "opencart", "магазин",
    # General dev
    "розробка", "додаток", "мобільний додаток", "програма",
    "python", "javascript", "typescript", "парсинг", "скрапінг",
]

EXCLUDED_KEYWORDS: list[str] = [
    "копірайтинг", "написання текстів", "написати текст", "seo-текст", "seo текст",
    "переклад", "перекладач",
    "дизайн логотипу", "логотип", "поліграфія", "друк", "банер",
    "відеомонтаж", "монтаж відео", "відеозйомка", "фотографія", "фотосесія",
    "озвучування", "озвучка",
    "ведення instagram", "ведення facebook", "ведення tiktok", "ведення соцмереж",
    "таргетована реклама", "smm менеджер", "контент-план",
]

_CAPTCHA_MARKERS: list[str] = [
    "captcha", "cloudflare", "recaptcha",
    "i am not a robot", "cf-challenge", "just a moment",
    "verify you are human", "access denied", "403 forbidden",
    "enable javascript", "challenge", "robot", "automated",
    "security check", "перевірка",
]

# Перевіряємо ТІЛЬКИ заголовок сторінки — контент може містити ці слова випадково
_CAPTCHA_TITLE_MARKERS: list[str] = [
    "captcha", "cloudflare", "challenge", "robot",
]

_STEALTH_SCRIPT = """
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
    Object.defineProperty(navigator, 'languages', {get: () => ['uk-UA','uk','ru','en-US']});
    window.chrome = {runtime: {}};
    Object.defineProperty(navigator, 'permissions', {
        query: (p) => Promise.resolve({state: 'granted'})
    });
"""

_PLAYWRIGHT_UNAVAILABLE: bool = False  # set True once if binary missing; prevents spam

_CHROMIUM_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-accelerated-2d-canvas",
    "--no-first-run",
    "--no-zygote",
    "--disable-gpu",
]


class BasePlatformParser:
    PLATFORM = "Unknown"
    MAX_RETRIES = 3
    CAPTCHA_WAIT = 30

    def __init__(self) -> None:
        self.logger = logging.getLogger(f"parser.{self.PLATFORM.lower()}")

    # ── helpers ──────────────────────────────────────────────────────────────

    def _random_ua(self) -> str:
        return random.choice(USER_AGENTS)

    def _parse_budget(self, text: str) -> tuple[float | None, float | None]:
        text = text.replace("\xa0", "").replace(" ", "").replace(" ", "")
        nums = [int(n) for n in re.findall(r"\d+", text)]
        if len(nums) >= 2:
            return float(nums[0]), float(nums[1])
        if len(nums) == 1:
            if "від" in text or "from" in text.lower() or "min" in text.lower():
                return float(nums[0]), None
            return None, float(nums[0])
        return None, None

    def _matches_filter(self, project: dict[str, Any]) -> bool:
        text = " ".join([
            project.get("category", "") or "",
            project.get("title", "") or "",
            project.get("description", "") or "",
        ]).lower()

        if any(kw in text for kw in EXCLUDED_KEYWORDS):
            return False

        return any(kw in text for kw in ALLOWED_KEYWORDS)

    def _matches_filter_verbose(self, project: dict[str, Any]) -> tuple[bool, str]:
        text = " ".join([
            project.get("category", "") or "",
            project.get("title", "") or "",
            project.get("description", "") or "",
        ]).lower()

        for kw in EXCLUDED_KEYWORDS:
            if kw in text:
                return False, f"EXCLUDED: '{kw}'"

        if any(kw in text for kw in ALLOWED_KEYWORDS):
            return True, ""

        return False, "ALLOWED: no keyword matched"

    def _debug_split(
        self, projects: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        matched: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        for p in projects:
            passes, reason = self._matches_filter_verbose(p)
            if passes:
                matched.append(p)
            else:
                rejected.append({**p, "_reject_reason": reason})
        return matched, rejected

    def _is_captcha(self, text: str) -> bool:
        lower = text.lower()
        return any(m in lower for m in _CAPTCHA_MARKERS)

    def _is_captcha_title(self, title: str) -> bool:
        lower = title.lower()
        return any(m in lower for m in _CAPTCHA_TITLE_MARKERS)

    # ── side-effects ──────────────────────────────────────────────────────────

    async def _take_screenshot(self, page: Any, label: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"debug_{self.PLATFORM.lower()}_{label}_{ts}.png"
        try:
            await page.screenshot(path=path, full_page=True)
            self.logger.warning("Screenshot saved: %s", path)
        except Exception as exc:
            self.logger.error("Screenshot failed: %s", exc)
        return path

    async def _send_alert(self, message: str) -> None:
        try:
            from config import settings
            url = f"https://api.telegram.org/bot{settings.TELEGRAM_TOKEN}/sendMessage"
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(url, json={
                    "chat_id": settings.TELEGRAM_CHAT_ID,
                    "text": f"🚨 Parser Alert [{self.PLATFORM}]\n{message}",
                })
        except Exception as exc:
            self.logger.error("Telegram alert failed: %s", exc)

    # ── stealth ───────────────────────────────────────────────────────────────

    async def _apply_manual_stealth(self, page: Any) -> None:
        await page.add_init_script(_STEALTH_SCRIPT)

    # ── human behaviour ───────────────────────────────────────────────────────

    async def _human_behavior(self, page: Any) -> None:
        await page.mouse.move(random.randint(200, 700), random.randint(200, 500))
        await page.evaluate("window.scrollBy(0, 300)")
        await asyncio.sleep(random.uniform(2, 4))

    # ── core Playwright session ───────────────────────────────────────────────

    async def _browse(
        self,
        url: str,
        callback: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        """
        Open *url* in a stealth Playwright session and call *callback(page)*.
        Retries up to MAX_RETRIES times; waits CAPTCHA_WAIT seconds on CAPTCHA.
        Returns callback result or None on total failure.
        """
        global _PLAYWRIGHT_UNAVAILABLE

        if _PLAYWRIGHT_UNAVAILABLE:
            self.logger.debug(
                "%s: Playwright disabled (Chromium binary missing) — skipping %s",
                self.PLATFORM, url,
            )
            return None

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self.logger.error(
                "playwright not installed — run:\n"
                "  pip install playwright\n"
                "  python -m playwright install chromium --with-deps"
            )
            return None

        cookies_path = f"cookies_{self.PLATFORM.lower()}.json"

        for attempt in range(1, self.MAX_RETRIES + 1):
            self.logger.info(
                "%s: Playwright attempt %d/%d → %s",
                self.PLATFORM, attempt, self.MAX_RETRIES, url,
            )

            async with async_playwright() as pw:
                browser = None
                ctx = None
                try:
                    browser = await pw.chromium.launch(
                        headless=True,
                        args=_CHROMIUM_ARGS,
                    )

                    ctx_kwargs: dict[str, Any] = dict(
                        viewport={"width": 1920, "height": 1080},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                        locale="uk-UA",
                        timezone_id="Europe/Kiev",
                        has_touch=False,
                        java_script_enabled=True,
                        extra_http_headers={
                            "Accept-Language": "uk-UA,uk;q=0.9",
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                        },
                    )
                    if Path(cookies_path).exists():
                        ctx_kwargs["storage_state"] = cookies_path
                        self.logger.info("%s: loading cookies from %s", self.PLATFORM, cookies_path)

                    ctx = await browser.new_context(**ctx_kwargs)
                    page = await ctx.new_page()
                    await self._apply_manual_stealth(page)

                    await page.goto(url, timeout=60_000, wait_until="domcontentloaded")

                    try:
                        await page.wait_for_load_state("networkidle", timeout=15_000)
                    except Exception:
                        pass  # networkidle may never fire on SPAs — that's fine

                    await self._human_behavior(page)

                    title = await page.title()
                    html = await page.content()
                    self.logger.debug(
                        "%s: page loaded, html_len=%d", self.PLATFORM, len(html)
                    )

                    print(f"[DEBUG] Page title: {title}")
                    print(f"[DEBUG] Page URL: {page.url}")
                    content_preview = html[:500]
                    print(f"[DEBUG] Content preview: {content_preview}")

                    if self._is_captcha_title(title):
                        self.logger.warning(
                            "%s: CAPTCHA detected on attempt %d", self.PLATFORM, attempt
                        )
                        await self._take_screenshot(page, f"captcha_a{attempt}")
                        if attempt < self.MAX_RETRIES:
                            self.logger.info(
                                "%s: waiting %ds before retry",
                                self.PLATFORM, self.CAPTCHA_WAIT,
                            )
                            await asyncio.sleep(self.CAPTCHA_WAIT)
                            continue
                        await ctx.storage_state(path=cookies_path)
                        self.logger.info("%s: cookies saved to %s", self.PLATFORM, cookies_path)
                        await self._send_alert(
                            f"CAPTCHA блокує {url} після {self.MAX_RETRIES} спроб — пропускаю платформу"
                        )
                        return None

                    result = await callback(page)
                    return result

                except Exception as exc:
                    err_str = str(exc).lower()
                    if "executable" in err_str and ("exist" in err_str or "found" in err_str):
                        _PLAYWRIGHT_UNAVAILABLE = True
                        self.logger.error(
                            "Playwright Chromium binary not found — browser-based parsing disabled. "
                            "Fix: add to Railway build command: "
                            "python -m playwright install chromium --with-deps"
                        )
                        await self._send_alert(
                            "Chromium binary відсутній на сервері.\n"
                            "Playwright fallback вимкнено до рестарту.\n\n"
                            "Виправлення — Railway → Settings → Build Command:\n"
                            "python -m playwright install chromium --with-deps"
                        )
                        return None
                    self.logger.error(
                        "%s: attempt %d error: %s", self.PLATFORM, attempt, exc
                    )
                    if attempt < self.MAX_RETRIES:
                        await asyncio.sleep(random.uniform(2.0, 5.0))
                        continue
                    await self._send_alert(
                        f"Playwright помилка після {self.MAX_RETRIES} спроб: {exc}"
                    )
                    return None
                finally:
                    if browser:
                        await browser.close()

        return None

    async def get_new_projects(self) -> list[dict[str, Any]]:
        raise NotImplementedError
