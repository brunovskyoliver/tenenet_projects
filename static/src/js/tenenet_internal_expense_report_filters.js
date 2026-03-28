import { AccountReport } from "@account_reports/components/account_report/account_report";
import { AccountReportFilters } from "@account_reports/components/account_report/filters/filters";

const { DateTime } = luxon;

export class TenenetInternalExpenseReportFilters extends AccountReportFilters {
    static template = "tenenet_projects.TenenetInternalExpenseReportFilters";

    get selectedYearValue() {
        const dateTo = this.controller.cachedFilterOptions.date?.date_to;
        const selectedYear = dateTo ? DateTime.fromISO(dateTo) : DateTime.now();
        return selectedYear.isValid ? selectedYear.startOf("year") : DateTime.now().startOf("year");
    }

    get yearFilterLabel() {
        return this.selectedYearValue.toFormat("yyyy");
    }

    async selectYearPeriod() {
        await this.controller.updateOption("date.filter", this.getDateFilter("year"));
        await this.controller.updateOption("date.period", this.dateFilter.year);
        await this.applyFilters("date.period", 0);
    }

    async selectYear(date) {
        if (!date) {
            return;
        }
        const selectedYear = date.startOf("year");
        const currentYear = DateTime.now().startOf("year");
        const offset = Math.round(selectedYear.diff(currentYear, "years").years);
        this.dateFilter.year = offset;
        await this.controller.updateOption("date.filter", this.getDateFilter("year"));
        await this.controller.updateOption("date.period", offset);
        await this.applyFilters("date.period", 0);
    }
}

AccountReport.registerCustomComponent(TenenetInternalExpenseReportFilters);
