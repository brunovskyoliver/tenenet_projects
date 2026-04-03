import { AccountReport } from "@account_reports/components/account_report/account_report";
import { AccountReportFilters } from "@account_reports/components/account_report/filters/filters";

const { DateTime } = luxon;

export class TenenetUtilizationReportFilters extends AccountReportFilters {
    static template = "tenenet_projects.TenenetUtilizationReportFilters";

    get currentMonthValue() {
        return DateTime.now().startOf("month");
    }

    get selectedMonthValue() {
        const dateTo = this.controller.cachedFilterOptions.date?.date_to;
        const selectedMonth = dateTo ? DateTime.fromISO(dateTo) : this.currentMonthValue;
        return selectedMonth.isValid ? selectedMonth.startOf("month") : this.currentMonthValue;
    }

    get monthFilterLabel() {
        return this.selectedMonthValue.toFormat("MMM yyyy");
    }

    get selectedMonthOffset() {
        return Math.round(this.selectedMonthValue.diff(this.currentMonthValue, "months").months);
    }

    displayPeriod(periodType) {
        if (periodType === "month") {
            return this.monthFilterLabel;
        }
        return super.displayPeriod(periodType);
    }

    async _syncMonthOptions(monthOffset = this.selectedMonthOffset) {
        this.dateFilter.month = monthOffset;
        await this.controller.updateOption("date.filter", this.getDateFilter("month"));
        await this.controller.updateOption("date.period", monthOffset);
    }

    async selectMonthPeriod() {
        await this._syncMonthOptions(this.dateFilter.month);
        await this.applyFilters("date.period", 0);
    }

    async selectMonth(date) {
        if (!date) {
            return;
        }

        const selectedMonth = date.startOf("month");
        const offset = Math.round(selectedMonth.diff(this.currentMonthValue, "months").months);

        await this._syncMonthOptions(offset);
        await this.applyFilters("date.period", 0);
    }

    get filterWarnings() {
        return this.controller.cachedFilterOptions?.tenenet_filter_warnings || false;
    }

    async toggleFilterWarnings() {
        await this._syncMonthOptions();
        await this.controller.updateOption("tenenet_filter_warnings", !this.filterWarnings);
        await this.applyFilters("tenenet_filter_warnings", 0);
    }
}

AccountReport.registerCustomComponent(TenenetUtilizationReportFilters);
