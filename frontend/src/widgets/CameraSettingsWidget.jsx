import React, { useState, useEffect, useRef } from 'react';
import { useRobot } from '../context/RobotContext';

// Хук для "Оптимистичного UI" (твой код)
function useOptimisticValue(serverValue, delay = 1000) {
    const [value, setValue] = useState(serverValue);
    const lastInteraction = useRef(0);

    useEffect(() => {
        const now = Date.now();
        if (now - lastInteraction.current > delay) {
            setValue(serverValue || 0);
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

    // 1. Получаем список доступных камер из system_monitor (или делаем fallback)
    // Предполагаем, что heartbeat собирается в system_monitor.cameras
    const knownCameras = pluginData?.system_monitor?.cameras || {};

    // Если пусто, хотя бы camera_0 должна быть
    const cameraIds = Object.keys(knownCameras).length > 0
        ? Object.keys(knownCameras).map(Number)
        : [0];

    const [selectedCamId, setSelectedCamId] = useState(cameraIds[0]);

    // 2. Получаем конфиг выбранной камеры
    // Воркер теперь шлет "config" в heartbeat, значит он будет здесь
    const activeCameraConfig = knownCameras[selectedCamId]?.config || pluginData?.camera_config || {};

    // --- Exposure & Gain (State) ---
    const [exposure, setExposure] = useOptimisticValue(activeCameraConfig.exposure || 150);
    const [gain, setGain] = useOptimisticValue(activeCameraConfig.gain || 0);
    const [threshold, setThreshold] = useOptimisticValue(activeCameraConfig.threshold || 200);

    // Следим, чтобы ID не потерялся при рестарте
    useEffect(() => {
        if (!cameraIds.includes(selectedCamId) && cameraIds.length > 0) {
            setSelectedCamId(cameraIds[0]);
        }
    }, [cameraIds]);

    // --- Handlers (Universal) ---
    const commitValue = (param, val) => {
        // Формируем target динамически: camera_0, camera_1...
        const target = `camera_${selectedCamId}`;
        console.log(`Sending to ${target}: ${param}=${val}`);

        // Отправляем команду так же, как и раньше
        sendCommand(target, 'SET_CONFIG', { [param]: val });
    };

    return (
        <div style={{padding: 10, color: '#e2e8f0', fontFamily: 'monospace'}}>
            {/* Header + Selector */}
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 15, borderBottom: '1px solid #475569', paddingBottom: 10}}>
                <h4 style={{margin: 0}}>Hardware Control</h4>
                <select
                    value={selectedCamId}
                    onChange={(e) => setSelectedCamId(Number(e.target.value))}
                    style={{background: '#1e293b', color: 'white', border: '1px solid #475569', padding: '2px 5px', borderRadius: 4}}
                >
                    {cameraIds.map(id => (
                        <option key={id} value={id}>
                            CAM {id} {knownCameras[id]?.role ? `(${knownCameras[id].role})` : ''}
                        </option>
                    ))}
                </select>
            </div>

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
                    onChange={(e) => setExposure(Number(e.target.value))}
                    onMouseUp={() => commitValue('exposure', exposure)}
                    onTouchEnd={() => commitValue('exposure', exposure)}
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
                    onChange={(e) => setGain(Number(e.target.value))}
                    onMouseUp={() => commitValue('gain', gain)}
                    onTouchEnd={() => commitValue('gain', gain)}
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
                        onChange={(e) => setThreshold(Number(e.target.value))}
                        onMouseUp={() => commitValue('threshold', threshold)}
                        onTouchEnd={() => commitValue('threshold', threshold)}
                        style={{width: '100%', cursor: 'pointer', accentColor: '#38bdf8'}}
                    />
                </div>
            </div>
        </div>
    );
};