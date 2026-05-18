import React from "react";
import { HSE_COLORS } from "../utils/Utils";

export const Logo: React.FC = () => (
    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        {/* Шашка ВШЭ */}
        <svg width="40" height="40" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect width="40" height="40" rx="4" fill={HSE_COLORS.primary} />
            <text x="20" y="27" textAnchor="middle" fill="white" fontSize="18" fontWeight="bold" fontFamily="Arial">
                ВШЭ
            </text>
        </svg>
        <div style={{ lineHeight: 1.2 }}>
            <div style={{ color: HSE_COLORS.primary, fontWeight: 700, fontSize: 14, letterSpacing: 0.5 }}>
                НИУ ВШЭ — Нижний Новгород
            </div>
            <div style={{ color: HSE_COLORS.gray, fontSize: 11 }}>
                Бронирование аудиторий
            </div>
        </div>
    </div>
);
