import React, { useEffect, useState } from "react";
import { Alert, Button, Card, Empty, Space, Spin, Typography } from "antd";
import { DeleteOutlined } from "@ant-design/icons";
import { BackButton, useShowPopup } from "@vkruglikov/react-telegram-web-app";
import { useNavigate } from "react-router-dom";
import styled from "styled-components";

import { Booking, cancelBooking, formatDate, formatTime, getMyBookings } from "../utils/BookingApi";
import { HSE_COLORS } from "../utils/Utils";
import { isTelegramWindow, tg } from "../utils/TelegramWebApp";

const { Title, Text } = Typography;

const PageTitle = styled(Title)`
    && {
        color: ${HSE_COLORS.primary} !important;
        text-align: center;
        margin-bottom: 16px !important;
    }
`;

const BookingCard = styled(Card)`
    margin-bottom: 10px;
    border-radius: 8px !important;
    border-color: ${HSE_COLORS.border} !important;
`;

const StatusBadge = styled.span<{ $statusId: number }>`
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 600;
    background: ${({ $statusId }) =>
        $statusId === 2 ? "#E6F4EA" : $statusId === 1 ? "#FFF3CD" : "#F8D7DA"};
    color: ${({ $statusId }) =>
        $statusId === 2 ? "#2D6A2D" : $statusId === 1 ? "#7D5A00" : "#6B1A1A"};
`;

export default function MyBookingsPage() {
    const navigate = useNavigate();
    const showPopup = useShowPopup();

    const [bookings, setBookings] = useState<Booking[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const load = async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await getMyBookings();
            setBookings(data);
        } catch {
            setError("Не удалось загрузить бронирования. Попробуйте позже.");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (isTelegramWindow) tg.expand();
        load();
    }, []);

    const handleCancel = async (booking: Booking) => {
        const confirmed = await showPopup({
            title: "Отменить бронирование?",
            message: `Аудитория: ${booking.room_id}\n${formatDate(booking.starts_at)} ${formatTime(booking.starts_at)}–${formatTime(booking.ends_at)}`,
            buttons: [
                { id: "ok", type: "destructive", text: "Отменить бронь" },
                { id: "cancel", type: "cancel", text: "Назад" },
            ],
        });

        if (confirmed === "ok") {
            try {
                await cancelBooking(booking.booking_id);
                await load();
                tg.HapticFeedback?.notificationOccurred("success");
            } catch {
                setError("Не удалось отменить бронирование.");
            }
        }
    };

    return (
        <div>
            <BackButton onClick={() => navigate("/")} />
            <PageTitle level={4}>Мои бронирования</PageTitle>

            {error && (
                <Alert type="error" message={error} closable onClose={() => setError(null)} style={{ marginBottom: 12 }} />
            )}

            {loading && (
                <div style={{ textAlign: "center", padding: 32 }}>
                    <Spin size="large" />
                </div>
            )}

            {!loading && bookings.length === 0 && (
                <Empty
                    description="У вас нет активных бронирований"
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                />
            )}

            {!loading &&
                bookings.map((b) => (
                    <BookingCard
                        key={b.booking_id}
                        size="small"
                        extra={
                            b.status_id <= 2 && (
                                <Button
                                    size="small"
                                    danger
                                    icon={<DeleteOutlined />}
                                    onClick={() => handleCancel(b)}
                                />
                            )
                        }
                    >
                        <Space direction="vertical" size={4} style={{ width: "100%" }}>
                            <Text strong style={{ color: HSE_COLORS.primary, fontSize: 15 }}>
                                Ауд. {b.room_id}
                            </Text>
                            <Text style={{ color: HSE_COLORS.gray, fontSize: 13 }}>
                                {formatDate(b.starts_at)} · {formatTime(b.starts_at)}–{formatTime(b.ends_at)}
                            </Text>
                            {b.purpose && (
                                <Text style={{ fontSize: 12, color: HSE_COLORS.gray }}>{b.purpose}</Text>
                            )}
                            <StatusBadge $statusId={b.status_id}>{b.status_label}</StatusBadge>
                        </Space>
                    </BookingCard>
                ))}
        </div>
    );
}
