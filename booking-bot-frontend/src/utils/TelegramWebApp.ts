// @ts-ignore
export const tg = window.Telegram?.WebApp;

export const isTelegramWindow: boolean = Boolean(tg && tg.initData);

export const lang: "ru" = "ru";

export function getTelegramInitData(): string {
    return tg?.initData || "";
}

export function getTelegramUser() {
    return tg?.initDataUnsafe?.user ?? null;
}
