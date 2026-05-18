import axios, { AxiosResponse } from "axios";
import { getTelegramInitData } from "./TelegramWebApp";

// Production: один origin с FastAPI. Dev: CRA :3000, API :8000 (или переопределите REACT_APP_API_URL).
const RAW =
    process.env.REACT_APP_API_URL ||
    (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8000" : "");
const BASE_URL = RAW.replace(/\/$/, "");

function authHeaders(): Record<string, string> {
    const initData = getTelegramInitData();
    if (initData) {
        return { "X-Telegram-Init-Data": initData };
    }
    return {};
}

function api<T>(method: "get" | "post" | "delete", path: string, data?: unknown): Promise<AxiosResponse<T>> {
    return axios({ method, url: `${BASE_URL}${path}`, data, headers: authHeaders() });
}

// ---- Типы ----

export interface Building {
    id: number;
    name: string;
}

export interface Room {
    id: number;
    name: string;
    capacity: number;
    building_id: number;
    building_name: string;
}

export interface Booking {
    booking_id: number;
    room_id: number;
    starts_at: string;
    ends_at: string;
    purpose: string;
    status_id: number;
    status_label: string;
}

export interface CreateBookingPayload {
    room_id: number;
    starts_at: string;
    ends_at: string;
    purpose?: string;
}

// ---- API функции ----

export async function getBuildings(): Promise<Building[]> {
    const resp = await api<{ buildings: Building[] }>("get", "/api/buildings");
    return resp.data.buildings;
}

export async function getAvailableRooms(
    startsAt: string,
    endsAt: string,
    buildingId?: number,
): Promise<Room[]> {
    const params = new URLSearchParams({
        starts_at: startsAt,
        ends_at: endsAt,
    });
    if (buildingId !== undefined) {
        params.set("building_id", String(buildingId));
    }
    const resp = await api<{ rooms: Room[] }>("get", `/api/rooms/available?${params}`);
    return resp.data.rooms;
}

export async function createBooking(payload: CreateBookingPayload): Promise<Booking> {
    const resp = await api<Booking>("post", "/api/bookings", payload);
    return resp.data;
}

export async function getMyBookings(): Promise<Booking[]> {
    const resp = await api<{ bookings: Booking[] }>("get", "/api/bookings/my");
    return resp.data.bookings;
}

export async function cancelBooking(bookingId: number): Promise<Booking> {
    const resp = await api<Booking>("delete", `/api/bookings/${bookingId}`);
    return resp.data;
}

// ---- Вспомогательные ----

export function formatDateTime(iso: string): string {
    const d = new Date(iso);
    return d.toLocaleString("ru-RU", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    });
}

export function formatTime(iso: string): string {
    const d = new Date(iso);
    return d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

export function formatDate(iso: string): string {
    const d = new Date(iso);
    return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" });
}

// Следующие 7 дней для выбора даты
export function getNextDays(count = 7): { label: string; value: string }[] {
    const result: { label: string; value: string }[] = [];
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    for (let i = 0; i < count; i++) {
        const d = new Date(today);
        d.setDate(d.getDate() + i);
        result.push({
            label: d.toLocaleDateString("ru-RU", { weekday: "short", day: "numeric", month: "long" }),
            value: d.toISOString().substring(0, 10),
        });
    }
    return result;
}

// Построить ISO datetime из даты + HH:MM строки
export function buildIso(date: string, time: string): string {
    return `${date}T${time}:00+03:00`;
}
