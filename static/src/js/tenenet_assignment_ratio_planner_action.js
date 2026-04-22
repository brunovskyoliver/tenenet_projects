/** @odoo-module **/

import { Component, onMounted, onPatched, onWillStart, useExternalListener, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

import {
    MONTHS,
    normalizeRange,
    roundAmount,
} from "./tenenet_month_planner_utils";
import { TenenetAssignmentRatioPlannerDialog } from "./tenenet_assignment_ratio_planner_field";

export class TenenetAssignmentRatioPlannerAction extends Component {
    static template = "tenenet_projects.TenenetAssignmentRatioPlannerAction";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.actionService = useService("action");
        this.rootRef = useRef("root");
        this.assignmentId = this.props.action.params?.assignment_id;
        this.state = useState({
            loading: true,
            year: this.props.action.params?.year || new Date().getFullYear(),
            row: null,
            zeroMode: false,
            drag: this._emptyDragState(),
        });

        onWillStart(async () => {
            await this.loadPlannerData();
        });
        onMounted(() => this.applyModalSizing());
        onPatched(() => this.applyModalSizing());

        useExternalListener(window, "pointerup", this.onGlobalPointerUp.bind(this));
        useExternalListener(window, "resize", this.applyModalSizing.bind(this));
    }

    get months() {
        return MONTHS;
    }

    get row() {
        return this.state.row;
    }

    _emptyDragState() {
        return {
            active: false,
            startMonth: null,
            endMonth: null,
        };
    }

    async loadPlannerData(year = this.state.year) {
        if (!this.assignmentId) {
            this.state.loading = false;
            this.state.row = null;
            return;
        }
        this.state.loading = true;
        try {
            this.state.row = await this.orm.call("tenenet.project.assignment", "get_ratio_planner_data", [
                [this.assignmentId],
                year,
            ]);
            this.state.year = this.state.row.year;
        } catch (error) {
            this.notification.add(error.data?.message || _t("Nepodarilo sa načítať alokačný plán."), {
                type: "danger",
            });
            this.state.row = null;
        } finally {
            this.state.loading = false;
            this.resetDrag();
        }
    }

    async changeYear(delta) {
        await this.loadPlannerData(this.state.year + delta);
    }

    onToggleZeroMode(ev) {
        this.state.zeroMode = Boolean(ev.target.checked);
        this.resetDrag();
    }

    onCellPointerDown(month, ev) {
        if (!this.row || this.state.loading) {
            return;
        }
        ev.preventDefault();
        this.state.drag.active = true;
        this.state.drag.startMonth = month;
        this.state.drag.endMonth = month;
    }

    onCellPointerEnter(month) {
        if (this.state.drag.active) {
            this.state.drag.endMonth = month;
        }
    }

    async onGlobalPointerUp() {
        if (!this.state.drag.active || !this.row) {
            return;
        }
        const selection = this.getSelection();
        this.resetDrag();
        if (!selection) {
            return;
        }
        if (this.state.zeroMode) {
            await this.applyZeroSelection(selection);
            return;
        }
        this.openEditorDialog(selection);
    }

    resetDrag() {
        Object.assign(this.state.drag, this._emptyDragState());
    }

    getSelection() {
        if (!this.state.drag.startMonth || !this.state.drag.endMonth) {
            return null;
        }
        const normalized = normalizeRange(this.state.drag.startMonth, this.state.drag.endMonth);
        const selectedMonths = this.months
            .map((month) => month.number)
            .filter((month) => month >= normalized.startMonth && month <= normalized.endMonth);
        return { ...normalized, selectedMonths };
    }

    buildDialogEntries(selection) {
        return selection.selectedMonths.map((month) => ({
            month,
            amount: roundAmount(this.row.months?.[String(month)] || 0),
            manual: true,
        }));
    }

    openEditorDialog(selection) {
        const explicit = new Set(this.row.explicit_months || []);
        this.dialog.add(TenenetAssignmentRatioPlannerDialog, {
            rowLabel: this.row.label,
            year: this.row.year,
            fallbackRatio: this.row.fallback_ratio,
            entries: this.buildDialogEntries(selection),
            hasExistingAllocation: selection.selectedMonths.some((month) => explicit.has(month)),
            save: (payload) => this.applySelection(payload),
            clear: () => this.clearSelection(selection),
        });
    }

    async applySelection(payload) {
        try {
            await this.orm.call("tenenet.project.assignment", "set_month_ratios", [
                [this.assignmentId],
                this.state.year,
                payload.monthRatios,
            ]);
            this.notification.add(_t("Alokačný plán bol aktualizovaný."), { type: "success" });
            await this.loadPlannerData();
        } catch (error) {
            this.notification.add(error.data?.message || _t("Nepodarilo sa uložiť alokačný plán."), {
                type: "danger",
            });
            return false;
        }
        return true;
    }

    async applyZeroSelection(selection) {
        const monthRatios = Object.fromEntries(selection.selectedMonths.map((month) => [String(month), 0]));
        return this.applySelection({ monthRatios });
    }

    async clearSelection(selection) {
        try {
            await this.orm.call("tenenet.project.assignment", "clear_month_ratios", [
                [this.assignmentId],
                this.state.year,
                selection.selectedMonths,
            ]);
            this.notification.add(_t("Vybrané mesiace používajú predvolený úväzok."), { type: "success" });
            await this.loadPlannerData();
        } catch (error) {
            this.notification.add(error.data?.message || _t("Nepodarilo sa vymazať alokačný plán."), {
                type: "danger",
            });
            return false;
        }
        return true;
    }

    isExplicit(month) {
        return (this.row?.explicit_months || []).includes(month);
    }

    isSelected(month) {
        if (!this.state.drag.active) {
            return false;
        }
        const { startMonth, endMonth } = normalizeRange(
            this.state.drag.startMonth,
            this.state.drag.endMonth
        );
        return month >= startMonth && month <= endMonth;
    }

    isSelectionEdge(month) {
        if (!this.isSelected(month)) {
            return false;
        }
        const { startMonth, endMonth } = normalizeRange(
            this.state.drag.startMonth,
            this.state.drag.endMonth
        );
        return month === startMonth || month === endMonth;
    }

    formatRatio(value) {
        return `${roundAmount(value).toFixed(2)} %`;
    }

    formatCellValue(month) {
        return this.formatRatio(this.row?.months?.[String(month)] || 0);
    }

    close() {
        if (this.env.dialogData?.close) {
            this.env.dialogData.close();
            return;
        }
        this.actionService.restore();
    }

    applyModalSizing() {
        const root = this.rootRef.el;
        if (!root) {
            return;
        }
        const dialog = root.closest(".modal-dialog");
        const content = root.closest(".modal-content");
        if (!dialog || !content) {
            return;
        }
        const mobile = window.innerWidth < 992;
        const targetWidth = mobile ? "calc(100vw - 1rem)" : "1320px";
        const maxWidth = mobile ? "calc(100vw - 1rem)" : "calc(100vw - 2rem)";

        dialog.classList.add("o_tenenet_budget_line_planner_modal");
        dialog.style.setProperty("--bs-modal-width", targetWidth, "important");
        dialog.style.setProperty("--modal-width", targetWidth, "important");
        dialog.style.setProperty("width", targetWidth, "important");
        dialog.style.setProperty("max-width", maxWidth, "important");

        content.style.setProperty("width", mobile ? "100%" : "max-content", "important");
        content.style.setProperty("max-width", maxWidth, "important");
    }
}

registry.category("actions").add(
    "tenenet_assignment_ratio_planner_action",
    TenenetAssignmentRatioPlannerAction
);
