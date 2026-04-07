"""
Migration 19.0.5.8.0 → 19.0.5.8.1

Drop stale customized views that still request the removed ``note`` field
from ``tenenet.employee.site.key`` one2many subviews.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

_AFFECTED_VIEW_XMLIDS = (
    "tenenet_projects.view_hr_employee_form_tenenet",
    "tenenet_projects.view_tenenet_project_site_form",
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    base_views = env["ir.ui.view"].sudo().browse(_get_existing_view_ids(env))
    _log_unexpected_source_views(base_views)
    _cleanup_stale_site_key_customizations(env, base_views)


def _cleanup_stale_site_key_customizations(env, base_views):
    custom_view_model = env["ir.ui.view.custom"].sudo()
    stale_custom_views = custom_view_model.browse()

    if not base_views:
        _logger.info("No target base views found for stale site key customization cleanup.")
        return

    for base_view in base_views:
        stale_custom_views |= custom_view_model.search([
            ("ref_id", "=", base_view.id),
            ("arch", "ilike", "site_key_ids"),
            ("arch", "ilike", "note"),
        ])

    if not stale_custom_views:
        _logger.info("No stale site key customized views found.")
        return

    _logger.info(
        "Removing %d stale customized view(s) requesting note on tenenet.employee.site.key: %s",
        len(stale_custom_views),
        ", ".join(
            f"id={view.id}/ref={view.ref_id.id}/user={view.user_id.id}"
            for view in stale_custom_views
        ),
    )
    stale_custom_views.unlink()
    env.registry.clear_cache()
    env.registry.clear_cache("templates")
    env.invalidate_all()


def _log_unexpected_source_views(base_views):
    unexpected_views = base_views.filtered(
        lambda view: "site_key_ids" in (view.arch_db or "") and 'name="note"' in (view.arch_db or "")
    )
    if unexpected_views:
        _logger.warning(
            "Affected base views still contain note in site_key_ids and may need manual reset: %s",
            ", ".join(f"id={view.id}/key={view.key}" for view in unexpected_views),
        )


def _get_existing_view_ids(env):
    view_ids = []
    for xmlid in _AFFECTED_VIEW_XMLIDS:
        try:
            view_ids.append(env.ref(xmlid).id)
        except ValueError:
            _logger.warning("Could not resolve view xmlid during migration cleanup: %s", xmlid)
    return view_ids
