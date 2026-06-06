"""
Notification tasks — send alerts when high-score opportunities are found.
Supports Telegram and email. Designed to be extended with more channels.
"""
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.core.config import settings
from app.core.logging import get_logger
from app.db.database import get_db_context
from app.db.models.deal import Deal
from app.db.models.opportunity import Opportunity
from app.db.models.product import AmazonProduct
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    name="app.workers.notification_tasks.send_opportunity_alert_task",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def send_opportunity_alert_task(self, deal_id: int):
    """Send alert notification for a high-scoring opportunity."""
    logger.info("notification_task_started", deal_id=deal_id)
    try:
        _run_async(_send_alert(deal_id))
    except Exception as exc:
        logger.error("notification_task_failed", deal_id=deal_id, error=str(exc))
        raise self.retry(exc=exc)


async def _send_alert(deal_id: int) -> None:
    async with get_db_context() as db:
        # Load all needed data
        deal_result = await db.execute(select(Deal).where(Deal.id == deal_id))
        deal = deal_result.scalar_one_or_none()

        opp_result = await db.execute(
            select(Opportunity).where(Opportunity.deal_id == deal_id)
        )
        opp = opp_result.scalar_one_or_none()

        amazon_result = await db.execute(
            select(AmazonProduct).where(AmazonProduct.deal_id == deal_id)
        )
        amazon = amazon_result.scalar_one_or_none()

        if not deal or not opp:
            logger.warning("alert_missing_data", deal_id=deal_id)
            return

        if opp.alert_sent:
            logger.info("alert_already_sent", deal_id=deal_id)
            return

        message = _format_alert_message(deal, opp, amazon)
        sent = False

        if settings.telegram_bot_token and settings.telegram_chat_id:
            sent = await _send_telegram(message)

        if settings.smtp_user and settings.alert_email_to:
            sent = await _send_email(
                subject=f"🔥 ArbitrageAI Alert: Score {opp.score}/100 — {deal.title[:60]}",
                body=message,
            ) or sent

        if sent:
            await db.execute(
                update(Opportunity)
                .where(Opportunity.deal_id == deal_id)
                .values(alert_sent=True, alert_sent_at=datetime.now(timezone.utc))
            )
            await db.commit()
            logger.info("alert_sent", deal_id=deal_id, score=opp.score)
        else:
            logger.warning("alert_no_channel_configured", deal_id=deal_id)


def _format_alert_message(deal: Deal, opp: Opportunity, amazon: AmazonProduct | None) -> str:
    lines = [
        f"🎯 HIGH SCORE OPPORTUNITY — {opp.score}/100 ({opp.confidence_level.upper()} confidence)",
        "",
        f"📦 {deal.title}",
        f"🏷  Buy: £{opp.buy_price:.2f} → Sell: £{opp.sell_price:.2f}",
        f"💰 Net profit: £{opp.net_profit:.2f} | ROI: {opp.roi_percent:.1f}%",
        f"📊 Margin: {opp.margin_percent:.1f}%",
    ]

    if amazon and amazon.estimated_monthly_sales:
        lines.append(f"📈 ~{amazon.estimated_monthly_sales} estimated monthly sales")

    if amazon and amazon.asin:
        lines.append(f"🔗 Amazon: https://www.amazon.co.uk/dp/{amazon.asin}")

    lines.append(f"🛒 Deal: {deal.source_url}")

    if opp.score_reasoning:
        lines.extend(["", f"💡 {opp.score_reasoning}"])

    return "\n".join(lines)


async def _send_telegram(message: str) -> bool:
    """Send a Telegram message via Bot API."""
    try:
        import httpx
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                json={
                    "chat_id": settings.telegram_chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            logger.info("telegram_alert_sent")
            return True
    except Exception as exc:
        logger.error("telegram_send_error", error=str(exc))
        return False


async def _send_email(subject: str, body: str) -> bool:
    """Send email via SMTP."""
    try:
        import aiosmtplib
        from email.mime.text import MIMEText

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = settings.smtp_user
        msg["To"] = settings.alert_email_to

        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            start_tls=True,
        )
        logger.info("email_alert_sent", to=settings.alert_email_to)
        return True
    except Exception as exc:
        logger.error("email_send_error", error=str(exc))
        return False
