// frontend/src/widgets/CameraSettingsWidget.jsx
import React, { useState, useEffect, useRef } from 'react';
import { useRobot } from '../context/RobotContext';

// Хук для "Оптимистичного UI" (чтобы слайдер не прыгал)
function useOptimisticValue(serverValue, delay = 1000) {
    const [value, setValue] = useState(serverValue);
    const lastInteraction = useRef(0);

    useEffect(() => {
        const now = Date.now();
        if (now - lastInteraction.current > delay) {
            setValue(serverValue);
        }
    }, [serverValue, delay]);

    const update = (newValue) => {
        lastInteraction.current = Date.now();
        setValue(newValue);
    };

    return [value, update];
}

export const CameraSettingsWidget = () => {
    const { sendCommand, pluginData } = useRobot();

    // Данные приходят в пакете system_state -> camera_config
    // Если структура данных другая, поправь путь (например data.config)
    const config = pluginData?.camera_config || {};

    // --- Exposure & Gain ---
    const [exposure, setExposure] = useOptimisticValue(config.exposure || 150);
    const [gain, setGain] = useOptimisticValue(config.gain || 0);

    // --- Threshold (Soft) ---
    // Берем значение из конфига, так как detection.py читает его оттуда
    const [threshold, setThreshold] = useOptimisticValue(config.threshold || 200);

    // Handlers
    const handleExposureChange = (e) => setExposure(Number(e.target.value));
    const handleExposureCommit = () => {
        // Отправляем SET_CONFIG для камеры
        sendCommand('camera_0', 'SET_CONFIG', { exposure: exposure });
    };

    const handleGainChange = (e) => setGain(Number(e.target.value));
    const handleGainCommit = () => {
        sendCommand('camera_0', 'SET_CONFIG', { gain: gain });
    };

    const handleThresholdChange = (e) => setThreshold(Number(e.target.value));
    const handleThresholdCommit = () => {
        // [FIX] Раньше было target: 'blob_detection'.
        // Теперь шлем SET_CONFIG, так как алгоритм читает ctx.config.threshold
        sendCommand('camera_0', 'SET_CONFIG', { threshold: threshold });
    };

    return (
        <div style={{padding: 10, color: '#e2e8f0', fontFamily: 'monospace'}}>
            <h4 style={{margin: '0 0 10px', borderBottom: '1px solid #475569'}}>Camera Control</h4>

            {/* EXPOSURE */}
            <div style={{marginBottom: 12}}>
                <div style={{display:'flex', justifyContent:'space-between', fontSize: '0.8em', marginBottom: 2, color: '#94a3b8'}}>
                    <span>Exposure</span>
                    <span style={{color: '#fff', fontWeight: 'bold'}}>{exposure}</span>
                </div>
                <input
                    type="range"
                    min={1} max={5000} step={10}
                    value={exposure}
                    onChange={handleExposureChange}
                    onMouseUp={handleExposureCommit}
                    onTouchEnd={handleExposureCommit}
                    style={{width: '100%', cursor: 'pointer', accentColor: '#38bdf8'}}
                />
            </div>

            {/* GAIN */}
            <div style={{marginBottom: 12}}>
                <div style={{display:'flex', justifyContent:'space-between', fontSize: '0.8em', marginBottom: 2, color: '#94a3b8'}}>
                    <span>Gain</span>
                    <span style={{color: '#fff', fontWeight: 'bold'}}>{gain}</span>
                </div>
                <input
                    type="range"
                    min={0} max={255} step={1}
                    value={gain}
                    onChange={handleGainChange}
                    onMouseUp={handleGainCommit}
                    onTouchEnd={handleGainCommit}
                    style={{width: '100%', cursor: 'pointer', accentColor: '#38bdf8'}}
                />
            </div>

            {/* THRESHOLD */}
            <div style={{borderTop: '1px solid #475569', margin: '15px 0', paddingTop: 15}}>
                 <div style={{marginBottom: 12}}>
                    <div style={{display:'flex', justifyContent:'space-between', fontSize: '0.8em', marginBottom: 2, color: '#94a3b8'}}>
                        <span>Soft Threshold</span>
                        <span style={{color: '#fff', fontWeight: 'bold'}}>{threshold}</span>
                    </div>
                    <input
                        type="range"
                        min={0} max={255}
                        value={threshold}
                        onChange={handleThresholdChange}
                        onMouseUp={handleThresholdCommit}
                        onTouchEnd={handleThresholdCommit}
                        style={{width: '100%', cursor: 'pointer', accentColor: '#38bdf8'}}
                    />
                </div>
            </div>
        </div>
    );
};