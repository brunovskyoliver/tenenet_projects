/** @odoo-module **/

import { Component, onMounted, onPatched, onWillStart, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

import { parseAmount, roundAmount } from "./tenenet_month_planner_utils";

export class TenenetBudgetAddAction extends Component {
    static template = "tenenet_projects.TenenetBudgetAddAction";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.actionService = useService("action");
        this.rootRef = useRef("root");
        this.projectId = this.props.action.params?.project_id;
        this.state = useState({
            loading: true,
            saving: false,
            data: null,
            budgetType: "labor",
            amount: 0,
            allocationPercentage: 0,
            amountInput: "0.00",
            percentageInput: "0.00",
            note: "",
        });

        onWillStart(async () => {
            await this.loadData();
        });

        onMounted(() => this.applyModalSizing());
        onPatched(() => this.applyModalSizing());
    }

    get data() {
        return this.state.data;
    }

    get budgetTypeOptions() {
        return this.data?.budget_type_options || [];
    }

    formatAmount(value) {
        return new Intl.NumberFormat(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        }).format(roundAmount(value || 0));
    }

    formatAmountWithCurrency(value) {
        const formatted = this.formatAmount(value);
        if (!this.data?.currency_symbol) {
            return formatted;
        }
        return this.data.currency_position === "before"
            ? `${this.data.currency_symbol} ${formatted}`
            : `${formatted} ${this.data.currency_symbol}`;
    }

    formatAmountInput(value) {
        return roundAmount(value || 0).toFixed(2);
    }

    async loadData() {
        if (!this.projectId) {
            this.state.loading = false;
            return;
        }
        this.state.loading = true;
        try {
            const data = await this.orm.call("tenenet.project", "get_budget_add_action_data", [[this.projectId]]);
            this.state.data = data;
            this.state.budgetType = data.default_budget_type || "labor";
            this.state.amount = 0;
            this.state.allocationPercentage = 0;
            this.state.amountInput = this.formatAmountInput(0);
            this.state.percentageInput = this.formatAmountInput(0);
            this.state.note = "";
        } catch (error) {
            this.notification.add(error.data?.message || _t("Nepodarilo sa načítať údaje rozpočtu."), {
                type: "danger",
            });
            this.state.data = null;
        } finally {
            this.state.loading = false;
        }
    }

    syncPercentageFromAmount() {
        const available = this.data?.available_amount || 0;
        if (available <= 0) {
            this.state.allocationPercentage = 0;
            this.state.percentageInput = this.formatAmountInput(0);
            return;
        }
        this.state.allocationPercentage = roundAmount((this.state.amount / available) * 100);
        this.state.percentageInput = this.formatAmountInput(this.state.allocationPercentage);
    }

    syncAmountFromPercentage() {
        const available = this.data?.available_amount || 0;
        if (available <= 0) {
            this.state.amount = 0;
            this.state.amountInput = this.formatAmountInput(0);
            return;
        }
        this.state.amount = roundAmount(available * (this.state.allocationPercentage / 100));
        this.state.amountInput = this.formatAmountInput(this.state.amount);
    }

    selectBudgetType(value) {
        this.state.budgetType = value;
    }

    onBudgetTypeBadgeClick(ev) {
        this.selectBudgetType(ev.currentTarget.dataset.value);
    }

    onAmountChange(ev) {
        this.state.amountInput = ev.target.value;
        this.state.amount = Math.max(0, parseAmount(ev.target.value));
        this.syncPercentageFromAmount();
        this.state.amountInput = ev.target.value;
    }

    onPercentageChange(ev) {
        this.state.percentageInput = ev.target.value;
        const value = Math.max(0, Math.min(100, parseAmount(ev.target.value)));
        this.state.allocationPercentage = roundAmount(value);
        this.syncAmountFromPercentage();
        this.state.percentageInput = ev.target.value;
    }

    onAmountBlur() {
        this.state.amountInput = this.formatAmountInput(this.state.amount);
    }

    onPercentageBlur() {
        this.state.percentageInput = this.formatAmountInput(this.state.allocationPercentage);
    }

    onNoteChange(ev) {
        this.state.note = ev.target.value;
    }

    async onSubmit() {
        if (this.state.saving || !this.data) {
            return;
        }
        this.state.saving = true;
        try {
            const action = await this.orm.call("tenenet.project", "action_create_budget_line_from_quick_add", [
                [this.projectId],
                this.state.budgetType,
                this.state.amount,
                this.state.allocationPercentage,
                this.state.note,
            ]);
            await this.actionService.doAction(action);
        } catch (error) {
            this.notification.add(error.data?.message || _t("Nepodarilo sa pridať rozpočtovú položku."), {
                type: "danger",
            });
            this.state.saving = false;
            return;
        }
        this.state.saving = false;
    }

    close() {
        if (this.env.dialogData?.close) {
            this.env.dialogData.close();
            return;
        }
        this.actionService.restore();
    }

    applyModalSizing() {
        const root = this.rootRef.el;
        if (!root) {
            return;
        }
        const dialog = root.closest(".modal-dialog");
        if (!dialog) {
            return;
        }
        dialog.classList.add("o_tenenet_budget_add_action_dialog");
        dialog.style.setProperty("--bs-modal-width", "680px", "important");
        dialog.style.setProperty("width", "680px", "important");
        dialog.style.setProperty("max-width", "calc(100vw - 2rem)", "important");
    }
}

registry.category("actions").add("tenenet_budget_add_action", TenenetBudgetAddAction);
