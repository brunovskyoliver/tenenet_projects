import { registry } from "@web/core/registry";
import { ganttView } from "@web_gantt/gantt_view";
import { GanttModel } from "@web_gantt/gantt_model";
import { GanttRenderer } from "@web_gantt/gantt_renderer";
import { GanttRendererControls } from "@web_gantt/gantt_renderer_controls";

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
        const stopDate = DateTime.fromObject({ year, month: 12, day: 31 }).endOf("day");
        return { focusDate, startDate, stopDate, rangeId: "custom" };
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
        const stopDate = DateTime.fromObject({ year, month: 12, day: 31 }).endOf("day");
        this.selectCustomRange(startDate, stopDate);
    }
}

// ---------------------------------------------------------------------------
// Renderer — custom controls
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
