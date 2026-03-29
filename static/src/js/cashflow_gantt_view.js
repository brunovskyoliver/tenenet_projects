import { registry } from "@web/core/registry";
import { ganttView } from "@web_gantt/gantt_view";
import { GanttModel } from "@web_gantt/gantt_model";
import { GanttRenderer } from "@web_gantt/gantt_renderer";
import { GanttRendererControls } from "@web_gantt/gantt_renderer_controls";
import { Domain } from "@web/core/domain";

const { DateTime } = luxon;

// ---------------------------------------------------------------------------
// Model
// ---------------------------------------------------------------------------
export class CashflowGanttModel extends GanttModel {
    _getInitialRangeParams(metaData, searchParams) {
        const year =
            searchParams.context?.cashflow_initial_year || DateTime.now().year;
        const focusDate = DateTime.fromObject({ year, month: 1, day: 1 }).startOf("day");
        const startDate = focusDate;
        // stopDate = Dec 31 of the current year.  The gantt always adds one month
        // of padding beyond the stopDate month, so January of year+1 becomes the
        // natural "Spolu" column — no extra column appears.
        const stopDate = DateTime.fromObject({ year, month: 12, day: 31 }).endOf("day");
        return { focusDate, startDate, stopDate, rangeId: "custom" };
    }

    /**
     * Always exclude is_total summary records from the gantt.
     * Without this, a 2025 receipt's total record (date_start Jan 1, 2026)
     * would appear as a pill in the 2026 January column.
     */
    _getDomain(metaData) {
        const baseList = super._getDomain(metaData);
        return Domain.and([baseList, [["is_total", "=", false]]]).toList();
    }

    async _fetchData(metaData) {
        await super._fetchData(metaData);
        // Keep the single group row permanently collapsed so all pills are on one row
        this._collapseAllRows();
    }

    _collapseAllRows() {
        const collapse = (rows) => {
            for (const row of rows) {
                this.closedRows.add(row.id);
                if (row.rows) {
                    collapse(row.rows);
                }
            }
        };
        if (this.data && this.data.rows) {
            collapse(this.data.rows);
        }
    }

    get rowsAreExpanded() {
        return false;
    }

    expandRows() {}

    /**
     * Sum of all fetched monthly record amounts — shown in the Spolu column header.
     */
    get yearTotalFormatted() {
        let total = 0;
        const sumRows = (rows) => {
            for (const row of rows) {
                for (const pill of (row.pills || [])) {
                    total += pill.record?.amount || 0;
                }
                if (row.rows?.length) sumRows(row.rows);
            }
        };
        if (this.data?.rows) sumRows(this.data.rows);
        const formatted = Math.round(total)
            .toLocaleString("en-US")
            .replace(/,/g, "\u00a0");
        return `${formatted}\u00a0€`;
    }
}

// ---------------------------------------------------------------------------
// Controls — year navigation (prev/next calendar year)
// ---------------------------------------------------------------------------
export class CashflowGanttRendererControls extends GanttRendererControls {
    static rangeMenuTemplate =
        "tenenet_projects.CashflowGanttRendererControls.RangeMenu";

    selectRange(direction) {
        const sign = direction === "next" ? 1 : -1;
        const currentYear = this.state.startDate.year;
        this._setCalendarYear(currentYear + sign);
    }

    onTodayClicked() {
        this._setCalendarYear(DateTime.now().year);
    }

    _setCalendarYear(year) {
        const startDate = DateTime.fromObject({ year, month: 1, day: 1 }).startOf("day");
        // Dec 31 → gantt padding produces Jan of year+1 as the Spolu column
        const stopDate = DateTime.fromObject({ year, month: 12, day: 31 }).endOf("day");
        this.selectCustomRange(startDate, stopDate);
    }
}

// ---------------------------------------------------------------------------
// Renderer — custom controls + custom header (last column = "Spolu")
// ---------------------------------------------------------------------------
export class CashflowGanttRenderer extends GanttRenderer {
    static headerTemplate = "tenenet_projects.CashflowGanttRenderer.Header";
}
CashflowGanttRenderer.components = {
    ...GanttRenderer.components,
    GanttRendererControls: CashflowGanttRendererControls,
};

// ---------------------------------------------------------------------------
// View registration
// ---------------------------------------------------------------------------
export const cashflowGanttView = {
    ...ganttView,
    Model: CashflowGanttModel,
    Renderer: CashflowGanttRenderer,
};

registry.category("views").add("cashflow_gantt", cashflowGanttView);
