import React, { useEffect } from "react";
import { Link } from "react-router-dom";
import { Typography } from "antd";
import styled from "styled-components";

import { isTelegramWindow, tg } from "../utils/TelegramWebApp";
import { HSE_COLORS } from "../utils/Utils";

const { Title } = Typography;

const Wrapper = styled.div`
    padding: 8px 0;
`;

const PageTitle = styled(Title)`
    && {
        color: ${HSE_COLORS.primary} !important;
        text-align: center;
        margin-bottom: 24px !important;
        font-size: 20px !important;
    }
`;

const NavButton = styled(Link)`
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px;
    margin-bottom: 10px;
    background: ${HSE_COLORS.white};
    border: 2px solid ${HSE_COLORS.border};
    border-radius: 10px;
    color: ${HSE_COLORS.primary};
    font-weight: 600;
    font-size: 15px;
    text-decoration: none;
    transition: border-color 0.2s, background 0.2s;

    &:hover {
        border-color: ${HSE_COLORS.accent};
        background: #EFF3FB;
        color: ${HSE_COLORS.accent};
    }
`;

const NavButtonIcon = styled.span`
    font-size: 20px;
`;

const Chevron = styled.span`
    color: ${HSE_COLORS.border};
    font-size: 18px;
`;

export default function NavigationPage() {
    useEffect(() => {
        if (isTelegramWindow) {
            tg.BackButton?.hide();
        }
    }, []);

    return (
        <Wrapper>
            <PageTitle level={3}>Главное меню</PageTitle>

            <NavButton to="/book">
                <span>
                    <NavButtonIcon>📅</NavButtonIcon>{"  "}
                    Забронировать аудиторию
                </span>
                <Chevron>›</Chevron>
            </NavButton>

            <NavButton to="/my">
                <span>
                    <NavButtonIcon>📋</NavButtonIcon>{"  "}
                    Мои бронирования
                </span>
                <Chevron>›</Chevron>
            </NavButton>

            <NavButton to="/rules">
                <span>
                    <NavButtonIcon>📖</NavButtonIcon>{"  "}
                    Правила использования
                </span>
                <Chevron>›</Chevron>
            </NavButton>
        </Wrapper>
    );
}
