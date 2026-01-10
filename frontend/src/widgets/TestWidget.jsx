// src/components/TestWidget.jsx (временно для отладки)
import React, { useState, useRef } from 'react';

export const TestWidget = ({ data, sendCommand }) => {
    const [clickCount, setClickCount] = useState(0);
    const clickTimestampsRef = useRef([]);
    const lastClickTimeRef = useRef(0);

    const payload = data?.data || data || {};
    const count = payload.count_val || 0;
    const imgSrc = payload.image_src || null;
    const time = payload.server_time || 0;

    const handleClick = () => {
        const now = Date.now();
        const timeSinceLastClick = now - lastClickTimeRef.current;

        console.group('🖱️ TestWidget Button Click');
        console.log(`Click #${clickCount + 1}`);
        console.log(`Time since last click: ${timeSinceLastClick}ms`);
        console.log('Button was clicked at:', new Date().toISOString());

        // Записываем время клика
        clickTimestampsRef.current.push(now);
        lastClickTimeRef.current = now;

        // Оставляем только последние 10 кликов
        if (clickTimestampsRef.current.length > 10) {
            clickTimestampsRef.current.shift();
        }

        setClickCount(prev => prev + 1);

        // Отправляем команду
        console.log('📤 Calling sendCommand...');
        sendCommand('test_ping', 'click', {});

        console.groupEnd();

        // Логируем историю кликов
        if (clickTimestampsRef.current.length > 1) {
            const intervals = [];
            for (let i = 1; i < clickTimestampsRef.current.length; i++) {
                intervals.push(clickTimestampsRef.current[i] - clickTimestampsRef.current[i-1]);
            }
            console.log('📊 Click intervals:', intervals);
        }
    };

    return (
        <div style={{
            padding: 20,
            background: '#222',
            color: '#fff',
            border: '2px solid yellow',
            fontFamily: 'monospace'
        }}>
            <h3>🛠️ TEST PING-PONG (DEBUG)</h3>

            {/* Статистика */}
            <div style={{
                background: '#333',
                padding: 10,
                marginBottom: 10,
                borderRadius: 5
            }}>
                <div>🧪 Total clicks: {clickCount}</div>
                <div>📊 Backend counter: {count}</div>
                <div>⏱️ Server time: {time.toFixed(3)}</div>
            </div>

            {/* Картинка с бэка */}
            <div style={{ marginBottom: 10 }}>
                {imgSrc ? (
                    <img
                        src={imgSrc}
                        style={{
                            border: '1px solid #fff',
                            display: 'block',
                            margin: '0 auto'
                        }}
                        alt="test"
                    />
                ) : (
                    <div style={{ color: '#888' }}>NO IMAGE YET</div>
                )}
            </div>

            {/* Кнопка */}
            <button
                onClick={handleClick}
                style={{
                    padding: '15px 30px',
                    marginTop: 10,
                    fontSize: '1.2em',
                    background: '#4CAF50',
                    color: 'white',
                    border: 'none',
                    borderRadius: '5px',
                    cursor: 'pointer',
                    display: 'block',
                    margin: '0 auto',
                    fontWeight: 'bold'
                }}
                title={`Click #${clickCount + 1}`}
            >
                🔴 ТЫКНИ МЕНЯ
            </button>

            {/* Инструкция */}
            <div style={{
                marginTop: 15,
                fontSize: '0.8em',
                color: '#aaa',
                textAlign: 'center'
            }}>
                Откройте консоль браузера (F12) для просмотра логов
            </div>
        </div>
    );
};