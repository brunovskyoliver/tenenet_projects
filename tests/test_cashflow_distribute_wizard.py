from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetCashflowDistributeWizard(TransactionCase):
    def setUp(self):
        super().setUp()
        self.program = self.env["tenenet.program"].create({"name": "Cashflow Program", "code": "CFW"})
        self.project = self.env["tenenet.project"].create({
            "name": "Cashflow Project",
            "program_ids": [(6, 0, self.program.ids)],
            "reporting_program_id": self.program.id,
        })

    def _create_receipt(self, amount=1200.0, date_received="2027-03-15"):
        return self.env["tenenet.project.receipt"].create({
            "project_id": self.project.id,
            "date_received": date_received,
            "amount": amount,
        })

    def _amounts_by_month(self, receipt):
        return {
            cashflow.month: cashflow.amount
            for cashflow in receipt.cashflow_ids.sorted("month")
        }

    def test_receipt_action_opens_distribution_wizard(self):
        receipt = self._create_receipt()

        action = receipt.action_open_cashflow_distribute_wizard()

        self.assertEqual(action["res_model"], "tenenet.project.cashflow.distribute.wizard")
        self.assertEqual(action["target"], "new")
        self.assertEqual(action["context"]["default_receipt_id"], receipt.id)

    def test_distribution_wizard_replaces_cashflow_with_selected_month_span(self):
        receipt = self._create_receipt(amount=1200.0)
        self.assertEqual(sorted(receipt.cashflow_ids.mapped("month")), list(range(3, 13)))

        wizard = self.env["tenenet.project.cashflow.distribute.wizard"].create({
            "receipt_id": receipt.id,
            "amount": 1200.0,
            "date_from": "2027-03-10",
            "date_to": "2027-08-20",
        })
        wizard.action_distribute()
        receipt.invalidate_recordset(["cashflow_ids"])

        self.assertEqual(sorted(receipt.cashflow_ids.mapped("month")), [3, 4, 5, 6, 7, 8])
        self.assertEqual(self._amounts_by_month(receipt), {
            3: 200.0,
            4: 200.0,
            5: 200.0,
            6: 200.0,
            7: 200.0,
            8: 200.0,
        })

    def test_distribution_wizard_rounds_remainder_into_last_month(self):
        receipt = self._create_receipt(amount=1000.0)

        wizard = self.env["tenenet.project.cashflow.distribute.wizard"].create({
            "receipt_id": receipt.id,
            "amount": 1000.0,
            "date_from": "2027-03-01",
            "date_to": "2027-08-31",
        })
        wizard.action_distribute()
        receipt.invalidate_recordset(["cashflow_ids"])
        amounts_by_month = self._amounts_by_month(receipt)

        self.assertAlmostEqual(sum(amounts_by_month.values()), 1000.0, places=2)
        self.assertAlmostEqual(amounts_by_month[3], 166.67, places=2)
        self.assertAlmostEqual(amounts_by_month[8], 166.65, places=2)

    def test_distribution_wizard_rejects_cross_year_span(self):
        receipt = self._create_receipt()

        with self.assertRaises(ValidationError):
            self.env["tenenet.project.cashflow.distribute.wizard"].create({
                "receipt_id": receipt.id,
                "amount": 1200.0,
                "date_from": "2027-11-01",
                "date_to": "2028-01-31",
            })

    def test_distribution_wizard_defaults_follow_existing_receipt_cashflow(self):
        receipt = self._create_receipt(amount=1200.0)
        receipt.distribute_cashflow_span(fields.Date.to_date("2027-05-01"), fields.Date.to_date("2027-07-31"))

        wizard = self.env["tenenet.project.cashflow.distribute.wizard"].with_context(
            default_receipt_id=receipt.id
        ).create({"receipt_id": receipt.id})

        self.assertEqual(wizard.date_from, fields.Date.to_date("2027-05-01"))
        self.assertEqual(wizard.date_to, fields.Date.to_date("2027-07-31"))
        self.assertEqual(wizard.amount, 1200.0)
