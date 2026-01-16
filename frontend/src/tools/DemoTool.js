// frontend/src/tools/DemoTool.js
import React from 'react';

export const DemoTool = {
    id: 'demo_stats', // Должен совпадать с PLUGIN_ID в python-файле
    name: 'Stats Monitor',
    icon: '📊',

    /**
     * ЛОГИКА ОТРИСОВКИ (Canvas Layer)
     * renderer - это наш класс BikeFitRenderer
     * data - это то, что прислал Python (msg, points_seen)
     */
    draw: (renderer, data) => {
        if (!data) return;
        const ctx = renderer.ctx;

        // Рисуем красивую полупрозрачную плашку
        ctx.save();
        ctx.fillStyle = 'rgba(15, 23, 42, 0.8)'; // Темно-синий фон
        ctx.strokeStyle = '#4ade80'; // Зеленая рамка
        ctx.lineWidth = 1;

        // Рисуем прямоугольник с закругленными углами
        // (если браузер старый и не умеет roundRect, можно просто rect)
        if (ctx.roundRect) {
            ctx.beginPath();
            ctx.roundRect(10, 10, 320, 90, 8);
            ctx.fill();
            ctx.stroke();
        } else {
            ctx.fillRect(10, 10, 320, 90);
            ctx.strokeRect(10, 10, 320, 90);
        }

        // Заголовок
        ctx.fillStyle = '#4ade80';
        ctx.font = 'bold 16px system-ui, sans-serif';
        ctx.fillText(`🔌 Plugin System Active`, 25, 35);

        // Данные от Python
        ctx.fillStyle = '#fff';
        ctx.font = '14px monospace';
        ctx.fillText(data.msg || "Waiting for data...", 25, 60);
        ctx.fillText(`Points Detected: ${data.points_seen !== undefined ? data.points_seen : '-'}`, 25, 80);

        ctx.restore();
    },

    /**
     * ЛОГИКА ИНТЕРФЕЙСА (React UI Layer)
     * Панелька с кнопками, которая будет в сайдбаре
     */
    Controls: ({ data, sendCommand }) => {
        return (
            <div style={{
                background: '#334155',
                borderRadius: 6,
                padding: 10,
                marginTop: 10,
                color: 'white',
                border: '1px solid #475569'
            }}>
                <div style={{display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8}}>
                    <span>📊</span>
                    <span style={{fontWeight: 'bold', fontSize: '0.9em'}}>Stats Control</span>
                </div>

                <div style={{fontSize: '0.75em', color: '#94a3b8', marginBottom: 10}}>
                   Last msg: {data?.msg?.split('!')[1] || '-'}
                </div>

                <button
                    onClick={() => sendCommand('reset_counter')}
                    style={{
                        width: '100%',
                        background: '#ef4444',
                        color: 'white',
                        border: 'none',
                        padding: '6px',
                        borderRadius: 4,
                        cursor: 'pointer',
                        fontWeight: '600',
                        fontSize: '0.85em'
                    }}
                >
                    Reset Counter (Backend)
                </button>
            </div>
        );
    }
};