import json
import unicodedata
import urllib.request
from datetime import datetime, time
import pytz
from odoo import api, fields, models


class ResourceCalendarLeavesSK(models.Model):
    _inherit = "resource.calendar.leaves"

    SK_PUBLIC_HOLIDAY_NAMES = {
        "den vzniku slovenskej republiky",
        "zjavenie pana",
        "velky piatok",
        "velkonocny pondelok",
        "sviatok prace",
        "den vitazstva nad fasizmom",
        "sviatok svateho cyrila a svateho metoda",
        "vyrocie slovenskeho narodneho povstania",
        "den ustavy slovenskej republiky",
        "sedembolestna panna maria",
        "sviatok vsetkych svatych",
        "den boja za slobodu a demokraciu",
        "stedry den",
        "prvy sviatok vianocny",
        "druhy sviatok vianocny",
    }

    @api.model
    def _tenenet_normalize_public_holiday_name(self, name):
        normalized = unicodedata.normalize("NFKD", (name or "").strip().casefold())
        return "".join(char for char in normalized if not unicodedata.combining(char))

    def _tenenet_is_public_holiday_leave(self):
        self.ensure_one()
        return (
            not self.resource_id
            and self._tenenet_normalize_public_holiday_name(self.name) in self.SK_PUBLIC_HOLIDAY_NAMES
        )

    def _tenenet_sync_public_holiday_targets(self):
        years = {
            fields.Datetime.to_datetime(record.date_from).date().year
            for record in self.filtered(lambda rec: rec.date_from and rec._tenenet_is_public_holiday_leave())
        }
        if not years:
            return
        Cost = self.env["tenenet.employee.tenenet.cost"].sudo()
        for year in years:
            Cost._sync_target_employees_for_year(year)

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

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._tenenet_sync_public_holiday_targets()
        return records

    def write(self, vals):
        tracked = self.filtered(lambda rec: rec._tenenet_is_public_holiday_leave())
        result = super().write(vals)
        (tracked | self).filtered(lambda rec: rec._tenenet_is_public_holiday_leave())._tenenet_sync_public_holiday_targets()
        return result

    def unlink(self):
        years = {
            fields.Datetime.to_datetime(record.date_from).date().year
            for record in self.filtered(lambda rec: rec.date_from and rec._tenenet_is_public_holiday_leave())
        }
        result = super().unlink()
        Cost = self.env["tenenet.employee.tenenet.cost"].sudo()
        for year in years:
            Cost._sync_target_employees_for_year(year)
        return result
