from unittest.mock import patch

from psycopg2 import IntegrityError

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetPlan14Alerts(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.base_user_group = self.env.ref("base.group_user")
        self.tenenet_user_group = self.env.ref("tenenet_projects.group_tenenet_user")
        self.tenenet_manager_group = self.env.ref("tenenet_projects.group_tenenet_manager")

        self.user_user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Používateľ Upozornenia",
            "login": "alert_user",
            "email": "alert_user@example.com",
            "company_id": self.company.id,
            "company_ids": [Command.set([self.company.id])],
            "group_ids": [Command.set([self.base_user_group.id, self.tenenet_user_group.id])],
        })
        self.manager_user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Manažér Upozornenia",
            "login": "alert_manager",
            "email": "alert_manager@example.com",
            "company_id": self.company.id,
            "company_ids": [Command.set([self.company.id])],
            "group_ids": [Command.set([self.base_user_group.id, self.tenenet_manager_group.id])],
        })

        self.partner = self.env["res.partner"].create({
            "name": "Externý príjemca",
            "email": "partner@example.com",
        })
        self.allowed_model = self.env["tenenet.alert.allowed.model"].create({
            "model_id": self.env["ir.model"]._get_id("tenenet.project"),
        })
        self.project_model = self.env["ir.model"].search([("model", "=", "tenenet.project")], limit=1)
        self.date_end_field = self.env["ir.model.fields"].search([
            ("model_id", "=", self.project_model.id),
            ("name", "=", "date_end"),
        ], limit=1)
        self.active_field = self.env["ir.model.fields"].search([
            ("model_id", "=", self.project_model.id),
            ("name", "=", "active"),
        ], limit=1)
        self.name_field = self.env["ir.model.fields"].search([
            ("model_id", "=", self.project_model.id),
            ("name", "=", "name"),
        ], limit=1)

    def _create_rule(self, **overrides):
        vals = {
            "name": "Projekt končí čoskoro",
            "allowed_model_id": self.allowed_model.id,
            "recipient_email_raw": "alerts@example.com",
            "recipient_partner_ids": [Command.set([self.partner.id])],
            "condition_ids": [
                Command.create({
                    "field_id": self.date_end_field.id,
                    "value_mode": "relative",
                    "operator": "within_next",
                    "relative_amount": 3,
                    "relative_unit": "month",
                }),
            ],
        }
        vals.update(overrides)
        return self.env["tenenet.alert.rule"].create(vals)

    def test_rule_requires_condition(self):
        with self.assertRaises(ValidationError):
            self.env["tenenet.alert.rule"].create({
                "name": "Bez podmienky",
                "allowed_model_id": self.allowed_model.id,
                "recipient_email_raw": "alerts@example.com",
            })

    def test_rule_requires_recipient(self):
        with self.assertRaises(ValidationError):
            self.env["tenenet.alert.rule"].create({
                "name": "Bez príjemcu",
                "allowed_model_id": self.allowed_model.id,
                "condition_ids": [
                    Command.create({
                        "field_id": self.date_end_field.id,
                        "value_mode": "relative",
                        "operator": "within_next",
                        "relative_amount": 3,
                        "relative_unit": "month",
                    }),
                ],
            })

    def test_invalid_email_is_rejected(self):
        with self.assertRaises(ValidationError):
            self._create_rule(recipient_email_raw="neplatny-email")

    def test_partner_without_email_is_rejected(self):
        partner_without_email = self.env["res.partner"].create({"name": "Bez mailu"})
        with self.assertRaises(ValidationError):
            self._create_rule(recipient_partner_ids=[Command.set([partner_without_email.id])])

    def test_duplicate_allowed_model_is_rejected(self):
        with self.cr.savepoint():
            with self.assertRaises(IntegrityError):
                self.env["tenenet.alert.allowed.model"].create({
                    "model_id": self.allowed_model.model_id.id,
                })

    def test_field_from_other_model_is_rejected(self):
        other_field = self.env["ir.model.fields"].search([("model", "=", "res.partner"), ("name", "=", "email")], limit=1)
        with self.assertRaises(ValidationError):
            self._create_rule(condition_ids=[
                Command.create({
                    "field_id": other_field.id,
                    "value_mode": "static",
                    "operator": "contains",
                    "value_char": "x",
                }),
            ])

    def test_condition_field_metadata_relation_uses_cascade_ondelete(self):
        self.assertEqual(
            self.env["tenenet.alert.condition"]._fields["field_id"].ondelete,
            "cascade",
        )

    def test_rule_builds_relative_domain(self):
        rule = self._create_rule()
        domain = rule._build_domain_from_conditions()
        self.assertEqual(domain[0][0], "date_end")
        self.assertEqual(domain[0][1], ">=")
        self.assertEqual(domain[1][0], "date_end")
        self.assertEqual(domain[1][1], "<=")

    def test_combined_and_conditions_match_expected_project(self):
        rule = self._create_rule(condition_ids=[
            Command.create({
                "field_id": self.date_end_field.id,
                "value_mode": "relative",
                "operator": "within_next",
                "relative_amount": 3,
                "relative_unit": "month",
            }),
            Command.create({
                "field_id": self.active_field.id,
                "value_mode": "static",
                "operator": "is_true",
            }),
            Command.create({
                "field_id": self.name_field.id,
                "value_mode": "static",
                "operator": "contains",
                "value_char": "Aktívny",
            }),
        ])
        today = self.env["tenenet.alert.rule"]._fields["last_run_at"].context_today(rule)
        matching = self.env["tenenet.project"].create({
            "name": "Aktívny projekt",
            "date_end": today,
            "active": True,
        })
        self.env["tenenet.project"].create({
            "name": "Neaktívny projekt",
            "date_end": today,
            "active": False,
        })

        matches = rule._search_matching_records()
        self.assertEqual(matches, matching)

    def test_rule_deduplicates_notifications_until_match_reappears(self):
        today = self.env["tenenet.alert.rule"]._fields["last_run_at"].context_today(self.env["tenenet.alert.rule"])
        project = self.env["tenenet.project"].create({
            "name": "Projekt termín",
            "date_end": today,
        })
        rule = self._create_rule()

        with patch("odoo.addons.tenenet_projects.models.tenenet_alert_rule.TenenetAlertRule._send_digest_email") as send_mail:
            rule._run_rules()
            self.assertEqual(send_mail.call_count, 1)

            rule._run_rules()
            self.assertEqual(send_mail.call_count, 1)

            project.date_end = today + rule._relative_delta(6, "month")
            rule._run_rules()
            self.assertFalse(rule.match_ids.filtered(lambda match: match.res_id == project.id).is_active)

            project.date_end = today
            rule._run_rules()
            self.assertEqual(send_mail.call_count, 2)

    def test_manager_acl_and_user_denied_create(self):
        with self.assertRaises(AccessError):
            self.env["tenenet.alert.rule"].with_user(self.user_user).create({
                "name": "Používateľské pravidlo",
                "allowed_model_id": self.allowed_model.id,
                "recipient_email_raw": "alerts@example.com",
                "condition_ids": [
                    Command.create({
                        "field_id": self.date_end_field.id,
                        "value_mode": "relative",
                        "operator": "within_next",
                        "relative_amount": 3,
                        "relative_unit": "month",
                    }),
                ],
            })

        rule = self.env["tenenet.alert.rule"].with_user(self.manager_user).create({
            "name": "Manažérske pravidlo",
            "allowed_model_id": self.allowed_model.id,
            "recipient_email_raw": "alerts@example.com",
            "condition_ids": [
                Command.create({
                    "field_id": self.date_end_field.id,
                    "value_mode": "relative",
                    "operator": "within_next",
                    "relative_amount": 3,
                    "relative_unit": "month",
                }),
            ],
        })
        self.assertTrue(rule.exists())

    def test_digest_rows_include_summary_fields(self):
        rule = self._create_rule(summary_field_ids=[Command.set([self.name_field.id])])
        today = self.env["tenenet.alert.rule"]._fields["last_run_at"].context_today(rule)
        project = self.env["tenenet.project"].create({
            "name": "Projekt s detailom",
            "date_end": today,
        })

        rows = rule._prepare_mail_rows(project)
        self.assertEqual(rows[0]["name"], "Projekt s detailom")
        self.assertEqual(rows[0]["summary_values"][0]["label"], self.name_field.field_description)
