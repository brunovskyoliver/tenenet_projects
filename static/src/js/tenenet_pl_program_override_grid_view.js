/** @odoo-module **/

import { registry } from "@web/core/registry";
import { gridView } from "@web_grid/views/grid_view";
import { GridModel } from "@web_grid/views/grid_model";

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

registry.category("views").add("tenenet_pl_program_override_grid", {
    ...gridView,
    Model: TenenetPLProgramOverrideGridModel,
});
