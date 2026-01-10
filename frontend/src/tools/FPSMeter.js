// frontend/src/tools/FPSMeter.js
import React from 'react';

export const FPSMeter = {
    id: 'fps_meter',
    name: 'FPS Monitor',
    icon: '⚡',

    // Рисуем на Canvas (поверх видео)
    draw: (renderer, data) => {
        if (!data) return;
        const ctx = renderer.ctx;
        const width = renderer.ctx.canvas.width;

        const fps = data.fps || 0;
        const dt = data.dt_ms || 0;

        // Цвет меняется от FPS: Зеленый > 80, Желтый > 60, Красный < 60
        let color = '#ef4444'; // Red
        if (fps > 80) color = '#4ade80'; // Green
        else if (fps > 60) color = '#facc15'; // Yellow

        // Рисуем плашку справа сверху
        ctx.save();
        ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
        ctx.fillRect(width - 110, 10, 100, 50);

        // Полоска статуса
        ctx.fillStyle = color;
        ctx.fillRect(width - 110, 10, 5, 50);

        // Текст
        ctx.fillStyle = '#fff';
        ctx.font = 'bold 20px monospace';
        ctx.fillText(`${fps.toFixed(1)}`, width - 95, 35);

        ctx.font = '12px monospace';
        ctx.fillStyle = '#94a3b8';
        ctx.fillText(`FPS (${dt}ms)`, width - 95, 52);

        ctx.restore();
    },

    // UI для сайдбара (просто инфо)
    Controls: ({ data }) => (
        <div style={{color: 'white', padding: 10, background: '#334155', borderRadius: 6}}>
            <div style={{fontWeight: 'bold', fontSize: '0.9em', color: '#94a3b8'}}>System Performance</div>
            <div style={{fontSize: '1.5em', fontWeight: 'bold', color: data?.fps > 80 ? '#4ade80' : '#ef4444'}}>
                {data?.fps || 0} FPS
            </div>
            <div style={{fontSize: '0.8em', color: '#64748b'}}>Frame time: {data?.dt_ms || 0} ms</div>
        </div>
    )
};