import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { HomeMenu } from "@web_enterprise/webclient/home_menu/home_menu";

import { onWillStart, useState } from "@odoo/owl";

patch(HomeMenu.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.tenenetPreviousMonthUtilization = useState({
            data: null,
            loaded: false,
        });

        onWillStart(async () => {
            await this._loadTenenetPreviousMonthUtilization();
        });
    },

    async _loadTenenetPreviousMonthUtilization() {
        try {
            const payload = await this.orm.call(
                "res.users",
                "get_home_menu_previous_month_utilization",
                []
            );
            this.tenenetPreviousMonthUtilization.data = payload || null;
        } catch {
            this.tenenetPreviousMonthUtilization.data = null;
        } finally {
            this.tenenetPreviousMonthUtilization.loaded = true;
        }
    },
});
