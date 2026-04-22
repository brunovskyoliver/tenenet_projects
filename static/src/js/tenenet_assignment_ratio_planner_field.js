/** @odoo-module **/

import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

import { Component, onWillStart, useExternalListener, useState } from "@odoo/owl";

import {
    MONTHS,
    getMonthLabel,
    normalizeRange,
    parseAmount,
    roundAmount,
} from "./tenenet_month_planner_utils";

class TenenetAssignmentRatioPlannerDialog extends Component {
    static template = "tenenet_projects.TenenetAssignmentRatioPlannerDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        rowLabel: String,
        year: Number,
        entries: Array,
        fallbackRatio: Number,
        hasExistingAllocation: Boolean,
        save: Function,
        clear: Function,
    };

    setup() {
        this.state = useState({
            saving: false,
            entries: this.props.entries.map((entry) => ({ ...entry })),
        });
    }

    get entries() {
        return this.state.entries;
    }

    getMonthLabel(month) {
        return getMonthLabel(month);
    }

    formatRatio(value) {
        return roundAmount(value).toFixed(2);
    }

    onRatioChange(month, ev) {
        const entry = this.state.entries.find((item) => item.month === month);
        if (!entry) {
            return;
        }
        entry.amount = Math.min(100, Math.max(0, parseAmount(ev.target.value)));
        entry.manual = true;
        ev.target.value = this.formatRatio(entry.amount);
    }

    serializeEntries() {
        return Object.fromEntries(
            this.state.entries.map((entry) => [String(entry.month), roundAmount(entry.amount)])
        );
    }

    async onSave() {
        if (this.state.saving) {
            return;
        }
        this.state.saving = true;
        try {
            const shouldClose = await this.props.save({ monthRatios: this.serializeEntries() });
            if (shouldClose !== false) {
                this.props.close();
            }
        } finally {
            this.state.saving = false;
        }
    }

    async onClear() {
        if (this.state.saving) {
            return;
        }
        this.state.saving = true;
        try {
            const shouldClose = await this.props.clear();
            if (shouldClose !== false) {
                this.props.close();
            }
        } finally {
            this.state.saving = false;
        }
    }
}

export class TenenetAssignmentRatioPlannerField extends Component {
    static template = "tenenet_projects.TenenetAssignmentRatioPlannerField";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.state = useState({
            loading: true,
            year: this.initialYear,
            row: null,
            zeroMode: false,
            drag: this._emptyDragState(),
        });

        onWillStart(async () => {
            await this.loadPlannerData();
        });

        useExternalListener(window, "pointerup", this.onGlobalPointerUp.bind(this));
    }

    get initialYear() {
        return this.props.record.data[this.props.name]?.current_year || new Date().getFullYear();
    }

    get hasRecord() {
        return !!this.props.record.resId;
    }

    get months() {
        return MONTHS;
    }

    _emptyDragState() {
        return {
            active: false,
            startMonth: null,
            endMonth: null,
        };
    }

    async loadPlannerData(year = this.state.year) {
        if (!this.hasRecord) {
            this.state.loading = false;
            this.state.row = null;
            return;
        }
        this.state.loading = true;
        try {
            this.state.row = await this.orm.call("tenenet.project.assignment", "get_ratio_planner_data", [
                [this.props.record.resId],
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
        if (!this.state.row || this.state.loading) {
            return;
        }
        ev.preventDefault();
        this.state.drag.active = true;
        this.state.drag.startMonth = month;
        this.state.drag.endMonth = month;
    }

    onCellPointerEnter(month) {
        if (!this.state.drag.active) {
            return;
        }
        this.state.drag.endMonth = month;
    }

    async onGlobalPointerUp() {
        if (!this.state.drag.active || !this.state.row) {
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
            amount: roundAmount(this.state.row.months?.[String(month)] || 0),
            manual: true,
        }));
    }

    openEditorDialog(selection) {
        const explicit = new Set(this.state.row.explicit_months || []);
        this.dialog.add(TenenetAssignmentRatioPlannerDialog, {
            rowLabel: this.state.row.label,
            year: this.state.row.year,
            fallbackRatio: this.state.row.fallback_ratio,
            entries: this.buildDialogEntries(selection),
            hasExistingAllocation: selection.selectedMonths.some((month) => explicit.has(month)),
            save: (payload) => this.applySelection(payload),
            clear: () => this.clearSelection(selection),
        });
    }

    async applySelection(payload) {
        try {
            await this.orm.call("tenenet.project.assignment", "set_month_ratios", [
                [this.props.record.resId],
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
                [this.props.record.resId],
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
        return (this.state.row?.explicit_months || []).includes(month);
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

    formatCellValue(month) {
        const value = this.state.row?.months?.[String(month)] || 0;
        return `${roundAmount(value).toFixed(2)} %`;
    }
}

registry.category("fields").add("tenenet_assignment_ratio_planner", {
    component: TenenetAssignmentRatioPlannerField,
    supportedTypes: ["json"],
});
