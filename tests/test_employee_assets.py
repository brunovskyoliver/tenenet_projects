import base64
from unittest.mock import patch

from lxml import etree

from odoo import Command, fields
from odoo.addons.tenenet_projects.models.tenenet_employee_asset_handover import TenenetEmployeeAssetHandover
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import file_open


@tagged("post_install", "-at_install")
class TestTenenetEmployeeAssets(TransactionCase):
    def setUp(self):
        super().setUp()
        self.employee = self.env["hr.employee"].create({
            "name": "Majetkový Zamestnanec",
            "work_email": "majetkovy.zamestnanec@example.com",
            "work_ratio": 100.0,
        })
        self.employee2 = self.env["hr.employee"].create({
            "name": "Druhý Zamestnanec",
            "work_ratio": 100.0,
        })
        self.asset_type_laptop = self.env["tenenet.employee.asset.type"].create({
            "name": "Laptop",
        })
        self.asset_type_phone = self.env["tenenet.employee.asset.type"].create({
            "name": "Mobil",
        })
        self.site_prevadzka = self.env["tenenet.project.site"].create({
            "name": "Prevádzka Test",
            "site_type": "prevadzka",
        })
        self.site_centrum = self.env["tenenet.project.site"].create({
            "name": "Centrum Test",
            "site_type": "centrum",
        })
        self.site_teren = self.env["tenenet.project.site"].create({
            "name": "Košický samosprávny kraj",
            "site_type": "teren",
            "kraj": "Košický samosprávny kraj",
        })
        self.company = self.env.company
        self.base_user_group = self.env.ref("base.group_user")
        self.tenenet_user_group = self.env.ref("tenenet_projects.group_tenenet_user")
        self.tenenet_manager_group = self.env.ref("tenenet_projects.group_tenenet_manager")
        self.env.user.email = self.env.user.email or "admin@example.com"
        self.user_user = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Použ. Majetok",
                "login": "asset_user",
                "email": "asset_user@example.com",
                "company_id": self.company.id,
                "company_ids": [Command.set([self.company.id])],
                "group_ids": [Command.set([self.base_user_group.id, self.tenenet_user_group.id])],
            }
        )
        self.manager_user = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Manažér Majetok",
                "login": "asset_manager",
                "email": "asset_manager@example.com",
                "company_id": self.company.id,
                "company_ids": [Command.set([self.company.id])],
                "group_ids": [Command.set([self.base_user_group.id, self.tenenet_manager_group.id])],
            }
        )
        self.helpdesk_team = self.env["helpdesk.team"].create({
            "name": "Interné TENENET",
            "company_id": self.company.id,
            "member_ids": [Command.link(self.env.user.id)],
        })
        self.helpdesk_stage_handover = self.env["helpdesk.stage"].create({
            "name": "Preberací protokol",
            "sequence": 5,
            "team_ids": [Command.link(self.helpdesk_team.id)],
        })
        self.helpdesk_stage_done = self.env["helpdesk.stage"].create({
            "name": "Vyriešené",
            "sequence": 10,
            "fold": True,
            "team_ids": [Command.link(self.helpdesk_team.id)],
        })
        self.helpdesk_team.write({
            "stage_ids": [Command.set([self.helpdesk_stage_handover.id, self.helpdesk_stage_done.id])],
            "to_stage_id": self.helpdesk_stage_done.id,
        })

    def test_employee_asset_creation(self):
        asset = self.env["tenenet.employee.asset"].create({
            "employee_id": self.employee.id,
            "asset_type_id": self.asset_type_laptop.id,
            "serial_number": "SN-LAPTOP-001",
            "handover_date": "2026-04-14",
            "cost": 1200.0,
            "note": "Inventár 123",
        })

        self.assertEqual(asset.employee_id, self.employee)
        self.assertEqual(asset.asset_type_id, self.asset_type_laptop)
        self.assertEqual(asset.name, "Laptop")
        self.assertEqual(asset.serial_number, "SN-LAPTOP-001")
        self.assertEqual(str(asset.handover_date), "2026-04-14")
        self.assertEqual(asset.cost, 1200.0)
        self.assertEqual(asset.note, "Inventár 123")

    def test_employee_asset_total_value_uses_active_assets(self):
        self.env["tenenet.employee.asset"].create({
            "employee_id": self.employee.id,
            "asset_type_id": self.asset_type_laptop.id,
            "serial_number": "SN-TOTAL-001",
            "cost": 1200.0,
        })
        self.env["tenenet.employee.asset"].create({
            "employee_id": self.employee.id,
            "asset_type_id": self.asset_type_phone.id,
            "serial_number": "SN-TOTAL-002",
            "cost": 300.0,
        })
        self.env["tenenet.employee.asset"].create({
            "employee_id": self.employee.id,
            "asset_type_id": self.asset_type_phone.id,
            "serial_number": "SN-TOTAL-003",
            "cost": 50.0,
            "active": False,
        })

        self.assertEqual(self.employee.asset_total_value, 1500.0)

    def test_site_key_created_from_employee_side_visible_on_site(self):
        self.employee.work_phone = "+421 900 111 222"
        key = self.env["tenenet.employee.site.key"].create({
            "employee_id": self.employee.id,
            "site_id": self.site_prevadzka.id,
        })

        self.assertEqual(key.site_id, self.site_prevadzka)
        self.assertIn(key, self.employee.site_key_ids)
        self.assertIn(key, self.site_prevadzka.site_key_ids)
        self.assertEqual(key.work_phone, "+421 900 111 222")

    def test_site_key_created_from_site_side_visible_on_employee(self):
        key = self.env["tenenet.employee.site.key"].create({
            "employee_id": self.employee.id,
            "site_id": self.site_centrum.id,
        })

        self.assertIn(key, self.site_centrum.site_key_ids)
        self.assertIn(key, self.employee.site_key_ids)

    def test_employee_supports_work_and_private_phone(self):
        self.employee.write({
            "work_phone": "+421 900 123 456",
            "private_phone": "+421 901 654 321",
        })

        self.assertEqual(self.employee.work_phone, "+421 900 123 456")
        self.assertEqual(self.employee.private_phone, "+421 901 654 321")

    def test_employee_moves_legacy_mobile_phone_to_private_phone(self):
        self.employee.write({
            "mobile_phone": "+421 901 654 321",
        })

        self.assertFalse(self.employee.mobile_phone)
        self.assertEqual(self.employee.private_phone, "+421 901 654 321")

    def test_employee_form_does_not_duplicate_language_skill_editor_on_tenenet_tab(self):
        arch = self.env["hr.employee"].get_view(
            view_id=self.env.ref("tenenet_projects.view_hr_employee_form_tenenet").id,
            view_type="form",
        )["arch"]
        root = etree.fromstring(arch.encode())

        language_fields = root.xpath(
            "//page[@string='TENENET']//field[@name='current_employee_skill_ids']"
        )
        self.assertFalse(
            language_fields,
            "Expected language skills to stay only in the standard Zivotopis section.",
        )

    def test_employee_form_contains_work_and_private_phone_in_personal_tab(self):
        arch = self.env["hr.employee"].get_view(
            view_id=self.env.ref("tenenet_projects.view_hr_employee_form_tenenet").id,
            view_type="form",
        )["arch"]
        root = etree.fromstring(arch.encode())

        personal_work_phone = root.xpath(
            "//page[@name='personal_information']//field[@name='work_phone']"
        )
        personal_private_phone = root.xpath(
            "//page[@name='personal_information']//field[@name='private_phone']"
        )

        self.assertTrue(personal_work_phone, "Expected work phone on the Personal tab.")
        self.assertTrue(personal_private_phone, "Expected private phone on the Personal tab.")
        self.assertTrue(
            root.xpath("//page[@name='personal_information']//field[@name='can_view_private_phone']"),
            "Expected the Personal tab to include the private-phone visibility helper field.",
        )
        self.assertIn(
            "not can_view_private_phone",
            personal_private_phone[0].get("invisible", ""),
        )

    def test_private_phone_visible_to_employee_manager_and_higher_up_only(self):
        hr_user_group = self.env.ref("hr.group_hr_user")
        grand_manager_user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Grand Manager Phone",
            "login": "grand_manager_phone",
            "email": "grand_manager_phone@example.com",
            "company_id": self.company.id,
            "company_ids": [Command.set([self.company.id])],
            "group_ids": [Command.set([self.base_user_group.id, hr_user_group.id])],
        })
        manager_user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Manager Phone",
            "login": "manager_phone",
            "email": "manager_phone@example.com",
            "company_id": self.company.id,
            "company_ids": [Command.set([self.company.id])],
            "group_ids": [Command.set([self.base_user_group.id, hr_user_group.id])],
        })
        employee_user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Employee Phone",
            "login": "employee_phone",
            "email": "employee_phone@example.com",
            "company_id": self.company.id,
            "company_ids": [Command.set([self.company.id])],
            "group_ids": [Command.set([self.base_user_group.id, hr_user_group.id])],
        })
        outsider_user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Outsider Phone",
            "login": "outsider_phone",
            "email": "outsider_phone@example.com",
            "company_id": self.company.id,
            "company_ids": [Command.set([self.company.id])],
            "group_ids": [Command.set([self.base_user_group.id, hr_user_group.id])],
        })
        grand_manager = self.env["hr.employee"].create({
            "name": "Grand Manager Phone",
            "user_id": grand_manager_user.id,
        })
        manager = self.env["hr.employee"].create({
            "name": "Manager Phone",
            "user_id": manager_user.id,
            "parent_id": grand_manager.id,
        })
        employee = self.env["hr.employee"].create({
            "name": "Employee Phone",
            "user_id": employee_user.id,
            "parent_id": manager.id,
            "private_phone": "+421 901 654 321",
        })
        self.env["hr.employee"].create({
            "name": "Outsider Phone",
            "user_id": outsider_user.id,
        })

        self.assertEqual(
            employee.with_user(employee_user).read(["private_phone"])[0]["private_phone"],
            "+421 901 654 321",
        )
        self.assertEqual(
            employee.with_user(manager_user).read(["private_phone"])[0]["private_phone"],
            "+421 901 654 321",
        )
        self.assertEqual(
            employee.with_user(grand_manager_user).read(["private_phone"])[0]["private_phone"],
            "+421 901 654 321",
        )
        self.assertFalse(
            employee.with_user(outsider_user).read(["private_phone"])[0]["private_phone"]
        )

    def test_site_key_rejects_teren(self):
        with self.assertRaises(ValidationError):
            self.env["tenenet.employee.site.key"].create({
                "employee_id": self.employee.id,
                "site_id": self.site_teren.id,
            })

    def test_site_key_unique_per_employee_and_site(self):
        self.env["tenenet.employee.site.key"].create({
            "employee_id": self.employee.id,
            "site_id": self.site_prevadzka.id,
        })

        with self.assertRaises(Exception):
            self.env["tenenet.employee.site.key"].create({
                "employee_id": self.employee.id,
                "site_id": self.site_prevadzka.id,
            })

    def test_asset_acl_user_read_only_manager_full(self):
        asset_model_user = self.env["tenenet.employee.asset"].with_user(self.user_user)
        asset_model_manager = self.env["tenenet.employee.asset"].with_user(self.manager_user)

        asset = asset_model_manager.create({
            "employee_id": self.employee.id,
            "asset_type_id": self.asset_type_laptop.id,
            "serial_number": "SN-ACL-001",
        })
        self.assertTrue(asset.exists())
        self.assertEqual(asset_model_user.search_count([("id", "=", asset.id)]), 1)

        with self.assertRaises(AccessError):
            asset_model_user.create({
                "employee_id": self.employee.id,
                "asset_type_id": self.asset_type_phone.id,
                "serial_number": "SN-ACL-002",
            })

    def test_asset_handover_wizard_creates_batch_without_sign_request(self):
        wizard = self.env["tenenet.employee.asset.handover.wizard"].create({
            "employee_id": self.employee.id,
            "handover_date": "2026-04-14",
            "line_ids": [
                Command.create({
                    "asset_type_id": self.asset_type_laptop.id,
                    "serial_number": "SN-WIZ-001",
                    "cost": 1200.0,
                    "note": "Notebook",
                }),
                Command.create({
                    "asset_type_id": self.asset_type_phone.id,
                    "serial_number": "SN-WIZ-002",
                    "cost": 300.0,
                    "note": "Mobil",
                }),
            ],
        })

        action = wizard.action_confirm()

        self.assertEqual(action["res_model"], "hr.employee")
        self.assertEqual(action["res_id"], self.employee.id)
        assets = self.env["tenenet.employee.asset"].search([("serial_number", "in", ["SN-WIZ-001", "SN-WIZ-002"])])
        self.assertEqual(len(assets), 2)
        self.assertEqual(set(assets.mapped("employee_id").ids), {self.employee.id})
        self.assertEqual(set(str(date) for date in assets.mapped("handover_date")), {"2026-04-14"})
        self.assertFalse(assets.mapped("handover_id"))

    def test_employee_action_creates_handover_and_sign_request_for_unsigned_assets(self):
        signed_handover = self.env["tenenet.employee.asset.handover"].create({
            "employee_id": self.employee.id,
            "handover_date": "2026-04-01",
        })
        already_signed_asset = self.env["tenenet.employee.asset"].create({
            "employee_id": self.employee.id,
            "asset_type_id": self.asset_type_laptop.id,
            "serial_number": "SN-OLD-SIGNED",
            "handover_date": "2026-04-01",
            "handover_id": signed_handover.id,
        })
        unsigned_assets = self.env["tenenet.employee.asset"].create([
            {
                "employee_id": self.employee.id,
                "asset_type_id": self.asset_type_laptop.id,
                "serial_number": "SN-WIZ-001",
                "handover_date": "2026-04-14",
                "cost": 1200.0,
                "note": "Notebook",
            },
            {
                "employee_id": self.employee.id,
                "asset_type_id": self.asset_type_phone.id,
                "serial_number": "SN-WIZ-002",
                "handover_date": "2026-04-15",
                "cost": 300.0,
                "note": "Mobil",
            },
        ])

        with self._patch_handover_pdf():
            action = self.employee.action_send_unsigned_assets_for_signature()

        handover = self.env["tenenet.employee.asset.handover"].browse(action["res_id"])
        self.assertEqual(handover.employee_id, self.employee)
        self.assertEqual(len(handover.asset_ids), 2)
        self.assertEqual(set(handover.asset_ids.mapped("serial_number")), {"SN-WIZ-001", "SN-WIZ-002"})
        self.assertEqual(set(handover.asset_ids.mapped("handover_id").ids), {handover.id})
        self.assertEqual(already_signed_asset.handover_id, signed_handover)
        self.assertEqual(unsigned_assets.handover_id, handover)

        self.assertTrue(handover.sign_template_id)
        self.assertTrue(handover.sign_request_id)
        self.assertTrue(handover.helpdesk_ticket_id)
        self.assertEqual(handover.helpdesk_ticket_id.team_id, self.helpdesk_team)
        self.assertEqual(handover.helpdesk_ticket_id.stage_id, self.helpdesk_stage_handover)
        self.assertEqual(handover.helpdesk_ticket_id.partner_id.email_normalized, "majetkovy.zamestnanec@example.com")
        self.assertIn("/sign/document/%s/" % handover.sign_request_id.id, handover.helpdesk_ticket_id.description)
        self.assertEqual(handover.sign_request_id.reference_doc, handover)
        self.assertEqual(len(handover.sign_request_id.request_item_ids), 1)
        self.assertEqual(
            handover.sign_request_id.request_item_ids.partner_id.email_normalized,
            "majetkovy.zamestnanec@example.com",
        )
        signature_items = handover.sign_template_id.sign_item_ids.filtered(
            lambda item: item.type_id == self.env.ref("sign.sign_item_type_signature")
        )
        self.assertEqual(len(signature_items), 1)
        self.assertEqual(signature_items.page, handover.sign_template_id.document_ids[:1].num_pages)
        self.assertEqual(signature_items.posX, 0.645)
        self.assertEqual(signature_items.posY, 0.475)
        self.assertEqual(signature_items.width, 0.255)
        self.assertEqual(signature_items.height, 0.060)

    def test_handover_helpdesk_ticket_closes_after_signature(self):
        asset = self.env["tenenet.employee.asset"].create({
            "employee_id": self.employee.id,
            "asset_type_id": self.asset_type_laptop.id,
            "serial_number": "SN-SIGN-001",
            "handover_date": "2026-04-14",
        })
        handover = self.env["tenenet.employee.asset.handover"].create({
            "employee_id": self.employee.id,
            "handover_date": "2026-04-14",
        })
        asset.handover_id = handover.id

        with self._patch_handover_pdf():
            handover.action_send_for_signature()

        self.assertEqual(handover.helpdesk_ticket_id.stage_id, self.helpdesk_stage_handover)

        handover.sign_request_id.request_item_ids.write({
            "state": "completed",
            "signing_date": fields.Date.today(),
        })
        with patch("odoo.addons.sign.models.sign_request.SignRequest._send_completed_documents", autospec=True, return_value=None):
            handover.sign_request_id._sign()

        self.assertEqual(handover.sign_request_id.state, "signed")
        self.assertEqual(handover.helpdesk_ticket_id.stage_id, self.helpdesk_stage_done)

    def test_employee_action_requires_work_email(self):
        self.employee.work_email = False
        self.env["tenenet.employee.asset"].create({
            "employee_id": self.employee.id,
            "asset_type_id": self.asset_type_laptop.id,
            "serial_number": "SN-NO-MAIL",
        })

        with self.assertRaises(UserError):
            self.employee.action_send_unsigned_assets_for_signature()

    def test_asset_handover_report_contains_asset_details(self):
        handover = self.env["tenenet.employee.asset.handover"].create({
            "employee_id": self.employee.id,
            "handover_date": "2026-04-14",
        })
        self.env["tenenet.employee.asset"].create({
            "employee_id": self.employee.id,
            "asset_type_id": self.asset_type_laptop.id,
            "serial_number": "SN-REPORT-001",
            "handover_date": "2026-04-14",
            "handover_id": handover.id,
        })

        html, _report_type = self.env["ir.actions.report"]._render_qweb_html(
            "tenenet_projects.action_report_employee_asset_handover",
            handover.ids,
        )
        html = html.decode() if isinstance(html, bytes) else html
        self.assertIn("Majetkový Zamestnanec", html)
        self.assertIn("Laptop", html)
        self.assertIn("SN-REPORT-001", html)
        self.assertIn("2026", html)
        self.assertIn("o_tenenet_signature_block", html)
        self.assertIn("justify-content: center", html)

    def test_asset_handover_acl_user_read_only_manager_full(self):
        handover_model_user = self.env["tenenet.employee.asset.handover"].with_user(self.user_user)
        handover_model_manager = self.env["tenenet.employee.asset.handover"].with_user(self.manager_user)

        handover = handover_model_manager.create({
            "employee_id": self.employee.id,
            "handover_date": "2026-04-14",
        })
        self.assertTrue(handover.exists())
        self.assertEqual(handover_model_user.search_count([("id", "=", handover.id)]), 1)

        with self.assertRaises(AccessError):
            handover_model_user.create({
                "employee_id": self.employee.id,
                "handover_date": "2026-04-14",
            })

    def test_site_key_acl_user_read_only_manager_full(self):
        key_model_user = self.env["tenenet.employee.site.key"].with_user(self.user_user)
        key_model_manager = self.env["tenenet.employee.site.key"].with_user(self.manager_user)

        key = key_model_manager.create({
            "employee_id": self.employee.id,
            "site_id": self.site_prevadzka.id,
        })
        self.assertTrue(key.exists())
        self.assertEqual(key_model_user.search_count([("id", "=", key.id)]), 1)

        with self.assertRaises(AccessError):
            key_model_user.create({
                "employee_id": self.employee2.id,
                "site_id": self.site_centrum.id,
            })

    def test_employee_form_site_key_subview_does_not_request_note(self):
        arch = self.env["hr.employee"].get_view(
            view_id=self.env.ref("tenenet_projects.view_hr_employee_form_tenenet").id,
            view_type="form",
        )["arch"]
        self._assert_site_key_subview_has_no_note(arch)

    def test_project_site_form_site_key_subview_does_not_request_note(self):
        arch = self.env["tenenet.project.site"].get_view(
            view_id=self.env.ref("tenenet_projects.view_tenenet_project_site_form").id,
            view_type="form",
        )["arch"]
        self._assert_site_key_subview_has_no_note(arch)

    def _assert_site_key_subview_has_no_note(self, arch):
        root = etree.fromstring(arch.encode())
        site_key_fields = root.xpath("//field[@name='site_key_ids']")
        self.assertTrue(site_key_fields, "Expected a site_key_ids subview in the form architecture.")
        self.assertFalse(
            root.xpath("//field[@name='site_key_ids']//field[@name='note']"),
            "site_key_ids subview should not request note on tenenet.employee.site.key.",
        )

    def test_employee_form_contains_asset_handover_button_and_columns(self):
        arch = self.env["hr.employee"].get_view(
            view_id=self.env.ref("tenenet_projects.view_hr_employee_form_tenenet").id,
            view_type="form",
        )["arch"]
        root = etree.fromstring(arch.encode())

        self.assertTrue(
            root.xpath("//button[@string='Pridať majetok']"),
            "Expected a button opening the asset handover wizard.",
        )
        self.assertTrue(
            root.xpath("//button[@string='Odoslať majetok na podpis']"),
            "Expected a button creating the handover sign request.",
        )
        self.assertTrue(
            root.xpath("//field[@name='asset_ids']//list[@editable='bottom']"),
            "Expected editable asset subview for incremental asset entry.",
        )
        self.assertTrue(
            root.xpath("//field[@name='asset_ids']//field[@name='serial_number']"),
            "Expected serial number in asset subview.",
        )
        self.assertTrue(
            root.xpath("//field[@name='asset_ids']//field[@name='handover_date']"),
            "Expected handover date in asset subview.",
        )
        self.assertTrue(
            root.xpath("//field[@name='asset_ids']//field[@name='sign_state']"),
            "Expected sign state in asset subview.",
        )

    def _patch_handover_pdf(self):
        with file_open("sign/static/demo/sample_contract.pdf", "rb") as pdf_file:
            pdf_data = base64.b64encode(pdf_file.read())
        return patch.object(TenenetEmployeeAssetHandover, "_render_pdf_for_sign", return_value=pdf_data)
