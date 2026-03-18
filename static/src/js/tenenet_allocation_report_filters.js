import { AccountReport } from "@account_reports/components/account_report/account_report";
import { AccountReportFilters } from "@account_reports/components/account_report/filters/filters";

const { DateTime } = luxon;

export class TenenetAllocationReportFilters extends AccountReportFilters {
    static template = "tenenet_projects.TenenetAllocationReportFilters";

    get currentEmployeeName() {
        return this.controller.cachedFilterOptions.selected_employee_name || "Zamestnanec";
    }

    get selectedEmployeeIds() {
        return this.controller.cachedFilterOptions.employee_ids || [];
    }

    get employeeSelectorProps() {
        return {
            resModel: "hr.employee",
            resIds: this.selectedEmployeeIds,
            update: (resIds) => this.selectEmployee(resIds),
            placeholder: "Vyber zamestnanca...",
        };
    }

    get selectedYearValue() {
        const dateTo = this.controller.cachedFilterOptions.date?.date_to;
        const selectedYear = dateTo ? DateTime.fromISO(dateTo) : DateTime.now();
        return selectedYear.isValid ? selectedYear.startOf("year") : DateTime.now().startOf("year");
    }

    get yearFilterLabel() {
        return this.selectedYearValue.toFormat("yyyy");
    }

    async selectEmployee(resIds) {
        const nextEmployeeIds = resIds.length ? [resIds[resIds.length - 1]] : [];
        await this.controller.updateOption("employee_ids", nextEmployeeIds);
        await this.applyFilters("employee_ids", 0);
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

AccountReport.registerCustomComponent(TenenetAllocationReportFilters);
