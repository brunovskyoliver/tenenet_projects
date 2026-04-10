/** @odoo-module **/

import { Component, onMounted, onPatched, onWillStart, useExternalListener, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

import {
    MONTHS,
    buildEntriesFromCurrentAmounts,
    buildEntriesFromMonthList,
    roundAmount,
    sumAmounts,
    normalizeRange,
} from "./tenenet_month_planner_utils";
import { TenenetBudgetLinePlannerDialog } from "./tenenet_budget_line_planner_field";

export class TenenetBudgetLinePlannerAction extends Component {
    static template = "tenenet_projects.TenenetBudgetLinePlannerAction";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.actionService = useService("action");
        this.rootRef = useRef("root");
        this.budgetLineId = this.props.action.params?.budget_line_id;
        this.state = useState({
            loading: true,
            deleting: false,
            row: null,
            zeroMode: false,
            drag: this._emptyDragState(),
        });

        onWillStart(async () => {
            await this.loadPlannerData();
        });

        onMounted(() => {
            this.applyModalSizing();
        });

        onPatched(() => {
            this.applyModalSizing();
        });

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

    async loadPlannerData() {
        if (!this.budgetLineId) {
            this.state.loading = false;
            this.state.row = null;
            return;
        }
        this.state.loading = true;
        try {
            this.state.row = await this.orm.call("tenenet.project.budget.line", "get_planner_data", [
                [this.budgetLineId],
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

    async onDelete() {
        if (this.state.deleting || !this.budgetLineId) {
            return;
        }
        this.state.deleting = true;
        try {
            await this.orm.call("tenenet.project.budget.line", "action_delete_with_reload", [
                [this.budgetLineId],
            ]);
            this.notification.add(_t("Rozpočtová položka bola odstránená."), { type: "success" });
            this.close();
        } catch (error) {
            this.notification.add(error.data?.message || _t("Nepodarilo sa odstrániť rozpočtovú položku."), {
                type: "danger",
            });
        } finally {
            this.state.deleting = false;
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
            !this.state.zeroMode &&
            normalized.startMonth === normalized.endMonth &&
            this.isFilled(normalized.startMonth)
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
                [this.budgetLineId],
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
                [this.budgetLineId],
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
                [this.budgetLineId],
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
    "tenenet_budget_line_planner_action",
    TenenetBudgetLinePlannerAction
);
