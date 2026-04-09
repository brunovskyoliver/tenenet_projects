/** @odoo-module **/

export const MONTHS = [
    { number: 1, label: "Jan" },
    { number: 2, label: "Feb" },
    { number: 3, label: "Mar" },
    { number: 4, label: "Apr" },
    { number: 5, label: "Máj" },
    { number: 6, label: "Jún" },
    { number: 7, label: "Júl" },
    { number: 8, label: "Aug" },
    { number: 9, label: "Sep" },
    { number: 10, label: "Okt" },
    { number: 11, label: "Nov" },
    { number: 12, label: "Dec" },
];

export function roundAmount(value) {
    return Math.round((Number(value || 0) + Number.EPSILON) * 100) / 100;
}

export function parseAmount(rawValue) {
    const normalized = String(rawValue ?? "")
        .replace(/\s+/g, "")
        .replace(",", ".");
    const value = parseFloat(normalized);
    return Number.isFinite(value) ? roundAmount(value) : 0;
}

export function getMonthLabel(month) {
    return MONTHS.find((item) => item.number === month)?.label || String(month);
}

export function normalizeRange(startMonth, endMonth) {
    return {
        startMonth: Math.min(startMonth, endMonth),
        endMonth: Math.max(startMonth, endMonth),
    };
}

export function sumAmounts(values) {
    return roundAmount(values.reduce((sum, value) => sum + value, 0));
}

export function distributeAcrossEntries(entries, totalAmount) {
    const unlockedEntries = entries.filter((entry) => !entry.manual);
    if (!unlockedEntries.length) {
        return;
    }

    const manualTotal = sumAmounts(
        entries.filter((entry) => entry.manual).map((entry) => entry.amount)
    );
    const amountForUnlocked = Math.max(0, roundAmount(totalAmount - manualTotal));
    const share = roundAmount(amountForUnlocked / unlockedEntries.length);
    let assigned = 0;

    unlockedEntries.forEach((entry, index) => {
        if (index === unlockedEntries.length - 1) {
            entry.amount = roundAmount(amountForUnlocked - assigned);
        } else {
            entry.amount = share;
            assigned = roundAmount(assigned + share);
        }
    });
}

export function buildEntriesFromMonthList(months, currentMonthAmounts, totalAmount) {
    const entries = months.map((month) => ({
        month,
        amount: roundAmount(currentMonthAmounts[String(month)] || 0),
        manual: false,
    }));
    const currentTotal = sumAmounts(entries.map((entry) => entry.amount));
    if ((Math.abs(currentTotal) < 0.00001 && totalAmount > 0) || Math.abs(currentTotal - totalAmount) > 0.00001) {
        distributeAcrossEntries(entries, totalAmount);
    }
    return entries;
}

export function buildEntriesFromCurrentAmounts(startMonth, endMonth, currentMonthAmounts, totalAmount) {
    const months = [];
    for (let month = startMonth; month <= endMonth; month++) {
        months.push(month);
    }
    return buildEntriesFromMonthList(months, currentMonthAmounts, totalAmount);
}

export function buildFreshEntries(startMonth, endMonth, totalAmount) {
    const months = [];
    for (let month = startMonth; month <= endMonth; month++) {
        months.push(month);
    }
    return buildEntriesFromMonthList(months, {}, totalAmount);
}
