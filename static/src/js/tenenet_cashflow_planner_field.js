/** @odoo-module **/

import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

import { Component, onWillStart, onWillUpdateProps, useExternalListener, useState } from "@odoo/owl";

const MONTHS = [
    { number: 1, label: "Jan" },
    { number: 2, label: "Feb" },
    { number: 3, label: "Mar" },
    { number: 4, label: "Apr" },
    { number: 5, label: "Máj" },
    { number: 6, label: "Jún" },
    { number: 7, label: "Júl" },
    { number: 8, label: "Aug" },
    { number: 9, label: "Sep" },
    { number: 10, label: "Okt" },
    { number: 11, label: "Nov" },
    { number: 12, label: "Dec" },
];

function roundAmount(value) {
    return Math.round((Number(value || 0) + Number.EPSILON) * 100) / 100;
}

function parseAmount(rawValue) {
    const normalized = String(rawValue ?? "")
        .replace(/\s+/g, "")
        .replace(",", ".");
    const value = parseFloat(normalized);
    return Number.isFinite(value) ? roundAmount(value) : 0;
}

function getMonthLabel(month) {
    return MONTHS.find((item) => item.number === month)?.label || String(month);
}

function normalizeRange(startMonth, endMonth) {
    return {
        startMonth: Math.min(startMonth, endMonth),
        endMonth: Math.max(startMonth, endMonth),
    };
}

function sumAmounts(values) {
    return roundAmount(values.reduce((sum, value) => sum + value, 0));
}

function distributeAcrossEntries(entries, totalAmount) {
    const unlockedEntries = entries.filter((entry) => !entry.manual);
    if (!unlockedEntries.length) {
        return;
    }

    const manualTotal = sumAmounts(
        entries.filter((entry) => entry.manual).map((entry) => entry.amount)
    );
    const amountForUnlocked = Math.max(0, roundAmount(totalAmount - manualTotal));
    const share = roundAmount(amountForUnlocked / unlockedEntries.length);
    let assigned = 0;

    unlockedEntries.forEach((entry, index) => {
        if (index === unlockedEntries.length - 1) {
            entry.amount = roundAmount(amountForUnlocked - assigned);
        } else {
            entry.amount = share;
            assigned = roundAmount(assigned + share);
        }
    });
}

function buildEntriesFromCurrentAmounts(startMonth, endMonth, currentMonthAmounts, totalAmount) {
    const entries = [];
    let currentTotal = 0;
    for (let month = startMonth; month <= endMonth; month++) {
        const amount = roundAmount(currentMonthAmounts[String(month)] || 0);
        currentTotal = roundAmount(currentTotal + amount);
        entries.push({
            month,
            amount,
            manual: false,
        });
    }
    if (Math.abs(currentTotal) < 0.00001 && totalAmount > 0) {
        distributeAcrossEntries(entries, totalAmount);
    }
    return entries;
}

function buildFreshEntries(startMonth, endMonth, totalAmount) {
    const entries = [];
    for (let month = startMonth; month <= endMonth; month++) {
        entries.push({
            month,
            amount: 0,
            manual: false,
        });
    }
    if (totalAmount > 0) {
        distributeAcrossEntries(entries, totalAmount);
    }
    return entries;
}

class TenenetCashflowPlannerDialog extends Component {
    static template = "tenenet_projects.TenenetCashflowPlannerDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        rowLabel: String,
        year: Number,
        receiptAmount: Number,
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

export class TenenetCashflowPlannerField extends Component {
    static template = "tenenet_projects.TenenetCashflowPlannerField";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            year: this.initialYear,
            rows: [],
            availableYears: [],
            currencySymbol: "",
            currencyPosition: "after",
            drag: this._emptyDragState(),
        });

        onWillStart(async () => {
            await this.loadPlannerData();
        });

        onWillUpdateProps(async (nextProps) => {
            const nextResId = nextProps.record.resId;
            const currentResId = this.props.record.resId;
            const nextYear = nextProps.record.data[nextProps.name]?.current_year || new Date().getFullYear();
            if (nextResId !== currentResId) {
                this.state.year = nextYear;
                await this.loadPlannerData(nextResId);
            }
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
            receiptId: null,
            startMonth: null,
            endMonth: null,
        };
    }

    async loadPlannerData(resId = this.props.record.resId) {
        if (!resId) {
            this.state.loading = false;
            this.state.rows = [];
            this.state.availableYears = [];
            return;
        }
        this.state.loading = true;
        try {
            const data = await this.orm.call("tenenet.project", "get_cashflow_planner_data", [
                [resId],
                this.state.year,
            ]);
            this.state.rows = data.rows || [];
            this.state.availableYears = data.available_years || [];
            this.state.currencySymbol = data.currency_symbol || "";
            this.state.currencyPosition = data.currency_position || "after";
            this.state.year = data.year || this.state.year;
        } catch (error) {
            this.notification.add(error.data?.message || _t("Nepodarilo sa načítať cashflow."), {
                type: "danger",
            });
            this.state.rows = [];
        } finally {
            this.state.loading = false;
            this.resetDrag();
        }
    }

    async changeYear(delta) {
        this.state.year += delta;
        await this.loadPlannerData();
    }

    onCellPointerDown(row, month, ev) {
        if (!this.hasRecord || this.state.loading) {
            return;
        }
        ev.preventDefault();
        this.state.drag.active = true;
        this.state.drag.receiptId = row.receipt_id;
        this.state.drag.startMonth = month;
        this.state.drag.endMonth = month;
    }

    onCellPointerEnter(row, month) {
        if (!this.state.drag.active || this.state.drag.receiptId !== row.receipt_id) {
            return;
        }
        this.state.drag.endMonth = month;
    }

    async onGlobalPointerUp() {
        if (!this.state.drag.active) {
            return;
        }
        const selection = this.getSelection();
        this.resetDrag();
        if (!selection) {
            return;
        }
        this.openEditorDialog(selection);
    }

    resetDrag() {
        Object.assign(this.state.drag, this._emptyDragState());
    }

    getAllocatedSpan(row, month) {
        let startMonth = month;
        let endMonth = month;
        while (startMonth > 1 && this.isFilled(row, startMonth - 1)) {
            startMonth -= 1;
        }
        while (endMonth < 12 && this.isFilled(row, endMonth + 1)) {
            endMonth += 1;
        }
        return { startMonth, endMonth };
    }

    getSelection() {
        const { receiptId, startMonth, endMonth } = this.state.drag;
        if (!receiptId || !startMonth || !endMonth) {
            return null;
        }
        const row = this.state.rows.find((item) => item.receipt_id === receiptId);
        if (!row) {
            return null;
        }

        let normalized = normalizeRange(startMonth, endMonth);
        if (
            normalized.startMonth === normalized.endMonth
            && this.isFilled(row, normalized.startMonth)
        ) {
            normalized = this.getAllocatedSpan(row, normalized.startMonth);
        }
        const allMonths = this.months.map((month) => month.number);
        const selectedMonths = allMonths.filter(
            (month) => month >= normalized.startMonth && month <= normalized.endMonth
        );
        const selectedTotal = sumAmounts(
            selectedMonths.map((month) => row.months?.[String(month)] || 0)
        );
        const totalDistributed = sumAmounts(
            allMonths.map((month) => row.months?.[String(month)] || 0)
        );
        const outsideTotal = roundAmount(totalDistributed - selectedTotal);
        const remainingAmount = Math.max(0, roundAmount(row.amount - totalDistributed));
        const maxDistributeAmount = Math.max(0, roundAmount(row.amount - outsideTotal));
        const initialDistributeAmount = selectedTotal > 0 ? selectedTotal : remainingAmount;

        return {
            receiptId,
            row,
            ...normalized,
            selectedMonths,
            selectedTotal,
            totalDistributed,
            outsideTotal,
            remainingAmount,
            maxDistributeAmount,
            initialDistributeAmount,
        };
    }

    buildDialogEntries(selection) {
        return buildEntriesFromCurrentAmounts(
            selection.startMonth,
            selection.endMonth,
            selection.row.months || {},
            selection.initialDistributeAmount
        );
    }

    openEditorDialog(selection) {
        this.dialog.add(TenenetCashflowPlannerDialog, {
            rowLabel: selection.row.label,
            year: this.state.year,
            receiptAmount: selection.row.amount,
            distributeAmount: selection.initialDistributeAmount,
            maxDistributeAmount: selection.maxDistributeAmount,
            remainingAmount: selection.remainingAmount,
            currencySymbol: this.state.currencySymbol,
            currencyPosition: this.state.currencyPosition,
            entries: this.buildDialogEntries(selection),
            hasExistingAllocation: selection.selectedTotal > 0,
            startMonth: selection.startMonth,
            endMonth: selection.endMonth,
            save: (payload) => this.applySelection(selection, payload),
        });
    }

    buildUpdatedYearMonthAmounts(selection, payload) {
        const updated = {};
        for (const month of this.months.map((item) => item.number)) {
            updated[String(month)] = roundAmount(selection.row.months?.[String(month)] || 0);
        }
        for (const month of selection.selectedMonths) {
            updated[String(month)] = roundAmount(payload.monthAmounts[String(month)] || 0);
        }
        return updated;
    }

    async applySelection(selection, payload) {
        try {
            await this.orm.call("tenenet.project.receipt", "set_cashflow_month_amounts", [
                [selection.receiptId],
                this.state.year,
                this.buildUpdatedYearMonthAmounts(selection, payload),
            ]);
            this.notification.add(_t("Cashflow bol aktualizovaný."), { type: "success" });
            await this.loadPlannerData();
        } catch (error) {
            this.notification.add(error.data?.message || _t("Nepodarilo sa uložiť cashflow."), {
                type: "danger",
            });
            return false;
        }
        return true;
    }

    isFilled(row, month) {
        const value = row.months?.[String(month)] || 0;
        return Math.abs(value) > 0.00001;
    }

    isSelected(row, month) {
        if (!this.state.drag.active || this.state.drag.receiptId !== row.receipt_id) {
            return false;
        }
        const { startMonth, endMonth } = normalizeRange(
            this.state.drag.startMonth,
            this.state.drag.endMonth
        );
        return month >= startMonth && month <= endMonth;
    }

    isSelectionEdge(row, month) {
        if (!this.isSelected(row, month)) {
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

    formatCellValue(row, month) {
        const value = row.months?.[String(month)] || 0;
        if (Math.abs(value) < 0.00001) {
            return "";
        }
        return this.formatAmount(value);
    }
}

registry.category("fields").add("tenenet_cashflow_planner", {
    component: TenenetCashflowPlannerField,
    supportedTypes: ["json"],
});
