from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetEmployeeTraining(TransactionCase):
    def setUp(self):
        super().setUp()
        self.employee = self.env["hr.employee"].create({"name": "Training Employee"})

    def test_training_can_be_created_with_attachment(self):
        training = self.env["tenenet.employee.training"].create({
            "employee_id": self.employee.id,
            "name": "Krízová intervencia",
            "training_type": "internal",
            "provider": "TENENET",
        })
        self.env["ir.attachment"].create({
            "name": "certificate.pdf",
            "datas": "UERG",
            "mimetype": "application/pdf",
            "res_model": "tenenet.employee.training",
            "res_id": training.id,
        })

        attachment_count = self.env["ir.attachment"].search_count([
            ("res_model", "=", "tenenet.employee.training"),
            ("res_id", "=", training.id),
        ])
        self.assertEqual(training.employee_id, self.employee)
        self.assertEqual(training.training_type, "internal")
        self.assertEqual(attachment_count, 1)

    def test_employee_cascade_removes_trainings(self):
        training = self.env["tenenet.employee.training"].create({
            "employee_id": self.employee.id,
            "name": "Supervízia",
        })
        self.employee.unlink()
        self.assertFalse(training.exists())
