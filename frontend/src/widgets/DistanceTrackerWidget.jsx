// frontend/src/widgets/DistanceTrackerWidget.jsx
import React, { useState, useEffect } from 'react';

export const DistanceTrackerWidget = ({ data, sendCommand }) => {
    // Локальный стейт для инпута ID
    const [pointId, setPointId] = useState("0");

    // Данные от бэка
    const isTracking = data?.is_tracking || false;
    const distance = data?.distance || 0.0;
    const lensRms = data?.lens_rms || 0;
    const scale = data?.scale || 0;
    const availableIds = data?.available_ids || []; // Список видимых ID

    // [AUTO-FILL] Если видим ровно одну точку и еще не трекаем - подставляем ID
    useEffect(() => {
        if (!isTracking && availableIds.length === 1) {
            setPointId(String(availableIds[0]));
        }
    }, [availableIds, isTracking]);

    const handleStart = () => {
        // [FIX] Проверка наличия функции, чтобы не падало
        if (typeof sendCommand === 'function') {
            sendCommand('start_tracking', { point_id: pointId });
        } else {
            console.error("sendCommand is not provided to DistanceTrackerWidget");
        }
    };

    const handleStop = () => {
        if (typeof sendCommand === 'function') {
            sendCommand('stop_tracking');
        }
    };

    return (
        <div style={{
            display: 'flex',
            flexDirection: 'column',
            height: '100%',
            padding: 10,
            fontFamily: 'monospace',
            color: '#e2e8f0',
            backgroundColor: '#1e293b'
        }}>
            <h4 style={{ margin: '0 0 10px', borderBottom: '1px solid #475569' }}>
                Distance Tool
            </h4>

            {/* Ввод ID точки */}
            <div style={{ marginBottom: 10, display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontSize: '0.8em', color: '#94a3b8' }}>Point ID:</span>
                <input
                    type="text"
                    value={pointId}
                    onChange={(e) => setPointId(e.target.value)}
                    disabled={isTracking}
                    style={{
                        width: 60,
                        background: '#0f172a',
                        border: '1px solid #334155',
                        color: '#fff',
                        padding: '2px 5px',
                        textAlign: 'center'
                    }}
                />
                {/* Индикатор авто-выбора (опционально можно показать, что ID подставлен) */}
                {!isTracking && availableIds.length === 1 && (
                    <span style={{ fontSize: '0.7em', color: '#22c55e' }}>Auto</span>
                )}
            </div>

            {/* Метаданные (Ошибка) - Мелко */}
            <div style={{
                fontSize: '0.75em',
                color: '#64748b',
                marginBottom: 15,
                background: '#0f172a',
                padding: 5,
                borderRadius: 4
            }}>
                <div>Scale: {scale > 0 ? scale.toFixed(2) : "N/A"} px/cm</div>
                <div>Lens Error: {lensRms > 0 ? lensRms.toFixed(3) : "N/A"} px</div>
            </div>

            {/* Главное табло - Расстояние */}
            <div style={{
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'center',
                alignItems: 'center',
                background: isTracking ? '#0f172a' : 'transparent',
                borderRadius: 8,
                border: isTracking ? '1px solid #3b82f6' : '1px dashed #475569',
                marginBottom: 15
            }}>
                <div style={{ fontSize: '3em', fontWeight: 'bold', color: '#38bdf8' }}>
                    {distance.toFixed(2)}
                </div>
                <div style={{ color: '#94a3b8', fontSize: '0.9em' }}>CM</div>
            </div>

            {/* Кнопки управления */}
            {!isTracking ? (
                <button
                    onClick={handleStart}
                    style={{
                        padding: '10px',
                        background: '#22c55e',
                        color: '#fff',
                        border: 'none',
                        borderRadius: 4,
                        cursor: 'pointer',
                        fontWeight: 'bold'
                    }}
                >
                    START TRACKING
                </button>
            ) : (
                <button
                    onClick={handleStop}
                    style={{
                        padding: '10px',
                        background: '#ef4444',
                        color: '#fff',
                        border: 'none',
                        borderRadius: 4,
                        cursor: 'pointer',
                        fontWeight: 'bold'
                    }}
                >
                    STOP
                </button>
            )}
        </div>
    );
};