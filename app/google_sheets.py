import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict

import gspread
from google.oauth2.service_account import Credentials

from app.config import get_settings
from app.models import Lead

logger = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _build_credentials(service_account_info: Dict[str, Any]) -> Credentials:
    return Credentials.from_service_account_info(service_account_info, scopes=_SCOPES)


def _append_row_to_sheet(lead_data: Dict[str, Any]) -> None:
    settings = get_settings()
    creds = _build_credentials(settings.google_service_account_info)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(settings.google_sheet_id)
    worksheet = (
        spreadsheet.worksheet(settings.google_sheet_worksheet)
        if settings.google_sheet_worksheet
        else spreadsheet.sheet1
    )
    timestamp = datetime.now(timezone.utc).isoformat()
    worksheet.append_row(
        [
            timestamp,
            lead_data["first_name"],
            lead_data["last_name"],
            lead_data["phone"],
            lead_data["email"],
            lead_data.get("address") or "",
            lead_data["state"],
            lead_data["postal"],
            lead_data.get("jornaya") or "",
        ],
        value_input_option="USER_ENTERED",
    )


async def append_lead_to_sheet(lead: Lead) -> None:
    """Persist the lead into the configured Google Sheet."""

    settings = get_settings()
    if not settings.google_sheets_enabled:
        logger.debug("Google Sheets integration disabled; skipping persistence")
        return

    lead_data = lead.model_dump()
    await asyncio.to_thread(_append_row_to_sheet, lead_data)
    logger.info("Appended lead to Google Sheet", extra={"lead_email": lead.email})