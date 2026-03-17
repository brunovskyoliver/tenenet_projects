/** @odoo-module **/

function syncTimesheetMatrixHosts(root = document) {
    const formViews = root.querySelectorAll(".o_form_view");
    for (const formView of formViews) {
        const hasMatrix = !!formView.querySelector(".o_tenenet_timesheet_matrix_view");
        formView.classList.toggle("o_tenenet_timesheet_matrix_host", hasMatrix);
    }
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => syncTimesheetMatrixHosts());
} else {
    syncTimesheetMatrixHosts();
}

const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
        if (mutation.type === "childList") {
            syncTimesheetMatrixHosts(document);
            break;
        }
    }
});

observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
});
