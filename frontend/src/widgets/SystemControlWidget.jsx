// src/widgets/SystemControlWidget.jsx
import React from 'react';
import { useRobot } from '../context/RobotContext';

export const SystemControlWidget = () => {
    const { sendCommand, pluginData } = useRobot();

    // Предполагаем, что конфиг приходит где-то в pluginData или мы запрашиваем его отдельно.
    // Пока сделаем локальные переключатели, отправляющие команды.

    const toggleStage = (stageName, currentState) => {
        // Пример команды конфигурации
        const key = `enable_${stageName}`; // enable_undistort
        sendCommand('core', 'SET_CONFIG', { [key]: !currentState });
    };

    return (
        <div style={{ padding: 10, display: 'flex', flexDirection: 'column', gap: 10, height: '100%', overflow: 'auto' }}>
            <div style={{ fontSize: '0.8em', color: '#94a3b8', textTransform: 'uppercase' }}>Kernel Modules</div>

            <ToggleItem
                label="Undistort (Lens Correction)"
                active={true} // TODO: Брать из pluginData.config
                onClick={() => toggleStage('undistort', true)}
            />

            <ToggleItem
                label="Calibration Mode"
                active={false}
                onClick={() => sendCommand('core', 'SET_CONFIG', { is_calibration_mode: true })}
            />

            <div style={{ height: 1, background: '#334155', margin: '5px 0' }} />

            <div style={{ fontSize: '0.8em', color: '#94a3b8', textTransform: 'uppercase' }}>System</div>
            <button
                onClick={() => sendCommand('core', 'RESTART_PIPELINE')}
                style={{ background: '#f59e0b', border: 'none', padding: 8, borderRadius: 4, cursor: 'pointer', fontWeight: 'bold' }}
            >
                ⚡ Restart Pipeline
            </button>
        </div>
    );
};

const ToggleItem = ({ label, active, onClick }) => (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#1e293b', padding: 8, borderRadius: 4, border: '1px solid #334155' }}>
        <span style={{ fontSize: '0.9em', color: '#e2e8f0' }}>{label}</span>
        <button
            onClick={onClick}
            style={{
                width: 40, height: 20, borderRadius: 10, border: 'none', cursor: 'pointer',
                background: active ? '#10b981' : '#475569', position: 'relative'
            }}
        >
            <div style={{
                width: 16, height: 16, borderRadius: '50%', background: 'white',
                position: 'absolute', top: 2, left: active ? 22 : 2, transition: 'left 0.2s'
            }} />
        </button>
    </div>
);
