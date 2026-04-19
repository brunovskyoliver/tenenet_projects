import { AccountReport } from "@account_reports/components/account_report/account_report";
import { AccountReportFilters } from "@account_reports/components/account_report/filters/filters";

const { DateTime } = luxon;

export class TenenetEmployeeListReportFilters extends AccountReportFilters {
    static template = "tenenet_projects.TenenetEmployeeListReportFilters";

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

    get selectedJobIds() {
        return this.controller.cachedFilterOptions.job_ids || [];
    }

    get selectedMainSiteIds() {
        return this.controller.cachedFilterOptions.main_site_ids || [];
    }

    get selectedProjectIds() {
        return this.controller.cachedFilterOptions.project_ids || [];
    }

    get selectedProgramIds() {
        return this.controller.cachedFilterOptions.program_ids || [];
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

    get selectedMainSiteLabel() {
        return this._formatSelectionLabel(
            this.controller.cachedFilterOptions.selected_main_site_names || [],
            "Pracoviská",
        );
    }

    get selectedLanguageLabel() {
        return this._formatSelectionLabel(
            this.controller.cachedFilterOptions.selected_language_names || [],
            "Jazyky",
        );
    }

    get selectedProjectLabel() {
        return this._formatSelectionLabel(
            this.controller.cachedFilterOptions.selected_project_names || [],
            "Projekty",
        );
    }

    get selectedProgramLabel() {
        return this._formatSelectionLabel(
            this.controller.cachedFilterOptions.selected_program_names || [],
            "Programy",
        );
    }

    get selectedAvailabilityLabel() {
        const availabilityMode = this.controller.cachedFilterOptions.availability_mode;
        const minimumFreeHours = this.minimumFreeHours;
        if (availabilityMode === "free") {
            return `Voľný (${minimumFreeHours} h+)`;
        }
        if (availabilityMode === "full") {
            return "Plne alokovaný";
        }
        return "Dostupnosť";
    }

    get minimumFreeHours() {
        const value = this.controller.cachedFilterOptions.minimum_free_hours;
        return Number.isFinite(Number(value)) ? Number(value) : 0;
    }

    get isFreeAvailabilityModeSelected() {
        return this.controller.cachedFilterOptions.availability_mode === "free";
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

    get mainSiteSelectorProps() {
        return {
            resModel: "tenenet.project.site",
            resIds: this.selectedMainSiteIds,
            domain: [["site_type", "in", ["prevadzka", "centrum"]]],
            update: (resIds) => this.updateRecordFilter("main_site_ids", resIds),
            context: { active_test: false },
            placeholder: "Vyber hlavné pracoviská...",
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

    get projectSelectorProps() {
        return {
            resModel: "tenenet.project",
            resIds: this.selectedProjectIds,
            update: (resIds) => this.updateRecordFilter("project_ids", resIds),
            context: { active_test: false },
            placeholder: "Vyber projekty...",
        };
    }

    get programSelectorProps() {
        return {
            resModel: "tenenet.program",
            resIds: this.selectedProgramIds,
            update: (resIds) => this.updateRecordFilter("program_ids", resIds),
            context: { active_test: false },
            placeholder: "Vyber programy...",
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

    async updateRecordFilter(optionKey, resIds) {
        await this.controller.updateOption(optionKey, resIds);
        await this.applyFilters(optionKey, 0);
    }

    async selectAvailabilityMode(mode) {
        const nextMode = this.controller.cachedFilterOptions.availability_mode === mode ? false : mode;
        await this.controller.updateOption("availability_mode", nextMode);
        if (nextMode !== "free") {
            await this.controller.updateOption("minimum_free_hours", 0);
        }
        await this.applyFilters("availability_mode", 0);
    }

    async updateMinimumFreeHours(ev) {
        const parsedValue = Number.parseFloat(ev.target.value);
        const minimumFreeHours = Number.isFinite(parsedValue) && parsedValue > 0 ? parsedValue : 0;
        await this.controller.updateOption("minimum_free_hours", minimumFreeHours);
        await this.applyFilters("minimum_free_hours", 0);
    }

    async selectGroupingMode(mode) {
        await this.controller.updateOption("grouping_mode", mode);
        await this.applyFilters("grouping_mode", 0);
    }
}

AccountReport.registerCustomComponent(TenenetEmployeeListReportFilters);
