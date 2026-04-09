/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";

const CHART_HEIGHT = 260;
const CHART_WIDTH = 760;
const PADDING = { top: 20, right: 20, bottom: 34, left: 72 };
const SERIES_COLORS = {
    predicted_cf: "#0d6efd",
    real_expense: "#dc3545",
};

function formatAmount(value) {
    return new Intl.NumberFormat(undefined, {
        minimumFractionDigits: 0,
        maximumFractionDigits: 2,
    }).format(Number(value || 0));
}

function formatWithCurrency(value, state) {
    const formatted = formatAmount(value);
    if (!state.currency_symbol) {
        return formatted;
    }
    return state.currency_position === "before"
        ? `${state.currency_symbol} ${formatted}`
        : `${formatted} ${state.currency_symbol}`;
}

function roundUpTickStep(rawStep) {
    if (!Number.isFinite(rawStep) || rawStep <= 0) {
        return 1;
    }
    const magnitude = 10 ** Math.floor(Math.log10(rawStep));
    return Math.ceil(rawStep / magnitude) * magnitude;
}

export class TenenetFinanceComparisonChartField extends Component {
    static template = "tenenet_projects.TenenetFinanceComparisonChartField";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            year: this.initialYear,
            available_years: [],
            months: [],
            series: [],
            currency_symbol: "",
            currency_position: "after",
        });

        onWillStart(async () => {
            await this.loadChartData();
        });

        onWillUpdateProps(async (nextProps) => {
            const nextResId = nextProps.record.resId;
            const currentResId = this.props.record.resId;
            const nextYear = nextProps.record.data[nextProps.name]?.current_year || new Date().getFullYear();
            if (nextResId !== currentResId) {
                this.state.year = nextYear;
                await this.loadChartData(nextResId);
            }
        });
    }

    get initialYear() {
        return this.props.record.data[this.props.name]?.current_year || new Date().getFullYear();
    }

    get chartState() {
        return this.state;
    }

    get hasRecord() {
        return Boolean(this.props.record.resId);
    }

    get availableYears() {
        return this.chartState.available_years || [];
    }

    get canGoPrevious() {
        return this.availableYears.length && this.chartState.year > this.availableYears[0];
    }

    get canGoNext() {
        return this.availableYears.length && this.chartState.year < this.availableYears[this.availableYears.length - 1];
    }

    async loadChartData(resId = this.props.record.resId) {
        if (!resId) {
            this.state.loading = false;
            this.state.available_years = [];
            this.state.months = [];
            this.state.series = [];
            return;
        }
        this.state.loading = true;
        try {
            const data = await this.orm.call("tenenet.project", "get_finance_monthly_comparison_chart_data", [
                [resId],
                this.state.year,
            ]);
            this.state.year = data.year || this.state.year;
            this.state.available_years = data.available_years || [];
            this.state.months = data.months || [];
            this.state.series = data.series || [];
            this.state.currency_symbol = data.currency_symbol || "";
            this.state.currency_position = data.currency_position || "after";
        } catch (error) {
            this.notification.add(
                error.data?.message || _t("Nepodarilo sa načítať porovnanie cashflow a výdavkov."),
                { type: "danger" }
            );
            this.state.available_years = [];
            this.state.months = [];
            this.state.series = [];
        } finally {
            this.state.loading = false;
        }
    }

    async changeYear(step) {
        if (!this.hasRecord || this.state.loading) {
            return;
        }
        const nextYear = Number(this.chartState.year || 0) + step;
        if (!nextYear) {
            return;
        }
        this.state.year = nextYear;
        await this.loadChartData();
    }

    get maxValue() {
        const values = (this.chartState.series || []).flatMap((series) => series.values || []);
        const max = Math.max(...values, 0);
        return max > 0 ? max : 1;
    }

    get tickStep() {
        return roundUpTickStep(this.maxValue / 4);
    }

    get scaleMax() {
        return Math.max(this.tickStep * Math.ceil(this.maxValue / this.tickStep), this.tickStep);
    }

    get yTicks() {
        const ticks = [];
        for (let value = 0; value <= this.scaleMax + this.tickStep / 2; value += this.tickStep) {
            ticks.push({
                value,
                y: this.valueToY(value),
            });
        }
        return ticks;
    }

    get monthPoints() {
        const months = this.chartState.months || [];
        const width = this.plotRight - this.plotLeft;
        const step = months.length > 1 ? width / (months.length - 1) : 0;
        return months.map((label, index) => ({
            label,
            x: this.plotLeft + step * index,
        }));
    }

    get plotLeft() {
        return PADDING.left;
    }

    get plotRight() {
        return CHART_WIDTH - PADDING.right;
    }

    get plotBottom() {
        return CHART_HEIGHT - PADDING.bottom;
    }

    get yLabelX() {
        return this.plotLeft - 8;
    }

    valueToY(value) {
        const usableHeight = CHART_HEIGHT - PADDING.top - PADDING.bottom;
        const clampedValue = Math.min(Math.max(value || 0, 0), this.scaleMax);
        return PADDING.top + usableHeight - (clampedValue / this.scaleMax) * usableHeight;
    }

    polyline(series) {
        return (series.values || [])
            .map((value, index) => `${this.monthPoints[index]?.x || PADDING.left},${this.valueToY(value)}`)
            .join(" ");
    }

    colorFor(seriesKey) {
        return SERIES_COLORS[seriesKey] || "#6c757d";
    }

    amountLabel(value) {
        return formatWithCurrency(value, this.chartState);
    }

    axisAmountLabel(value) {
        return formatWithCurrency(Math.round(value || 0), this.chartState);
    }
}

export const tenenetFinanceComparisonChartField = {
    component: TenenetFinanceComparisonChartField,
    supportedTypes: ["json"],
};

registry.category("fields").add(
    "tenenet_finance_comparison_chart",
    tenenetFinanceComparisonChartField
);
