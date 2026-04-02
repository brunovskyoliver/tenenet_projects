/** @odoo-module **/

import { registry } from "@web/core/registry";
import { gridView } from "@web_grid/views/grid_view";
import { GridModel } from "@web_grid/views/grid_model";
import { GridRenderer } from "@web_grid/views/grid_renderer";
import { onMounted } from "@odoo/owl";

export class TenenetPLProgramOverrideGridModel extends GridModel {
    // Include invisible row fields like sequence in the groupby so the server returns
    // them and the grid can sort using report order instead of label order.
    _getGroupByFields(metaData = this.metaData) {
        const { sectionField } = metaData;
        const fields = [this.columnGroupByFieldName, ...this.defaultRowFields.map((rowField) => rowField.name)];
        if (sectionField) {
            fields.push(sectionField.name);
        }
        return fields;
    }

    // Copy invisible row field values into valuePerFieldName for sorting.
    _generateRowDomainAndValues(readGroupResult, rowFields) {
        const { domain, values } = super._generateRowDomainAndValues(readGroupResult, rowFields);
        for (const field of this.defaultRowFields) {
            if (!(field.name in values) && field.name in readGroupResult) {
                values[field.name] = readGroupResult[field.name];
            }
        }
        return { domain, values };
    }

    async loadData(metaData) {
        await super.loadData(metaData);
        metaData.data.items.sort((a, b) => {
            if (a.isSection) {
                return -1;
            }
            if (b.isSection) {
                return 1;
            }
            const sequenceA = a.valuePerFieldName?.sequence ?? 9999;
            const sequenceB = b.valuePerFieldName?.sequence ?? 9999;
            if (sequenceA !== sequenceB) {
                return sequenceA - sequenceB;
            }
            const labelA = a.valuePerFieldName?.row_label || "";
            const labelB = b.valuePerFieldName?.row_label || "";
            return String(labelA).localeCompare(String(labelB));
        });
    }
}

export class TenenetPLProgramOverrideGridRenderer extends GridRenderer {
    setup() {
        super.setup();
        onMounted(() => {
            this.rendererRef.el?.classList.add(
                "o_renderer",
                "o_tenenet_pl_program_override_renderer"
            );
        });
    }

    get gridTemplateColumns() {
        return `auto repeat(${this.props.columns.length}, minmax(8ch, 1fr)) minmax(10ch, 12em)`;
    }

    _isCostStartRow(row) {
        const rowKey = row.initialRecordValues?.row_key || "";
        const sequence = row.initialRecordValues?.sequence;
        return (
            sequence === 400 ||
            (rowKey.startsWith("labor_project:") && sequence === 401)
        );
    }

    getCellsClasses(column, row, section, isEven) {
        return {
            ...super.getCellsClasses(column, row, section, isEven),
            o_tenenet_pl_grid_cost_start_cell: this._isCostStartRow(row),
        };
    }

    getTotalCellsTextClasses(row, grandTotal) {
        return {
            ...super.getTotalCellsTextClasses(row, grandTotal),
            o_tenenet_pl_grid_cost_start_total: this._isCostStartRow(row),
        };
    }
}

registry.category("views").add("tenenet_pl_program_override_grid", {
    ...gridView,
    Model: TenenetPLProgramOverrideGridModel,
    Renderer: TenenetPLProgramOverrideGridRenderer,
});
