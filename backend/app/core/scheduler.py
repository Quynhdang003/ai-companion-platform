"""Background jobs, started and stopped with the app (FastAPI lifespan in `app/main.py`)."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import Settings
from app.services.memory.job import run_memory_job
from app.services.notification.telegram import TelegramBot
from app.services.notification.telegram_updates import TelegramUpdatePoller

logger = logging.getLogger(__name__)


def start_scheduler(settings: Settings) -> AsyncIOScheduler | None:
    """Needs a running event loop; None when jobs are disabled."""
    if not settings.scheduler_enabled:
        return None
    scheduler = AsyncIOScheduler()
    if settings.gemini_api_key:
        scheduler.add_job(
            run_memory_job,
            "interval",
            seconds=settings.memory_job_interval_seconds,
            id="memory_extraction",
            max_instances=1,
            coalesce=True,
        )
    else:
        logger.warning("GEMINI_API_KEY is not set: memory extraction is off")
    if settings.telegram_bot_token:
        bot = TelegramBot(settings.telegram_bot_token, settings.telegram_api_base_url)
        scheduler.add_job(
            TelegramUpdatePoller(bot).run_once,
            "interval",
            seconds=settings.telegram_poll_interval_seconds,
            id="telegram_updates",
            max_instances=1,
            coalesce=True,
        )
    else:
        logger.warning("TELEGRAM_BOT_TOKEN is not set: Telegram connect and alerts are off")
    scheduler.start()
    return scheduler
