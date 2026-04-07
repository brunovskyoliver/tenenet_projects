import { AccountReport } from "@account_reports/components/account_report/account_report";
import { AccountReportFilters } from "@account_reports/components/account_report/filters/filters";

export class TenenetEmployeeListReportFilters extends AccountReportFilters {
    static template = "tenenet_projects.TenenetEmployeeListReportFilters";

    get selectedJobIds() {
        return this.controller.cachedFilterOptions.job_ids || [];
    }

    get selectedLanguageSkillIds() {
        return this.controller.cachedFilterOptions.language_skill_ids || [];
    }

    get selectedJobLabel() {
        return this._formatSelectionLabel(
            this.controller.cachedFilterOptions.selected_job_names || [],
            "Profesie",
        );
    }

    get selectedLanguageLabel() {
        return this._formatSelectionLabel(
            this.controller.cachedFilterOptions.selected_language_names || [],
            "Jazyky",
        );
    }

    get selectedAvailabilityLabel() {
        const selectedItems = (this.controller.cachedFilterOptions.availability_filter_selection || []).filter(
            (item) => item.selected
        );
        if (!selectedItems.length) {
            return "Vyťaženosť";
        }
        if (selectedItems.length === 1) {
            return selectedItems[0].name;
        }
        return `${selectedItems.length} vybrané`;
    }

    get selectedGroupingLabel() {
        const selectedGrouping = (this.controller.cachedFilterOptions.grouping_mode_selection || []).find(
            (item) => item.selected
        );
        return selectedGrouping?.name || "Bez zoskupenia";
    }

    get jobSelectorProps() {
        return {
            resModel: "hr.job",
            resIds: this.selectedJobIds,
            update: (resIds) => this.updateRecordFilter("job_ids", resIds),
            placeholder: "Vyber profesie...",
        };
    }

    get languageSelectorProps() {
        return {
            resModel: "hr.skill",
            resIds: this.selectedLanguageSkillIds,
            domain: this.controller.cachedFilterOptions.language_skill_domain || [["id", "=", 0]],
            update: (resIds) => this.updateRecordFilter("language_skill_ids", resIds),
            placeholder: "Vyber jazyky...",
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

    async updateRecordFilter(optionKey, resIds) {
        await this.controller.updateOption(optionKey, resIds);
        await this.applyFilters(optionKey, 0);
    }

    async selectGroupingMode(mode) {
        await this.controller.updateOption("grouping_mode", mode);
        await this.applyFilters("grouping_mode", 0);
    }
}

AccountReport.registerCustomComponent(TenenetEmployeeListReportFilters);
