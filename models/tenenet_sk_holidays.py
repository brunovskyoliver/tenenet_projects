import json
import urllib.request
from datetime import datetime, time
import pytz
from odoo import api, fields, models


class ResourceCalendarLeavesSK(models.Model):
    _inherit = "resource.calendar.leaves"

    @api.model
    def _import_sk_public_holidays(self, year=None):
        """Fetch Slovak public holidays from Nager.Date API and create resource.calendar.leaves."""
        if year is None:
            year = fields.Date.today().year
        url = f"https://date.nager.at/api/v3/PublicHolidays/{year}/SK"
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                holidays = json.loads(resp.read())
        except Exception:
            return  # Fail silently in cron context

        tz = pytz.timezone("Europe/Bratislava")
        company = self.env.company

        for h in holidays:
            day = fields.Date.from_string(h["date"])
            date_from = tz.localize(datetime.combine(day, time(0, 0, 0))).astimezone(pytz.utc).replace(tzinfo=None)
            date_to   = tz.localize(datetime.combine(day, time(23, 59, 59))).astimezone(pytz.utc).replace(tzinfo=None)
            # Skip if already exists for this company + date
            exists = self.search_count([
                ("resource_id", "=", False),
                ("company_id", "=", company.id),
                ("date_from", ">=", date_from.replace(hour=0, minute=0)),
                ("date_from", "<",  date_to.replace(hour=23, minute=59)),
            ])
            if not exists:
                self.create({
                    "name": h["localName"],
                    "date_from": date_from,
                    "date_to": date_to,
                    "resource_id": False,
                    "company_id": company.id,
                    "time_type": "leave",
                })
