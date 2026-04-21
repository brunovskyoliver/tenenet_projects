import { useState, onRendered } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { BooleanToggleField, booleanToggleField } from "@web/views/fields/boolean_toggle/boolean_toggle_field";


export class TenenetSubtaskDoneCheckMark extends BooleanToggleField {
    static template = "tenenet_projects.TenenetSubtaskDoneCheckMark";

    setup() {
        super.setup();
        this.reached = useState({
            isReached: false,
        });
        onRendered(() => {
            this.reached.isReached = this.props.record.data[this.props.name];
        });
    }

    async onChange() {
        const { record, name } = this.props;
        const value = !record.data[name];
        const recordUpdate = record.update.bind(record);
        if (["kanban", "list"].includes(this.env.config.viewType)) {
            await recordUpdate({ [name]: value }, { save: true });
        } else {
            await recordUpdate({ [name]: value });
        }
    }
}

export const tenenetSubtaskDoneCheckMark = {
    ...booleanToggleField,
    component: TenenetSubtaskDoneCheckMark,
};

registry.category("fields").add("tenenet_subtask_done_checkmark", tenenetSubtaskDoneCheckMark);
