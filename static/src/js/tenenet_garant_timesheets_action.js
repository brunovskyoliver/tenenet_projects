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

export class TenenetGarantTimesheetsAction extends Component {
    static template = "tenenet_projects.TenenetGarantTimesheetsAction";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            projects: [],
            selectedProjectId: null,
            year: new Date().getFullYear(),
            matrices: [],
            collapsedMatrixIds: {},
        });

        onWillStart(() => this.loadProjects());
    }

    get months() {
        return MONTHS;
    }

    async loadProjects() {
        this.state.loading = true;
        this.state.projects = await this.orm.call(
            "tenenet.project.timesheet.matrix", "get_garant_projects", []
        );
        this.state.loading = false;
    }

    async selectProject(id) {
        this.state.selectedProjectId = id;
        await this.loadMatrices();
    }

    async loadMatrices() {
        if (!this.state.selectedProjectId) {
            this.state.matrices = [];
            this.state.collapsedMatrixIds = {};
            return;
        }
        this.state.loading = true;
        const matrices = await this.orm.searchRead(
            "tenenet.project.timesheet.matrix",
            [
                ["project_id", "=", this.state.selectedProjectId],
                ["year", "=", this.state.year],
            ],
            ["id", "employee_id", "project_id", "year", "line_ids"],
            { order: "employee_id" }
        );

        if (!matrices.length) {
            this.state.matrices = [];
            this.state.collapsedMatrixIds = {};
            this.state.loading = false;
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
        this.state.collapsedMatrixIds = {};
        this.state.loading = false;
    }

    async changeYear(delta) {
        this.state.year += delta;
        if (this.state.selectedProjectId) {
            await this.loadMatrices();
        }
    }

    isCellEditable(line, monthField) {
        return !line.is_total && !line.leave_sync_managed && line[`${monthField}_editable`];
    }

    get areAllMatricesCollapsed() {
        return (
            this.state.matrices.length > 0
            && this.state.matrices.every((matrix) => this.isMatrixCollapsed(matrix.id))
        );
    }

    isMatrixCollapsed(matrixId) {
        return !!this.state.collapsedMatrixIds[matrixId];
    }

    toggleAllMatrices() {
        const nextState = !this.areAllMatricesCollapsed;
        const collapsedMatrixIds = {};
        for (const matrix of this.state.matrices) {
            collapsedMatrixIds[matrix.id] = nextState;
        }
        this.state.collapsedMatrixIds = collapsedMatrixIds;
    }

    toggleMatrix(matrixId) {
        this.state.collapsedMatrixIds = {
            ...this.state.collapsedMatrixIds,
            [matrixId]: !this.isMatrixCollapsed(matrixId),
        };
    }

    getVisibleLines(matrix) {
        if (!this.isMatrixCollapsed(matrix.id)) {
            return matrix.lines;
        }
        return matrix.lines.filter((line) => line.is_total || line.hour_type === "total");
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

registry.category("actions").add("tenenet_garant_timesheets", TenenetGarantTimesheetsAction);
