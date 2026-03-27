import logging
import re
from datetime import datetime, time

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import email_normalize


_logger = logging.getLogger(__name__)

ALERT_RECIPIENT_RELATIONS = {"hr.employee", "res.users", "res.partner"}


class TenenetAlertRule(models.Model):
    _name = "tenenet.alert.rule"
    _description = "Pravidlo upozornenia"
    _order = "sequence, name"

    name = fields.Char(string="Názov", required=True)
    active = fields.Boolean(string="Aktívne", default=True)
    sequence = fields.Integer(string="Poradie", default=10)
    description = fields.Text(string="Popis")
    allowed_model_id = fields.Many2one(
        "tenenet.alert.allowed.model",
        string="Povolený model",
        required=True,
        ondelete="restrict",
    )
    model_id = fields.Many2one("ir.model", string="Model", related="allowed_model_id.model_id", store=True, readonly=True)
    model_model = fields.Char(string="Technický názov modelu", related="model_id.model", store=True, readonly=True)
    recipient_email_raw = fields.Text(string="E-mailové adresy")
    recipient_partner_ids = fields.Many2many(
        "res.partner",
        "tenenet_alert_rule_partner_rel",
        "rule_id",
        "partner_id",
        string="Partneri",
    )
    recipient_field_ids = fields.Many2many(
        "ir.model.fields",
        "tenenet_alert_rule_recipient_field_rel",
        "rule_id",
        "field_id",
        string="Dynamickí príjemcovia",
        domain="[('model_id', '=', model_id), ('store', '=', True), ('ttype', '=', 'many2one'), ('relation', 'in', ['hr.employee', 'res.users', 'res.partner'])]",
    )
    condition_ids = fields.One2many("tenenet.alert.condition", "rule_id", string="Podmienky")
    match_ids = fields.One2many("tenenet.alert.match", "rule_id", string="Zhody")
    active_match_ids = fields.One2many(
        "tenenet.alert.match",
        "rule_id",
        string="Aktívne zhody",
        domain=[("is_active", "=", True)],
    )
    match_count = fields.Integer(string="Počet zhôd", compute="_compute_match_count", store=True)
    summary_field_ids = fields.Many2many(
        "ir.model.fields",
        "tenenet_alert_rule_summary_field_rel",
        "rule_id",
        "field_id",
        string="Stĺpce v e-maile",
        domain="[('model_id', '=', model_id), ('store', '=', True), ('ttype', 'in', ['date','datetime','char','text','integer','float','monetary','boolean','selection','many2one'])]",
    )
    last_run_at = fields.Datetime(string="Naposledy spustené", readonly=True)
    last_result_count = fields.Integer(string="Počet výsledkov", readonly=True)
    last_new_match_count = fields.Integer(string="Nové zhody", readonly=True)
    last_mail_sent_at = fields.Datetime(string="Naposledy odoslaný e-mail", readonly=True)
    last_error = fields.Text(string="Posledná chyba", readonly=True)

    @api.depends("match_ids.is_active")
    def _compute_match_count(self):
        for rec in self:
            rec.match_count = len(rec.match_ids.filtered("is_active"))

    @api.constrains("condition_ids", "recipient_email_raw", "recipient_partner_ids", "recipient_field_ids", "model_id")
    def _check_configuration(self):
        for rec in self:
            rec._parse_recipient_emails()
            partners_without_email = rec.recipient_partner_ids.filtered(lambda partner: not partner.email)
            if partners_without_email:
                raise ValidationError("Vybraní partneri pre upozornenie musia mať vyplnený e-mail.")
            for field in rec.recipient_field_ids:
                if field.model_id != rec.model_id:
                    raise ValidationError("Dynamický príjemca musí patriť do rovnakého modelu ako pravidlo.")
                if not field.store or field.ttype != "many2one":
                    raise ValidationError("Dynamický príjemca musí byť uložené many2one pole.")
                if field.relation not in ALERT_RECIPIENT_RELATIONS:
                    raise ValidationError("Dynamický príjemca musí smerovať na partnera, používateľa alebo zamestnanca.")

    @api.constrains("summary_field_ids", "model_id")
    def _check_summary_fields(self):
        supported_types = {"date", "datetime", "char", "text", "integer", "float", "monetary", "boolean", "selection", "many2one"}
        for rec in self:
            for field in rec.summary_field_ids:
                if field.model_id != rec.model_id:
                    raise ValidationError("Súhrnné pole musí patriť do rovnakého modelu ako pravidlo.")
                if not field.store:
                    raise ValidationError("V e-maili je možné použiť len uložené polia.")
                if field.ttype not in supported_types:
                    raise ValidationError("Vybraný stĺpec sa ešte nedá zobraziť v e-maili.")

    def action_run_now(self):
        self._validate_runtime_configuration()
        self._run_rules()
        self.invalidate_recordset(["match_count", "last_run_at", "last_new_match_count"])
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Upozornenia",
                "message": "Pravidlo bolo vyhodnotené.",
                "type": "success",
                "sticky": False,
            },
        }

    def action_send_matching_now(self):
        self._validate_runtime_configuration()
        for rule in self:
            matches = rule._search_matching_records()
            if not matches:
                raise ValidationError("Pravidlo momentálne nemá žiadne zhodné záznamy na testovacie odoslanie.")
            rule._send_digest_email(matches)
            rule.write({
                "last_run_at": fields.Datetime.now(),
                "last_result_count": len(matches),
                "last_new_match_count": len(matches),
                "last_mail_sent_at": fields.Datetime.now(),
                "last_error": False,
            })
        self.invalidate_recordset(["last_run_at", "last_result_count", "last_new_match_count", "last_mail_sent_at"])
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Upozornenia",
                "message": "Testovací e-mail bol odoslaný pre všetky aktuálne zhody.",
                "type": "success",
                "sticky": False,
            },
        }

    def _validate_runtime_configuration(self):
        for rec in self:
            if not rec.condition_ids:
                raise ValidationError("Pravidlo upozornenia musí obsahovať aspoň jednu podmienku.")
            recipients = rec._parse_recipient_emails()
            if not recipients and not rec.recipient_partner_ids and not rec.recipient_field_ids:
                raise ValidationError("Pravidlo upozornenia musí mať aspoň jedného príjemcu.")

    def action_open_new_condition_wizard(self):
        self.ensure_one()
        view = self.env.ref("tenenet_projects.view_tenenet_alert_condition_wizard_form")
        return {
            "type": "ir.actions.act_window",
            "name": "Podmienka upozornenia",
            "res_model": "tenenet.alert.condition.wizard",
            "view_mode": "form",
            "view_id": view.id,
            "target": "new",
            "context": {
                "default_rule_id": self.id,
            },
        }

    @api.model
    def _cron_run_daily(self, limit=300):
        rules = self.search([("active", "=", True)], order="sequence, id", limit=limit)
        self.env["ir.cron"]._commit_progress(remaining=len(rules))
        for rule in rules:
            rule._run_rules()
            if not self.env["ir.cron"]._commit_progress(1):
                break

    def _run_rules(self):
        for rule in self:
            try:
                matches = rule._search_matching_records()
                new_records = rule._process_matches(matches)
                mail_sent_at = False
                if new_records:
                    rule._send_digest_email(new_records)
                    mail_sent_at = fields.Datetime.now()
                    match_rows = rule.match_ids.filtered(
                        lambda match: match.is_active and match.res_model == rule.model_model and match.res_id in new_records.ids
                    )
                    match_rows.write({"last_notified_at": mail_sent_at})
                rule.write({
                    "last_run_at": fields.Datetime.now(),
                    "last_result_count": len(matches),
                    "last_new_match_count": len(new_records),
                    "last_mail_sent_at": mail_sent_at or rule.last_mail_sent_at,
                    "last_error": False,
                })
            except Exception as exc:
                _logger.exception("Alert rule evaluation failed for %s", rule.name)
                rule.write({
                    "last_run_at": fields.Datetime.now(),
                    "last_error": str(exc),
                })

    def _search_matching_records(self):
        self.ensure_one()
        domain = self._build_domain_from_conditions()
        return self.env[self.model_model].search(domain)

    def _build_domain_from_conditions(self):
        self.ensure_one()
        domain = []
        for condition in self.condition_ids.sorted("sequence"):
            domain.extend(self._domain_for_condition(condition))
        return domain

    def _domain_for_condition(self, condition):
        field_name = condition.field_name
        operator = condition.operator
        if operator == "is_set":
            return [(field_name, "!=", False)]
        if operator == "is_not_set":
            return [(field_name, "=", False)]
        if operator == "is_true":
            return [(field_name, "=", True)]
        if operator == "is_false":
            return [(field_name, "=", False)]
        if condition.value_mode == "relative":
            return self._relative_domain_for_condition(condition)
        value = self._condition_value(condition)
        return [(field_name, self._map_operator(operator), value)]

    def _relative_domain_for_condition(self, condition):
        field_name = condition.field_name
        now_dt = fields.Datetime.now()
        today = fields.Date.context_today(self)
        delta = self._relative_delta(condition.relative_amount, condition.relative_unit)
        if condition.field_ttype == "datetime":
            day_start = datetime.combine(today, time.min)
            day_end = datetime.combine(today, time.max)
            if condition.operator == "today":
                return [(field_name, ">=", fields.Datetime.to_string(day_start)), (field_name, "<=", fields.Datetime.to_string(day_end))]
            if condition.operator == "overdue":
                return [(field_name, "<", fields.Datetime.to_string(day_start))]
            if condition.operator == "within_next":
                return [(field_name, ">=", fields.Datetime.to_string(now_dt)), (field_name, "<=", fields.Datetime.to_string(now_dt + delta))]
            if condition.operator == "within_last":
                return [(field_name, ">=", fields.Datetime.to_string(now_dt - delta)), (field_name, "<=", fields.Datetime.to_string(now_dt))]
            if condition.operator == "older_than":
                return [(field_name, "<", fields.Datetime.to_string(now_dt - delta))]
            if condition.operator == "younger_than":
                return [(field_name, ">=", fields.Datetime.to_string(now_dt - delta))]
        if condition.operator == "today":
            return [(field_name, "=", today)]
        if condition.operator == "overdue":
            return [(field_name, "<", today)]
        if condition.operator == "within_next":
            return [(field_name, ">=", today), (field_name, "<=", today + delta)]
        if condition.operator == "within_last":
            return [(field_name, ">=", today - delta), (field_name, "<=", today)]
        if condition.operator == "older_than":
            return [(field_name, "<", today - delta)]
        if condition.operator == "younger_than":
            return [(field_name, ">=", today - delta)]
        raise ValidationError("Nepodporovaný relatívny operátor.")

    def _relative_delta(self, amount, unit):
        if unit == "day":
            return relativedelta(days=amount)
        if unit == "week":
            return relativedelta(weeks=amount)
        return relativedelta(months=amount)

    def _condition_value(self, condition):
        if condition.field_ttype == "char":
            return condition.value_char
        if condition.field_ttype == "text":
            return condition.value_text
        if condition.field_ttype in {"float", "monetary"}:
            return condition.value_float
        if condition.field_ttype == "integer":
            return condition.value_integer
        if condition.field_ttype == "boolean":
            return condition.value_boolean
        if condition.field_ttype == "selection":
            return condition.value_selection_key
        if condition.field_ttype == "many2one":
            return condition.value_reference.id if condition.value_reference else False
        if condition.field_ttype == "date":
            return condition.value_date
        if condition.field_ttype == "datetime":
            return condition.value_datetime
        return False

    def _map_operator(self, operator):
        mapping = {
            "eq": "=",
            "ne": "!=",
            "gt": ">",
            "ge": ">=",
            "lt": "<",
            "le": "<=",
            "equals": "=",
            "not_equals": "!=",
            "contains": "ilike",
            "not_contains": "not ilike",
        }
        return mapping[operator]

    def _process_matches(self, matches):
        self.ensure_one()
        current_ids = set(matches.ids)
        now = fields.Datetime.now()
        existing_by_res_id = {match.res_id: match for match in self.match_ids if match.res_model == self.model_model}
        new_records = self.env[self.model_model]

        active_to_disable = self.match_ids.filtered(
            lambda match: match.is_active and match.res_model == self.model_model and match.res_id not in current_ids
        )
        if active_to_disable:
            active_to_disable.write({"is_active": False})

        for record in matches:
            existing = existing_by_res_id.get(record.id)
            values = {
                "last_seen_at": now,
                "last_display_name": record.display_name,
                "is_active": True,
            }
            if existing:
                if not existing.is_active:
                    new_records |= record
                existing.write(values)
            else:
                self.env["tenenet.alert.match"].create({
                    "rule_id": self.id,
                    "res_model": self.model_model,
                    "res_id": record.id,
                    "is_active": True,
                    "first_matched_at": now,
                    "last_seen_at": now,
                    "last_display_name": record.display_name,
                })
                new_records |= record
        return new_records

    def _send_digest_email(self, new_match_records):
        self.ensure_one()
        recipients = self._collect_recipient_emails(new_match_records)
        if not recipients:
            raise ValidationError("Pravidlo upozornenia nemá platných príjemcov.")
        template = self.env.ref("tenenet_projects.mail_template_tenenet_alert_digest")
        ctx = {
            "alert_new_records": new_match_records,
            "alert_rule": self,
            "alert_record_rows": self._prepare_mail_rows(new_match_records),
            "alert_match_count": len(new_match_records),
        }
        template.with_context(ctx).send_mail(
            self.id,
            force_send=True,
            email_values={"email_to": ",".join(recipients)},
        )

    def _get_digest_match_count(self):
        self.ensure_one()
        records = self.env.context.get("alert_new_records")
        if records is not None:
            return len(records)
        return self.env.context.get("alert_match_count", self.last_new_match_count or 0)

    def _get_digest_match_count_text(self):
        self.ensure_one()
        return str(self._get_digest_match_count())

    def _get_digest_subject_target_text(self):
        self.ensure_one()
        records = self.env.context.get("alert_new_records") or self.env[self.model_model]
        if not records:
            return self.name
        first = records[:1].display_name
        extra_count = len(records) - 1
        if extra_count > 0:
            return "%s + %s" % (first, extra_count)
        return first

    def _format_alert_value(self, value):
        if hasattr(value, "display_name"):
            return value.display_name
        if isinstance(value, bool):
            return "Áno" if value else "Nie"
        return value or ""

    def _get_related_project(self, record):
        if not record or not record.exists():
            return self.env["tenenet.project"]
        if record._name == "tenenet.project":
            return record
        if "project_id" in record._fields and getattr(record, "project_id", False):
            project = record.project_id
            if project and project._name == "tenenet.project":
                return project
        return self.env["tenenet.project"]

    def _format_relative_unit(self, amount, unit):
        labels = {
            "day": ("deň", "dni", "dní"),
            "week": ("týždeň", "týždne", "týždňov"),
            "month": ("mesiac", "mesiace", "mesiacov"),
        }
        one, few, many = labels.get(unit, (unit, unit, unit))
        if amount == 1:
            return one
        if 2 <= amount <= 4:
            return few
        return many

    def _describe_match_reason(self, condition, record):
        field_label = condition.field_id.field_description or condition.field_name
        operator = condition.operator
        if condition.value_mode == "relative":
            if operator == "today":
                return "POZOR: %s je dnes." % field_label
            if operator == "overdue":
                return "POZOR: %s je po termíne." % field_label
            amount = condition.relative_amount
            unit = self._format_relative_unit(amount, condition.relative_unit)
            if operator == "within_next":
                return "POZOR: %s termín je v najbližších %s %s." % (field_label, amount, unit)
            if operator == "within_last":
                return "POZOR: %s bol v posledných %s %s." % (field_label, amount, unit)
            if operator == "older_than":
                return "POZOR: %s je starší ako %s %s." % (field_label, amount, unit)
            if operator == "younger_than":
                return "POZOR: %s je mladší ako %s %s." % (field_label, amount, unit)

        value = self._format_alert_value(record[condition.field_name])
        target = condition._get_value_label()
        messages = {
            "lt": "POZOR: %s je menšie ako %s.",
            "le": "POZOR: %s je najviac %s.",
            "gt": "POZOR: %s je väčšie ako %s.",
            "ge": "POZOR: %s je aspoň %s.",
            "eq": "POZOR: %s je %s.",
            "ne": "POZOR: %s nie je %s.",
            "contains": "POZOR: %s obsahuje \"%s\".",
            "not_contains": "POZOR: %s neobsahuje \"%s\".",
            "equals": "POZOR: %s je \"%s\".",
            "not_equals": "POZOR: %s nie je \"%s\".",
            "is_set": "POZOR: %s je vyplnené.",
            "is_not_set": "POZOR: %s nie je vyplnené.",
            "is_true": "POZOR: %s je Áno.",
            "is_false": "POZOR: %s je Nie.",
        }
        if operator in {"is_set", "is_not_set", "is_true", "is_false"}:
            return messages[operator] % field_label
        return messages.get(operator, "POZOR: %s spĺňa podmienku %s.") % (field_label, target or value or condition._get_condition_summary())

    def _prepare_mail_rows(self, records):
        rows = []
        for record in records:
            project = self._get_related_project(record)
            summary_values = []
            for field in self.summary_field_ids:
                value = record[field.name]
                display_value = self._format_alert_value(value)
                summary_values.append({
                    "label": field.field_description,
                    "value": display_value,
                })
            rows.append({
                "name": record.display_name,
                "project_name": project.display_name or "",
                "url": self._get_record_url(record),
                "match_reasons": [self._describe_match_reason(condition, record) for condition in self.condition_ids.sorted("sequence")],
                "summary_values": summary_values,
            })
        return rows

    def _collect_recipient_emails(self, records):
        self.ensure_one()
        emails = set(self._parse_recipient_emails())
        emails.update(email_normalize(partner.email) for partner in self.recipient_partner_ids if partner.email)
        for field in self.recipient_field_ids:
            for record in records:
                emails.update(self._emails_from_dynamic_value(record[field.name]))
        return sorted({email for email in emails if email})

    def _emails_from_dynamic_value(self, value):
        if not value:
            return []
        values = value if hasattr(value, "mapped") else self.env[value._name].browse(value.id)
        emails = []
        for rec in values:
            emails.extend(self._emails_from_recipient_record(rec))
        return [normalized for normalized in (email_normalize(email) for email in emails) if normalized]

    def _emails_from_recipient_record(self, record):
        if record._name == "res.partner":
            return [record.email] if record.email else []
        if record._name == "res.users":
            values = [record.email, record.partner_id.email]
            return [value for value in values if value]
        if record._name == "hr.employee":
            values = [
                getattr(record, "work_email", False),
                record.user_id.email,
                record.user_id.partner_id.email,
                getattr(record, "private_email", False),
            ]
            return [value for value in values if value]
        return []

    def _parse_recipient_emails(self):
        self.ensure_one()
        recipients = []
        for raw in re.split(r"[\n,;]+", self.recipient_email_raw or ""):
            value = email_normalize((raw or "").strip())
            if not value:
                continue
            recipients.append(value)
        invalid_tokens = []
        for raw in re.split(r"[\n,;]+", self.recipient_email_raw or ""):
            cleaned = (raw or "").strip()
            if cleaned and not email_normalize(cleaned):
                invalid_tokens.append(cleaned)
        if invalid_tokens:
            raise ValidationError("Neplatné e-mailové adresy: %s" % ", ".join(invalid_tokens))
        return sorted(set(recipients))

    def _get_record_url(self, record):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
        return "%s/web#id=%s&model=%s&view_type=form" % (base_url, record.id, record._name)
