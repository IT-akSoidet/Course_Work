import "./index.css";

import React from "react";
import { ConfigProvider } from "antd";
import ruRU from "antd/locale/ru_RU";
import { BrowserRouter } from "react-router-dom";
import styled from "styled-components";

import { Logo } from "./components/Logo";
import Pages from "./pages/Pages";
import { isTelegramWindow, tg } from "./utils/TelegramWebApp";
import { HSE_COLORS } from "./utils/Utils";

const AppWrapper = styled.div`
    min-height: 100vh;
    background: ${HSE_COLORS.white};
`;

const Header = styled.header`
    background: ${HSE_COLORS.primary};
    padding: 12px 16px;
    display: flex;
    align-items: center;
`;

const HeaderLogo = styled.div`
    display: flex;
    align-items: center;
    gap: 10px;
`;

const HeaderTitle = styled.div`
    color: ${HSE_COLORS.white};
    font-weight: 700;
    font-size: 13px;
    line-height: 1.3;
`;

const Content = styled.div`
    padding: 16px;
`;

const NoTelegramMsg = styled.div`
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 80vh;
    text-align: center;
    padding: 24px;
    color: ${HSE_COLORS.gray};
`;

function App(): JSX.Element {
    if (isTelegramWindow) {
        tg.expand();
        tg.enableClosingConfirmation();
    }

    return (
        <ConfigProvider
            locale={ruRU}
            theme={{
                token: {
                    colorPrimary: HSE_COLORS.accent,
                    colorLink: HSE_COLORS.accent,
                    borderRadius: 6,
                    fontFamily: "'Inter', 'Arial', sans-serif",
                },
                components: {
                    Button: {
                        colorPrimary: HSE_COLORS.primary,
                        colorPrimaryHover: HSE_COLORS.accent,
                    },
                },
            }}
        >
            <AppWrapper>
                <Header>
                    <HeaderLogo>
                        <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
                            <rect width="32" height="32" rx="3" fill="white" fillOpacity="0.15" />
                            <text x="16" y="22" textAnchor="middle" fill="white" fontSize="13" fontWeight="bold">
                                ВШЭ
                            </text>
                        </svg>
                        <HeaderTitle>
                            НИУ ВШЭ — Нижний Новгород<br />
                            <span style={{ fontWeight: 400, fontSize: 11 }}>Бронирование аудиторий</span>
                        </HeaderTitle>
                    </HeaderLogo>
                </Header>

                <Content>
                    {isTelegramWindow ? (
                        <BrowserRouter>
                            <Pages />
                        </BrowserRouter>
                    ) : (
                        <NoTelegramMsg>
                            <p style={{ fontSize: 16, marginBottom: 8 }}>
                                Приложение доступно только в Telegram
                            </p>
                            <p style={{ fontSize: 13 }}>
                                Откройте его через бота бронирования ВШЭ
                            </p>
                        </NoTelegramMsg>
                    )}
                </Content>
            </AppWrapper>
        </ConfigProvider>
    );
}

export default App;
