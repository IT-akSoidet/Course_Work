import React, { useEffect } from "react";
import { Card, Typography } from "antd";
import { BackButton } from "@vkruglikov/react-telegram-web-app";
import { useNavigate } from "react-router-dom";
import styled from "styled-components";

import { isTelegramWindow, tg } from "../utils/TelegramWebApp";
import { HSE_COLORS } from "../utils/Utils";

const { Title } = Typography;

const PageTitle = styled(Title)`
    && {
        color: ${HSE_COLORS.primary} !important;
        text-align: center;
        margin-bottom: 16px !important;
    }
`;

const RuleCard = styled(Card)`
    margin-bottom: 10px;
    border-radius: 8px !important;
    border-color: ${HSE_COLORS.border} !important;

    .ant-card-head {
        background: #F5F7FB;
        color: ${HSE_COLORS.primary} !important;
        font-weight: 600;
        border-bottom-color: ${HSE_COLORS.border} !important;
    }
`;

export default function RulesPage() {
    const navigate = useNavigate();

    useEffect(() => {
        if (isTelegramWindow) tg.expand();
    }, []);

    return (
        <div>
            <BackButton onClick={() => navigate("/")} />
            <PageTitle level={4}>Правила бронирования</PageTitle>

            <RuleCard title="Время бронирования" size="small">
                <p>Аудитория доступна только в промежутки, свободные от учебных занятий по расписанию.</p>
                <p>Проверьте расписание пар перед бронированием.</p>
            </RuleCard>

            <RuleCard title="Срок бронирования" size="small">
                <p>Бронирование оформляется на одну учебную пару (80 минут).</p>
                <p>Если нужна аудитория на более долгий срок — создайте несколько бронирований.</p>
            </RuleCard>

            <RuleCard title="Отмена" size="small">
                <p>Вы можете отменить бронирование в любой момент до его начала.</p>
                <p>Найдите его в разделе «Мои бронирования» и нажмите кнопку отмены.</p>
            </RuleCard>

            <RuleCard title="Ответственность" size="small">
                <p>Аудитория предоставляется для учебных и организационных целей.</p>
                <p>Пожалуйста, оставляйте аудиторию в том состоянии, в котором вы её нашли.</p>
            </RuleCard>
        </div>
    );
}
