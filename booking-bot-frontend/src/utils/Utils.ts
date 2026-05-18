export const HSE_COLORS = {
    primary: "#0F2D69",
    accent: "#234B9B",
    gray: "#929292",
    border: "#C6C6C6",
    bgLight: "#E6E6E6",
    white: "#FFFFFF",
} as const;

// Стандартные пары ВШЭ: начало → конец
export const HSE_PAIRS: { label: string; start: string; end: string }[] = [
    { label: "1 пара  08:00–09:20", start: "08:00", end: "09:20" },
    { label: "2 пара  09:30–10:50", start: "09:30", end: "10:50" },
    { label: "3 пара  11:00–12:20", start: "11:00", end: "12:20" },
    { label: "4 пара  12:30–13:50", start: "12:30", end: "13:50" },
    { label: "5 пара  14:00–15:20", start: "14:00", end: "15:20" },
    { label: "6 пара  15:30–16:50", start: "15:30", end: "16:50" },
    { label: "7 пара  17:00–18:20", start: "17:00", end: "18:20" },
    { label: "8 пара  18:30–19:50", start: "18:30", end: "19:50" },
];
