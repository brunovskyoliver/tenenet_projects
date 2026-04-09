/** @odoo-module **/

import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

import { Component, onWillStart, useExternalListener, useState } from "@odoo/owl";

import {
    MONTHS,
    buildEntriesFromCurrentAmounts,
    buildEntriesFromMonthList,
    buildFreshEntries,
    distributeAcrossEntries,
    getMonthLabel,
    normalizeRange,
    parseAmount,
    roundAmount,
    sumAmounts,
} from "./tenenet_month_planner_utils";

export class TenenetBudgetLinePlannerDialog extends Component {
    static template = "tenenet_projects.TenenetBudgetLinePlannerDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        rowLabel: String,
        year: Number,
        totalAmount: Number,
        distributeAmount: Number,
        maxDistributeAmount: Number,
        remainingAmount: Number,
        currencySymbol: { type: String, optional: true },
        currencyPosition: { type: String, optional: true },
        entries: Array,
        hasExistingAllocation: Boolean,
        startMonth: Number,
        endMonth: Number,
        save: Function,
    };

    setup() {
        this.state = useState({
            saving: false,
            distributeAmount: roundAmount(this.props.distributeAmount),
            entries: this.props.entries.map((entry) => ({ ...entry })),
        });
    }

    get entries() {
        return this.state.entries;
    }

    get totalAssigned() {
        return sumAmounts(this.state.entries.map((entry) => entry.amount));
    }

    get manualTotal() {
        return sumAmounts(
            this.state.entries.filter((entry) => entry.manual).map((entry) => entry.amount)
        );
    }

    getMonthLabel(month) {
        return getMonthLabel(month);
    }

    formatAmount(value) {
        return new Intl.NumberFormat(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        }).format(roundAmount(value));
    }

    formatAmountInput(value) {
        return roundAmount(value).toFixed(2);
    }

    formatYear(value) {
        return String(value || "");
    }

    formatAmountWithCurrency(value) {
        const formatted = this.formatAmount(value);
        if (!this.props.currencySymbol) {
            return formatted;
        }
        return this.props.currencyPosition === "before"
            ? `${this.props.currencySymbol} ${formatted}`
            : `${formatted} ${this.props.currencySymbol}`;
    }

    clampDistributeAmount(value) {
        const maxAmount = roundAmount(this.props.maxDistributeAmount);
        const minAmount = roundAmount(this.manualTotal);
        return Math.min(maxAmount, Math.max(minAmount, roundAmount(value)));
    }

    onDistributeAmountChange(ev) {
        this.state.distributeAmount = this.clampDistributeAmount(parseAmount(ev.target.value));
        if (!this.state.entries.some((entry) => !entry.manual)) {
            this.state.distributeAmount = this.manualTotal;
        }
        distributeAcrossEntries(this.state.entries, this.state.distributeAmount);
        ev.target.value = this.formatAmountInput(this.state.distributeAmount);
    }

    onAmountChange(month, ev) {
        const entry = this.state.entries.find((item) => item.month === month);
        if (!entry) {
            return;
        }
        entry.manual = true;
        const otherManualTotal = sumAmounts(
            this.state.entries
                .filter((item) => item.manual && item.month !== month)
                .map((item) => item.amount)
        );
        const maxEditable = Math.max(0, roundAmount(this.state.distributeAmount - otherManualTotal));
        entry.amount = Math.min(maxEditable, Math.max(0, parseAmount(ev.target.value)));
        distributeAcrossEntries(this.state.entries, this.state.distributeAmount);
        ev.target.value = this.formatAmountInput(entry.amount);
    }

    onRemoveMonth(month) {
        const index = this.state.entries.findIndex((entry) => entry.month === month);
        if (index < 0) {
            return;
        }
        this.state.entries.splice(index, 1);
        if (!this.state.entries.length) {
            this.state.distributeAmount = 0;
            return;
        }
        this.state.distributeAmount = Math.max(this.manualTotal, this.state.distributeAmount);
        distributeAcrossEntries(this.state.entries, this.state.distributeAmount);
    }

    onResetSelection() {
        this.state.entries.splice(
            0,
            this.state.entries.length,
            ...buildFreshEntries(
                this.props.startMonth,
                this.props.endMonth,
                this.state.distributeAmount
            )
        );
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
            const shouldClose = await this.props.save({
                distributeAmount: this.state.distributeAmount,
                monthAmounts: this.serializeEntries(),
            });
            if (shouldClose !== false) {
                this.props.close();
            }
        } finally {
            this.state.saving = false;
        }
    }
}

export class TenenetBudgetLinePlannerField extends Component {
    static template = "tenenet_projects.TenenetBudgetLinePlannerField";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            row: null,
            zeroMode: false,
            drag: this._emptyDragState(),
        });

        onWillStart(async () => {
            await this.loadPlannerData();
        });

        useExternalListener(window, "pointerup", this.onGlobalPointerUp.bind(this));
    }

    get months() {
        return MONTHS;
    }

    get hasRecord() {
        return !!this.props.record.resId;
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

    async loadPlannerData() {
        if (!this.hasRecord) {
            this.state.loading = false;
            this.state.row = null;
            return;
        }
        this.state.loading = true;
        try {
            this.state.row = await this.orm.call("tenenet.project.budget.line", "get_planner_data", [
                [this.props.record.resId],
            ]);
        } catch (error) {
            this.notification.add(error.data?.message || _t("Nepodarilo sa načítať plán rozpočtu."), {
                type: "danger",
            });
            this.state.row = null;
        } finally {
            this.state.loading = false;
            this.resetDrag();
        }
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
        if (!this.state.drag.active) {
            return;
        }
        this.state.drag.endMonth = month;
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
            const adjustmentSelection = this.buildZeroAdjustmentSelection(selection);
            if (!adjustmentSelection) {
                await this.applyZeroSelection(selection);
                return;
            }
            this.openEditorDialog(adjustmentSelection, {
                entries: buildEntriesFromMonthList(
                    adjustmentSelection.selectedMonths,
                    {},
                    adjustmentSelection.initialDistributeAmount
                ),
                distributeAmount: adjustmentSelection.initialDistributeAmount,
                maxDistributeAmount: adjustmentSelection.maxDistributeAmount,
                remainingAmount: adjustmentSelection.remainingAmount,
                hasExistingAllocation: false,
                save: (payload) =>
                    this.applyZeroSelectionWithAdjustment(selection, adjustmentSelection, payload),
            });
            return;
        }
        this.openEditorDialog(selection);
    }

    resetDrag() {
        Object.assign(this.state.drag, this._emptyDragState());
    }

    isFilled(month) {
        const value = this.row?.months?.[String(month)] || 0;
        return Math.abs(value) > 0.00001;
    }

    getAllocatedSpan(month) {
        let startMonth = month;
        let endMonth = month;
        while (startMonth > 1 && this.isFilled(startMonth - 1)) {
            startMonth -= 1;
        }
        while (endMonth < 12 && this.isFilled(endMonth + 1)) {
            endMonth += 1;
        }
        return { startMonth, endMonth };
    }

    getSelection() {
        if (!this.row || !this.state.drag.startMonth || !this.state.drag.endMonth) {
            return null;
        }
        let normalized = normalizeRange(this.state.drag.startMonth, this.state.drag.endMonth);
        if (
            !this.state.zeroMode
            && normalized.startMonth === normalized.endMonth
            && this.isFilled(normalized.startMonth)
        ) {
            normalized = this.getAllocatedSpan(normalized.startMonth);
        }
        const allMonths = this.months.map((month) => month.number);
        const selectedMonths = allMonths.filter(
            (month) => month >= normalized.startMonth && month <= normalized.endMonth
        );
        const selectedTotal = sumAmounts(
            selectedMonths.map((month) => this.row.months?.[String(month)] || 0)
        );
        const totalDistributed = sumAmounts(
            allMonths.map((month) => this.row.months?.[String(month)] || 0)
        );
        const outsideTotal = roundAmount(totalDistributed - selectedTotal);
        const remainingAmount = Math.max(0, roundAmount(this.row.amount - totalDistributed));
        const maxDistributeAmount = Math.max(0, roundAmount(this.row.amount - outsideTotal));
        const initialDistributeAmount = selectedTotal > 0 ? selectedTotal : remainingAmount;
        return {
            ...normalized,
            selectedMonths,
            selectedTotal,
            totalDistributed,
            remainingAmount,
            maxDistributeAmount,
            initialDistributeAmount,
        };
    }

    buildDialogEntries(selection) {
        return buildEntriesFromCurrentAmounts(
            selection.startMonth,
            selection.endMonth,
            this.row.months || {},
            selection.initialDistributeAmount
        );
    }

    buildZeroAdjustmentSelection(selection) {
        const selectedSet = new Set(selection.selectedMonths);
        const retainedMonths = this.months
            .map((item) => item.number)
            .filter((month) => !selectedSet.has(month));
        if (!retainedMonths.length) {
            return null;
        }
        return {
            row: this.row,
            startMonth: retainedMonths[0],
            endMonth: retainedMonths[retainedMonths.length - 1],
            selectedMonths: retainedMonths,
            selectedTotal: sumAmounts(
                retainedMonths.map((month) => this.row.months?.[String(month)] || 0)
            ),
            totalDistributed: selection.totalDistributed,
            remainingAmount: Math.max(0, roundAmount(this.row.amount - selection.totalDistributed)),
            maxDistributeAmount: roundAmount(this.row.amount),
            initialDistributeAmount: selection.totalDistributed,
        };
    }

    openEditorDialog(selection, dialogOptions = {}) {
        this.dialog.add(TenenetBudgetLinePlannerDialog, {
            rowLabel: this.row.label,
            year: this.row.year,
            totalAmount: this.row.amount,
            distributeAmount:
                dialogOptions.distributeAmount ?? selection.initialDistributeAmount,
            maxDistributeAmount:
                dialogOptions.maxDistributeAmount ?? selection.maxDistributeAmount,
            remainingAmount: dialogOptions.remainingAmount ?? selection.remainingAmount,
            currencySymbol: this.row.currency_symbol,
            currencyPosition: this.row.currency_position,
            entries: dialogOptions.entries ?? this.buildDialogEntries(selection),
            hasExistingAllocation:
                dialogOptions.hasExistingAllocation ?? selection.selectedTotal > 0,
            startMonth: selection.startMonth,
            endMonth: selection.endMonth,
            save: dialogOptions.save || ((payload) => this.applySelection(selection, payload)),
        });
    }

    buildUpdatedMonthAmounts(selection, payload) {
        const updated = {};
        for (const month of this.months.map((item) => item.number)) {
            updated[String(month)] = roundAmount(this.row.months?.[String(month)] || 0);
        }
        for (const month of selection.selectedMonths) {
            updated[String(month)] = roundAmount(payload.monthAmounts[String(month)] || 0);
        }
        return updated;
    }

    async applySelection(selection, payload) {
        try {
            await this.orm.call("tenenet.project.budget.line", "set_month_amounts", [
                [this.props.record.resId],
                this.buildUpdatedMonthAmounts(selection, payload),
            ]);
            this.notification.add(_t("Plán rozpočtu bol aktualizovaný."), { type: "success" });
            await this.loadPlannerData();
        } catch (error) {
            this.notification.add(error.data?.message || _t("Nepodarilo sa uložiť plán rozpočtu."), {
                type: "danger",
            });
            return false;
        }
        return true;
    }

    async applyZeroSelection(selection) {
        const updated = {};
        for (const month of this.months.map((item) => item.number)) {
            updated[String(month)] = roundAmount(this.row.months?.[String(month)] || 0);
        }
        for (const month of selection.selectedMonths) {
            updated[String(month)] = 0;
        }
        try {
            await this.orm.call("tenenet.project.budget.line", "set_month_amounts", [
                [this.props.record.resId],
                updated,
            ]);
            this.notification.add(_t("Vybrané mesiace boli vynulované."), { type: "success" });
            await this.loadPlannerData();
        } catch (error) {
            this.notification.add(error.data?.message || _t("Nepodarilo sa upraviť plán rozpočtu."), {
                type: "danger",
            });
        }
    }

    async applyZeroSelectionWithAdjustment(zeroSelection, adjustmentSelection, payload) {
        const updated = {};
        for (const month of this.months.map((item) => item.number)) {
            updated[String(month)] = roundAmount(this.row.months?.[String(month)] || 0);
        }
        for (const month of zeroSelection.selectedMonths) {
            updated[String(month)] = 0;
        }
        for (const month of adjustmentSelection.selectedMonths) {
            updated[String(month)] = roundAmount(payload.monthAmounts[String(month)] || 0);
        }
        try {
            await this.orm.call("tenenet.project.budget.line", "set_month_amounts", [
                [this.props.record.resId],
                updated,
            ]);
            this.notification.add(_t("Plán rozpočtu bol aktualizovaný."), { type: "success" });
            await this.loadPlannerData();
        } catch (error) {
            this.notification.add(error.data?.message || _t("Nepodarilo sa upraviť plán rozpočtu."), {
                type: "danger",
            });
            return false;
        }
        return true;
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

    formatAmount(value) {
        const roundedValue = roundAmount(value || 0);
        const hasDecimals = Math.abs(roundedValue - Math.round(roundedValue)) > 0.00001;
        return new Intl.NumberFormat(undefined, {
            minimumFractionDigits: hasDecimals ? 2 : 0,
            maximumFractionDigits: 2,
        }).format(roundedValue);
    }

    formatCellValue(month) {
        const value = this.row?.months?.[String(month)] || 0;
        if (Math.abs(value) < 0.00001) {
            return "";
        }
        return this.formatAmount(value);
    }
}

registry.category("fields").add("tenenet_budget_line_planner", {
    component: TenenetBudgetLinePlannerField,
    supportedTypes: ["json"],
});
