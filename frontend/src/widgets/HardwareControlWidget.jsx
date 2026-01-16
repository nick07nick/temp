import React, { useState, useEffect, useRef } from 'react';
import { useRobot } from '../context/RobotContext';

const EXPOSURE_STEPS = [1, 2, 3, 6, 11, 21, 40, 79, 157, 313, 626, 1251, 2501, 5001];

export const HardwareControlWidget = () => {
    const { sendCommand, pluginData } = useRobot();

    // 1. Получаем список камер из system_monitor
    // Оркестратор шлет данные в system_monitor.cameras = { 0: {...}, 1: {...} }
    const knownCameras = pluginData?.system_monitor?.cameras || {};

    // Получаем список ID (числа)
    const cameraIds = Object.keys(knownCameras).map(Number).sort((a,b) => a - b);

    // Если камер нет вообще, показываем хотя бы 0 (fallback)
    const displayIds = cameraIds.length > 0 ? cameraIds : [0];

    // Состояние выбранной камеры
    const [selectedCamId, setSelectedCamId] = useState(displayIds[0]);

    // 2. Получаем конфиг ТЕКУЩЕЙ выбранной камеры
    // fallback на camera_config нужен для совместимости, пока не пришел system_monitor
    const activeCameraData = knownCameras[selectedCamId] || {};
    const config = activeCameraData.config || pluginData?.camera_config || {};

    // Debug info
    const roleName = activeCameraData.role || "Connecting...";

    // --- Local State ---
    const [localExpIdx, setLocalExpIdx] = useState(4);
    const [localGain, setLocalGain] = useState(0);
    const [isAuto, setIsAuto] = useState(true);

    const isDragging = useRef(false);
    const lastSentTime = useRef(0);
    const THROTTLE_MS = 200;

    // Авто-выбор первой камеры при загрузке
    useEffect(() => {
        // Если выбранной камеры нет в списке (например, при рестарте), выбираем первую доступную
        if (cameraIds.length > 0 && !cameraIds.includes(selectedCamId)) {
            setSelectedCamId(cameraIds[0]);
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [cameraIds.length]); // Триггеримся только когда меняется кол-во камер

    // Синхронизация UI с данными сервера
    useEffect(() => {
        if (!isDragging.current) {
            if (config.exposure !== undefined) {
                // Находим ближайший индекс для экспозиции
                const closestIdx = EXPOSURE_STEPS.reduce((bestIdx, curr, currIdx) => {
                    return Math.abs(curr - config.exposure) < Math.abs(EXPOSURE_STEPS[bestIdx] - config.exposure)
                        ? currIdx : bestIdx;
                }, 0);
                setLocalExpIdx(closestIdx);
            }
            if (config.gain !== undefined) setLocalGain(config.gain);
            if (config.auto_exposure !== undefined) setIsAuto(config.auto_exposure);
        }
    }, [config.exposure, config.gain, config.auto_exposure, selectedCamId]); // +selectedCamId чтобы обновлять при переключении

    // --- Отправка команд ---
    const sendUpdate = (updates, force = false) => {
        const now = Date.now();
        if (force || (now - lastSentTime.current > THROTTLE_MS)) {
            const target = `camera_${selectedCamId}`;
            // console.log(`📡 Sending to ${target}:`, updates);
            sendCommand(target, 'SET_CONFIG', updates);
            lastSentTime.current = now;
        }
    };

    const toggleAuto = () => {
        const nextStateIsAuto = !isAuto;
        setIsAuto(nextStateIsAuto);
        const payload = { auto_exposure: nextStateIsAuto };
        if (!nextStateIsAuto) {
            payload.exposure = EXPOSURE_STEPS[localExpIdx];
            payload.gain = localGain;
        }
        sendUpdate(payload, true);
    };

    const onDragStart = () => { isDragging.current = true; };
    const onDragEnd = () => { isDragging.current = false; };

    // Handlers
    const handleExposureMove = (e) => {
        if (isAuto) return;
        const idx = Number(e.target.value);
        setLocalExpIdx(idx);
        sendUpdate({ exposure: EXPOSURE_STEPS[idx] }, false);
    };
    const handleExposureCommit = (e) => {
        if (isAuto) return;
        const idx = Number(e.target.value);
        onDragEnd();
        sendUpdate({ exposure: EXPOSURE_STEPS[idx] }, true);
    };

    const handleGainMove = (e) => {
        if (isAuto) return;
        const val = Number(e.target.value);
        setLocalGain(val);
        sendUpdate({ gain: val }, false);
    };
    const handleGainCommit = (e) => {
        if (isAuto) return;
        const val = Number(e.target.value);
        onDragEnd();
        sendUpdate({ gain: val }, true);
    };

    const disabledStyle = {
        opacity: isAuto ? 0.4 : 1,
        pointerEvents: isAuto ? 'none' : 'auto',
        transition: 'opacity 0.3s ease'
    };

    return (
        <div style={{padding: 10, color: '#e2e8f0', fontFamily: 'monospace', background: '#1e293b', borderRadius: 8, marginBottom: 10}}>

            {/* HEADER */}
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 15, borderBottom: '1px solid #334155', paddingBottom: 8}}>
                <div style={{display: 'flex', flexDirection: 'column'}}>
                    <h4 style={{margin: 0, color: '#94a3b8', fontSize: '0.8em', textTransform: 'uppercase'}}>Hardware</h4>

                    {/* CAMERA SELECTOR */}
                    <select
                        value={selectedCamId}
                        onChange={(e) => setSelectedCamId(Number(e.target.value))}
                        style={{
                            background: 'transparent', color: '#e2e8f0', border: 'none',
                            fontSize: '0.9em', fontWeight: 'bold', cursor: 'pointer', outline: 'none', marginTop: 2
                        }}
                    >
                        {displayIds.map(id => (
                            <option key={id} value={id} style={{background: '#1e293b'}}>
                                CAM {id} {knownCameras[id]?.role ? `(${knownCameras[id].role})` : ''}
                            </option>
                        ))}
                    </select>
                </div>

                <button onClick={toggleAuto} style={{
                    background: isAuto ? '#10b981' : '#f59e0b', color: isAuto ? '#064e3b' : '#451a03',
                    border: 'none', borderRadius: 4, padding: '4px 10px', fontSize: '0.75em', fontWeight: 'bold', cursor: 'pointer'
                }}>
                    {isAuto ? 'AUTO' : 'MANUAL'}
                </button>
            </div>

            {/* EXPOSURE */}
            <div style={{marginBottom: 15, ...disabledStyle}}>
                <div style={{display:'flex', justifyContent:'space-between', fontSize: '0.8em', marginBottom: 4, color: '#94a3b8'}}>
                    <span>Exposure</span>
                    <span style={{color: '#fbbf24', fontWeight: 'bold'}}>{EXPOSURE_STEPS[localExpIdx]} µs</span>
                </div>
                <input
                    type="range" min={0} max={EXPOSURE_STEPS.length - 1} step={1}
                    value={localExpIdx} disabled={isAuto}
                    onMouseDown={onDragStart} onTouchStart={onDragStart}
                    onChange={handleExposureMove}
                    onMouseUp={handleExposureCommit} onTouchEnd={handleExposureCommit}
                    style={{width: '100%', cursor: isAuto ? 'not-allowed' : 'pointer', accentColor: '#fbbf24'}}
                />
            </div>

            {/* GAIN */}
            <div style={disabledStyle}>
                <div style={{display:'flex', justifyContent:'space-between', fontSize: '0.8em', marginBottom: 4, color: '#94a3b8'}}>
                    <span>Gain</span>
                    <span style={{color: '#fff', fontWeight: 'bold'}}>{localGain}</span>
                </div>
                <input
                    type="range" min={0} max={255} step={1}
                    value={localGain} disabled={isAuto}
                    onMouseDown={onDragStart} onTouchStart={onDragStart}
                    onChange={handleGainMove}
                    onMouseUp={handleGainCommit} onTouchEnd={handleGainCommit}
                    style={{width: '100%', cursor: isAuto ? 'not-allowed' : 'pointer', accentColor: '#38bdf8'}}
                />
            </div>
        </div>
    );
};