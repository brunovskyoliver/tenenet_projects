/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const MONTHS = [
    { field: "month_01", label: "Jan" },
    { field: "month_02", label: "Feb" },
    { field: "month_03", label: "Mar" },
    { field: "month_04", label: "Apr" },
    { field: "month_05", label: "Máj" },
    { field: "month_06", label: "Jún" },
    { field: "month_07", label: "Júl" },
    { field: "month_08", label: "Aug" },
    { field: "month_09", label: "Sep" },
    { field: "month_10", label: "Okt" },
    { field: "month_11", label: "Nov" },
    { field: "month_12", label: "Dec" },
];

const LINE_FIELDS = [
    "id", "matrix_id", "name", "hour_type", "is_total", "leave_sync_managed", "sequence",
    ...MONTHS.map((m) => m.field),
    ...MONTHS.map((m) => `${m.field}_editable`),
];

export class TenenetMyTimesheetsAction extends Component {
    static template = "tenenet_projects.TenenetMyTimesheetsAction";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.employeeId = null;
        this.state = useState({
            loading: true,
            year: new Date().getFullYear(),
            matrices: [],
        });

        onWillStart(() => this.loadData());
    }

    get months() {
        return MONTHS;
    }

    async loadData() {
        this.state.loading = true;
        // sync_my_matrices returns the employee ID (or false) so we can filter
        // by employee_id directly rather than traversing employee_id.user_id.
        this.employeeId = await this.orm.call(
            "tenenet.project.timesheet.matrix", "sync_my_matrices", []
        );
        await this.fetchMatrices();
        this.state.loading = false;
    }

    async fetchMatrices() {
        if (!this.employeeId) {
            this.state.matrices = [];
            return;
        }
        const matrices = await this.orm.searchRead(
            "tenenet.project.timesheet.matrix",
            [
                ["employee_id", "=", this.employeeId],
                ["year", "=", this.state.year],
            ],
            ["id", "project_id", "year", "line_ids"],
            { order: "project_id" }
        );

        if (!matrices.length) {
            this.state.matrices = [];
            return;
        }

        const allLineIds = matrices.flatMap((m) => m.line_ids);
        const lines = await this.orm.read(
            "tenenet.project.timesheet.matrix.line",
            allLineIds,
            LINE_FIELDS
        );

        const linesByMatrix = {};
        for (const line of lines) {
            const mid = Array.isArray(line.matrix_id) ? line.matrix_id[0] : line.matrix_id;
            if (!linesByMatrix[mid]) linesByMatrix[mid] = [];
            linesByMatrix[mid].push(line);
        }

        this.state.matrices = matrices.map((m) => ({
            ...m,
            _key: 0,
            lines: (linesByMatrix[m.id] || []).sort((a, b) => a.sequence - b.sequence),
        }));
    }

    async changeYear(delta) {
        this.state.year += delta;
        this.state.loading = true;
        await this.fetchMatrices();
        this.state.loading = false;
    }

    isCellEditable(line, monthField) {
        return !line.is_total && !line.leave_sync_managed && line[`${monthField}_editable`];
    }

    async onCellChange(matrixId, lineId, monthField, event) {
        const raw = event.target.value;
        const value = parseFloat(String(raw).replace(",", ".")) || 0.0;
        try {
            await this.orm.write("tenenet.project.timesheet.matrix.line", [lineId], {
                [monthField]: value,
            });
        } catch (e) {
            this.notification.add(e.data?.message || "Chyba pri ukladaní", { type: "danger" });
        }
        await this.reloadMatrix(matrixId);
    }

    async reloadMatrix(matrixId) {
        const idx = this.state.matrices.findIndex((m) => m.id === matrixId);
        if (idx === -1) return;
        const matrix = this.state.matrices[idx];
        const lines = await this.orm.read(
            "tenenet.project.timesheet.matrix.line",
            matrix.line_ids,
            LINE_FIELDS
        );
        // Increment _key to force OWL to remount the matrix block so inputs
        // reflect the freshly loaded values rather than stale DOM state.
        this.state.matrices[idx] = {
            ...matrix,
            _key: (matrix._key || 0) + 1,
            lines: lines.sort((a, b) => a.sequence - b.sequence),
        };
    }

    formatValue(value) {
        return (value || 0).toFixed(2);
    }
}

registry.category("actions").add("tenenet_my_timesheets", TenenetMyTimesheetsAction);
