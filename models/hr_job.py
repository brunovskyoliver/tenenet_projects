from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrJob(models.Model):
    _inherit = "hr.job"

    salary_range_ids = fields.One2many(
        "tenenet.hr.job.salary.range",
        "job_id",
        string="Platové pásma",
    )
    salary_range_count = fields.Integer(
        string="Počet platových pásiem",
        compute="_compute_salary_range_count",
    )

    @api.depends("salary_range_ids")
    def _compute_salary_range_count(self):
        for job in self:
            job.salary_range_count = len(job.salary_range_ids)


class TenenetHrJobSalaryRange(models.Model):
    _name = "tenenet.hr.job.salary.range"
    _description = "Platové pásmo pozície"
    _order = "job_id, sequence, level_name, experience_years_from, id"

    sequence = fields.Integer(string="Poradie", default=10)
    job_id = fields.Many2one(
        "hr.job",
        string="Pozícia",
        required=True,
        ondelete="cascade",
        index=True,
    )
    level_name = fields.Char(
        string="Úroveň",
        required=True,
        help="Napr. Manažment, Top manažment, Výkonný manažment.",
    )
    experience_years_from = fields.Float(
        string="Praxe od (roky)",
        digits=(10, 2),
        default=0.0,
        required=True,
    )
    experience_years_to = fields.Float(
        string="Praxe do (roky)",
        digits=(10, 2),
        help="Prázdne = bez horného limitu.",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Mena",
        default=lambda self: self.env.ref("base.EUR"),
        required=True,
    )
    gross_min = fields.Monetary(
        string="Hrubá mzda od",
        currency_field="currency_id",
        required=True,
    )
    gross_max = fields.Monetary(
        string="Hrubá mzda do",
        currency_field="currency_id",
        required=True,
    )
    study_requirements = fields.Text(string="Odporúčané štúdium")
    notes = fields.Text(string="Poznámka")
    display_name = fields.Char(
        string="Názov pásma",
        compute="_compute_display_name",
    )

    _gross_range_check = models.Constraint(
        "CHECK(gross_min <= gross_max)",
        "Minimálna hrubá mzda nemôže byť vyššia ako maximálna.",
    )
    _experience_from_check = models.Constraint(
        "CHECK(experience_years_from >= 0)",
        "Roky praxe od musia byť nezáporné.",
    )

    @api.depends("job_id.name", "level_name", "experience_years_from", "experience_years_to")
    def _compute_display_name(self):
        for rec in self:
            if rec.experience_years_to:
                experience = f"{rec.experience_years_from:g} - {rec.experience_years_to:g} r."
            else:
                experience = f"od {rec.experience_years_from:g} r."
            rec.display_name = f"{rec.job_id.display_name or '-'} / {rec.level_name or '-'} / {experience}"

    @api.constrains("experience_years_from", "experience_years_to")
    def _check_experience_range(self):
        for rec in self:
            if rec.experience_years_to and rec.experience_years_to < rec.experience_years_from:
                raise ValidationError("Horná hranica praxe nemôže byť nižšia ako dolná hranica.")

    @api.constrains("job_id", "level_name", "experience_years_from", "experience_years_to")
    def _check_overlap_for_level(self):
        for rec in self:
            if not rec.job_id or not rec.level_name:
                continue

            rec_from = rec.experience_years_from or 0.0
            rec_to = rec.experience_years_to if rec.experience_years_to is not False else False
            peers = rec.job_id.salary_range_ids.filtered(
                lambda other: other.id != rec.id
                and (other.level_name or "").strip().casefold() == (rec.level_name or "").strip().casefold()
            )
            for other in peers:
                other_from = other.experience_years_from or 0.0
                other_to = other.experience_years_to if other.experience_years_to is not False else False
                if rec_to is not False and other_from > rec_to:
                    continue
                if other_to is not False and rec_from > other_to:
                    continue
                raise ValidationError(
                    "Roky praxe sa pre rovnakú úroveň pozície nesmú prekrývať."
                )
