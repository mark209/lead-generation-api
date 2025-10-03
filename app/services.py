import asyncio
import logging

from app.models import Lead

logger = logging.getLogger(__name__)


async def forward_to_crm(lead: Lead) -> None:
    """Simulate pushing the lead to an external CRM/dialer."""

    await asyncio.sleep(0.05)
    logger.info("Forwarded lead to CRM", extra={"lead_email": lead.email})