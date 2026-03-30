/** @odoo-module **/

import { registry } from "@web/core/registry";
import { gridView } from "@web_grid/views/grid_view";
import { GridModel } from "@web_grid/views/grid_model";
import { GridRenderer } from "@web_grid/views/grid_renderer";

const HOUR_TYPE_ORDER = {
    pp: 10,
    np: 20,
    travel: 30,
    training: 40,
    ambulance: 50,
    international: 60,
    vacation: 70,
    sick: 80,
    doctor: 90,
    holidays: 100,
    total: 9999,
};

export class TenenetTimesheetMatrixGridModel extends GridModel {
    // Include invisible row fields (sequence, hour_type, scope) in the groupby so the
    // server returns them and we can sort by HOUR_TYPE_ORDER.
    _getGroupByFields(metaData = this.metaData) {
        const { sectionField } = metaData;
        const fields = [this.columnGroupByFieldName, ...this.defaultRowFields.map((r) => r.name)];
        if (sectionField) {
            fields.push(sectionField.name);
        }
        return fields;
    }

    // Store invisible field values in valuePerFieldName so the sort below can use them.
    _generateRowDomainAndValues(readGroupResult, rowFields) {
        const { domain, values } = super._generateRowDomainAndValues(readGroupResult, rowFields);
        for (const f of this.defaultRowFields) {
            if (!(f.name in values) && f.name in readGroupResult) {
                values[f.name] = readGroupResult[f.name];
            }
        }
        return { domain, values };
    }

    async loadData(metaData) {
        await super.loadData(metaData);
        const { data } = metaData;
        data.items.sort((a, b) => {
            if (a.isSection) return -1;
            if (b.isSection) return 1;
            const orderA = HOUR_TYPE_ORDER[a.valuePerFieldName?.hour_type] ?? 9999;
            const orderB = HOUR_TYPE_ORDER[b.valuePerFieldName?.hour_type] ?? 9999;
            return orderA - orderB;
        });
    }
}

export class TenenetTimesheetMatrixGridRenderer extends GridRenderer {
    getCellsClasses(column, row, section, isEven) {
        return {
            ...super.getCellsClasses(column, row, section, isEven),
            o_tenenet_grid_leave_row: row.initialRecordValues.scope === "leave",
            o_tenenet_grid_total_row: row.initialRecordValues.scope === "total",
        };
    }
}

registry.category("views").add("tenenet_timesheet_matrix_grid", {
    ...gridView,
    Model: TenenetTimesheetMatrixGridModel,
    Renderer: TenenetTimesheetMatrixGridRenderer,
});
