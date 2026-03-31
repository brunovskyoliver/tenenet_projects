import { AccountReport } from "@account_reports/components/account_report/account_report";
import { AccountReportFilters } from "@account_reports/components/account_report/filters/filters";

const { DateTime } = luxon;

export class TenenetPLReportFilters extends AccountReportFilters {
    static template = "tenenet_projects.TenenetPLReportFilters";

    get currentProgramName() {
        return this.controller.cachedFilterOptions.selected_program_name || "Program";
    }

    get selectedProgramIds() {
        return this.controller.cachedFilterOptions.program_ids || [];
    }

    get programSelectorProps() {
        return {
            resModel: "tenenet.program",
            resIds: this.selectedProgramIds,
            update: (resIds) => this.selectProgram(resIds),
            context: { active_test: false },
            placeholder: "Vyber program...",
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

    async selectProgram(resIds) {
        const nextProgramIds = resIds.length ? [resIds[resIds.length - 1]] : [];
        await this.controller.updateOption("program_ids", nextProgramIds);
        await this.applyFilters("program_ids", 0);
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

AccountReport.registerCustomComponent(TenenetPLReportFilters);
