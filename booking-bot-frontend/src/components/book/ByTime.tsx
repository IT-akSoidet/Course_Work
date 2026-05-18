import React, { useCallback, useEffect, useState } from "react";
import { Alert, Button, Card, Select, Space, Spin, Typography } from "antd";
import { BackButton, MainButton } from "@vkruglikov/react-telegram-web-app";
import { useNavigate } from "react-router-dom";
import styled from "styled-components";

import {
    Building,
    Room,
    buildIso,
    cancelBooking as apiCancelBooking,
    createBooking,
    getAvailableRooms,
    getBuildings,
    getNextDays,
} from "../../utils/BookingApi";
import { HSE_COLORS, HSE_PAIRS } from "../../utils/Utils";
import { isTelegramWindow, tg } from "../../utils/TelegramWebApp";

const { Title, Text } = Typography;

const SectionTitle = styled(Title)`
    && {
        font-size: 14px !important;
        margin-bottom: 6px !important;
        margin-top: 16px !important;
        color: ${HSE_COLORS.primary} !important;
    }
`;

const RoomCard = styled(Card)<{ $selected: boolean }>`
    cursor: pointer;
    border: 2px solid ${({ $selected }) => ($selected ? HSE_COLORS.accent : HSE_COLORS.border)} !important;
    background: ${({ $selected }) => ($selected ? "#EFF3FB" : HSE_COLORS.white)} !important;
    border-radius: 8px !important;
    margin-bottom: 8px !important;
    transition: border-color 0.2s;
`;

const SearchButton = styled(Button)`
    background: ${HSE_COLORS.primary} !important;
    border-color: ${HSE_COLORS.primary} !important;
    color: white !important;
    width: 100%;
    margin-top: 16px;
    height: 42px;
    font-size: 15px;

    &:hover {
        background: ${HSE_COLORS.accent} !important;
        border-color: ${HSE_COLORS.accent} !important;
    }
`;

const CapacityBadge = styled.span`
    color: ${HSE_COLORS.gray};
    font-size: 12px;
`;

type Step = "form" | "rooms" | "done";

export default function ByTime() {
    const navigate = useNavigate();

    const [buildings, setBuildings] = useState<Building[]>([]);
    const [rooms, setRooms] = useState<Room[]>([]);
    const [loadingBuildings, setLoadingBuildings] = useState(true);
    const [loadingRooms, setLoadingRooms] = useState(false);
    const [booking, setBooking] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const [date, setDate] = useState<string | null>(null);
    const [buildingId, setBuildingId] = useState<number | null>(null);
    const [pairIndex, setPairIndex] = useState<number | null>(null);
    const [roomId, setRoomId] = useState<number | null>(null);
    const [purpose, setPurpose] = useState("");

    const [step, setStep] = useState<Step>("form");

    const dateOptions = getNextDays(7);
    const pairOptions = HSE_PAIRS.map((p, i) => ({ label: p.label, value: i }));

    useEffect(() => {
        if (isTelegramWindow) tg.expand();
        getBuildings()
            .then(setBuildings)
            .catch(() => setError("Не удалось загрузить список корпусов"))
            .finally(() => setLoadingBuildings(false));
    }, []);

    const handleSearch = useCallback(async () => {
        if (date === null || pairIndex === null) return;
        const pair = HSE_PAIRS[pairIndex];
        setLoadingRooms(true);
        setRoomId(null);
        setError(null);
        try {
            const data = await getAvailableRooms(
                buildIso(date, pair.start),
                buildIso(date, pair.end),
                buildingId ?? undefined,
            );
            setRooms(data);
            setStep("rooms");
        } catch {
            setError("Не удалось получить список аудиторий. Проверьте соединение.");
        } finally {
            setLoadingRooms(false);
        }
    }, [date, pairIndex, buildingId]);

    const handleBook = useCallback(async () => {
        if (roomId === null || pairIndex === null || date === null) return;
        const pair = HSE_PAIRS[pairIndex];
        setBooking(true);
        setError(null);
        try {
            await createBooking({
                room_id: roomId,
                starts_at: buildIso(date, pair.start),
                ends_at: buildIso(date, pair.end),
                purpose,
            });
            setStep("done");
            if (isTelegramWindow) {
                tg.HapticFeedback?.notificationOccurred("success");
                tg.showAlert("Аудитория успешно забронирована!", () => navigate("/"));
            } else {
                navigate("/");
            }
        } catch (err: unknown) {
            const msg =
                (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
                ?? "Ошибка при создании бронирования";
            setError(msg);
        } finally {
            setBooking(false);
        }
    }, [roomId, pairIndex, date, purpose, navigate]);

    const canSearch = date !== null && pairIndex !== null;
    const selectedRoom = rooms.find((r) => r.id === roomId);

    return (
        <div>
            <BackButton onClick={() => (step === "rooms" ? setStep("form") : navigate("/"))} />

            {error && (
                <Alert
                    type="error"
                    message={error}
                    closable
                    onClose={() => setError(null)}
                    style={{ marginBottom: 12 }}
                />
            )}

            {step === "form" && (
                <>
                    <SectionTitle level={5}>Дата</SectionTitle>
                    <Select
                        size="large"
                        style={{ width: "100%" }}
                        placeholder="Выберите дату"
                        options={dateOptions}
                        value={date}
                        onChange={setDate}
                    />

                    <SectionTitle level={5}>Корпус</SectionTitle>
                    {loadingBuildings ? (
                        <Spin size="small" />
                    ) : (
                        <Select
                            size="large"
                            style={{ width: "100%" }}
                            placeholder="Все корпуса"
                            allowClear
                            options={buildings.map((b) => ({ label: b.name, value: b.id }))}
                            value={buildingId}
                            onChange={setBuildingId}
                        />
                    )}

                    <SectionTitle level={5}>Пара</SectionTitle>
                    <Select
                        size="large"
                        style={{ width: "100%" }}
                        placeholder="Выберите пару"
                        options={pairOptions}
                        value={pairIndex}
                        onChange={setPairIndex}
                        disabled={date === null}
                    />

                    <SearchButton
                        onClick={handleSearch}
                        disabled={!canSearch}
                        loading={loadingRooms}
                    >
                        Найти свободные аудитории
                    </SearchButton>
                </>
            )}

            {step === "rooms" && (
                <>
                    <div style={{ marginBottom: 12 }}>
                        <Text strong style={{ color: HSE_COLORS.primary }}>
                            {dateOptions.find((d) => d.value === date)?.label}
                        </Text>
                        {pairIndex !== null && (
                            <Text style={{ color: HSE_COLORS.gray, marginLeft: 8 }}>
                                {HSE_PAIRS[pairIndex].start}–{HSE_PAIRS[pairIndex].end}
                            </Text>
                        )}
                    </div>

                    {rooms.length === 0 ? (
                        <Alert
                            type="info"
                            message="Нет свободных аудиторий в выбранное время"
                            description="Попробуйте выбрать другую пару или корпус"
                        />
                    ) : (
                        <>
                            <Text style={{ color: HSE_COLORS.gray, fontSize: 12, display: "block", marginBottom: 8 }}>
                                Нашлось аудиторий: {rooms.length}. Выберите:
                            </Text>
                            {rooms.map((room) => (
                                <RoomCard
                                    key={room.id}
                                    size="small"
                                    $selected={roomId === room.id}
                                    onClick={() => setRoomId(room.id)}
                                >
                                    <Space direction="vertical" size={2} style={{ width: "100%" }}>
                                        <Text strong style={{ fontSize: 15 }}>
                                            Ауд. {room.name}
                                        </Text>
                                        <Text style={{ color: HSE_COLORS.gray, fontSize: 12 }}>
                                            {room.building_name}
                                        </Text>
                                        <CapacityBadge>Вместимость: {room.capacity} чел.</CapacityBadge>
                                    </Space>
                                </RoomCard>
                            ))}
                        </>
                    )}

                    {selectedRoom && (
                        <MainButton
                            text={`Забронировать ауд. ${selectedRoom.name}`}
                            onClick={handleBook}
                            progress={booking}
                            color={HSE_COLORS.primary}
                            textColor={HSE_COLORS.white}
                        />
                    )}
                </>
            )}
        </div>
    );
}
