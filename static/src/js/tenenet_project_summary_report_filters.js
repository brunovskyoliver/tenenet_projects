import { AccountReport } from "@account_reports/components/account_report/account_report";
import { AccountReportFilters } from "@account_reports/components/account_report/filters/filters";

const { DateTime } = luxon;

export class TenenetProjectSummaryReportFilters extends AccountReportFilters {
    static template = "tenenet_projects.TenenetProjectSummaryReportFilters";

    get selectedProgramIds() {
        return this.controller.cachedFilterOptions.program_ids || [];
    }

    get selectedDonorIds() {
        return this.controller.cachedFilterOptions.donor_ids || [];
    }

    get selectedYearValue() {
        const dateTo = this.controller.cachedFilterOptions.date?.date_to;
        const selectedYear = dateTo ? DateTime.fromISO(dateTo) : DateTime.now();
        return selectedYear.isValid ? selectedYear.startOf("year") : DateTime.now().startOf("year");
    }

    get yearFilterLabel() {
        return this.selectedYearValue.toFormat("yyyy");
    }

    get selectedProgramLabel() {
        return this._formatSelectionLabel(
            this.controller.cachedFilterOptions.selected_program_names || [],
            "Programy",
        );
    }

    get selectedDonorLabel() {
        return this._formatSelectionLabel(
            this.controller.cachedFilterOptions.selected_donor_names || [],
            "Donori",
        );
    }

    get selectedProjectTypeLabel() {
        const option = (this.controller.cachedFilterOptions.project_type_selection || []).find(
            (item) => item.selected
        );
        return option?.name || "Všetky typy";
    }

    get selectedSemaphoreLabel() {
        const option = (this.controller.cachedFilterOptions.semaphore_selection || []).find(
            (item) => item.selected
        );
        return option?.name || "Všetky";
    }

    get selectedProjectScopeLabel() {
        const option = (this.controller.cachedFilterOptions.project_scope_selection || []).find(
            (item) => item.selected
        );
        return option?.name || "Aktívne v roku";
    }

    get programSelectorProps() {
        return {
            resModel: "tenenet.program",
            resIds: this.selectedProgramIds,
            domain: this.controller.cachedFilterOptions.available_program_domain || [["id", "=", 0]],
            update: (resIds) => this.updateRecordFilter("program_ids", resIds),
            context: { active_test: false },
            placeholder: "Vyber programy...",
        };
    }

    get donorSelectorProps() {
        return {
            resModel: "tenenet.donor",
            resIds: this.selectedDonorIds,
            domain: this.controller.cachedFilterOptions.available_donor_domain || [["id", "=", 0]],
            update: (resIds) => this.updateRecordFilter("donor_ids", resIds),
            context: { active_test: false },
            placeholder: "Vyber donorov...",
        };
    }

    _formatSelectionLabel(names, defaultLabel) {
        if (!names.length) {
            return defaultLabel;
        }
        if (names.length === 1) {
            return names[0];
        }
        return `${names.length} vybrané`;
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

    async updateRecordFilter(optionKey, resIds) {
        await this.controller.updateOption(optionKey, resIds);
        await this.applyFilters(optionKey, 0);
    }

    async selectOption(optionKey, value) {
        await this.controller.updateOption(optionKey, value || false);
        await this.applyFilters(optionKey, 0);
    }
}

AccountReport.registerCustomComponent(TenenetProjectSummaryReportFilters);
