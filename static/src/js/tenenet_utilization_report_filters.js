import { AccountReport } from "@account_reports/components/account_report/account_report";
import { AccountReportFilters } from "@account_reports/components/account_report/filters/filters";

const { DateTime } = luxon;

export class TenenetUtilizationReportFilters extends AccountReportFilters {
    static template = "tenenet_projects.TenenetUtilizationReportFilters";

    get selectedMonthValue() {
        const dateTo = this.controller.cachedFilterOptions.date?.date_to;
        const selectedMonth = dateTo ? DateTime.fromISO(dateTo) : DateTime.now();
        return selectedMonth.isValid ? selectedMonth.startOf("month") : DateTime.now().startOf("month");
    }

    get monthFilterLabel() {
        return this.selectedMonthValue.toFormat("MMM yyyy");
    }

    displayPeriod(periodType) {
        if (periodType === "month") {
            return this.monthFilterLabel;
        }
        return super.displayPeriod(periodType);
    }

    selectMonthPeriod() {
        this.controller.updateOption("date.filter", this.getDateFilter("month"));
        this.controller.updateOption("date.period", this.dateFilter.month);
        this.applyFilters("date.period");
    }

    selectMonth(date) {
        if (!date) {
            return;
        }

        const selectedMonth = date.startOf("month");
        const currentMonth = DateTime.now().startOf("month");
        const offset = Math.round(selectedMonth.diff(currentMonth, "months").months);

        this.dateFilter.month = offset;
        this.controller.updateOption("date.filter", this.getDateFilter("month"));
        this.controller.updateOption("date.period", offset);
        this.applyFilters("date.period");
    }
}

AccountReport.registerCustomComponent(TenenetUtilizationReportFilters);
