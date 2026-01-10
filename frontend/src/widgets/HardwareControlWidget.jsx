import React, { useState, useEffect, useRef } from 'react';
import { useRobot } from '../context/RobotContext';

const EXPOSURE_STEPS = [1, 2, 3, 6, 11, 21, 40, 79, 157, 313, 626, 1251, 2501, 5001];

export const HardwareControlWidget = () => {
    const { sendCommand, pluginData } = useRobot();

    // Получаем конфиг или пустой объект
    const config = pluginData?.camera_config || {};

    const [localExpIdx, setLocalExpIdx] = useState(4);
    const [localGain, setLocalGain] = useState(0);
    const [isAuto, setIsAuto] = useState(true);

    const isDragging = useRef(false);
    const lastSentTime = useRef(0);
    const THROTTLE_MS = 200;

    // [FIX] Исправляем Warning: указываем конкретные поля в зависимостях
    useEffect(() => {
        if (!isDragging.current) {
            // 1. Синхронизируем Экспозицию
            if (config.exposure !== undefined) {
                const closestIdx = EXPOSURE_STEPS.reduce((bestIdx, curr, currIdx) => {
                    return Math.abs(curr - config.exposure) < Math.abs(EXPOSURE_STEPS[bestIdx] - config.exposure)
                        ? currIdx : bestIdx;
                }, 0);
                setLocalExpIdx(closestIdx);
            }

            // 2. Синхронизируем Gain
            if (config.gain !== undefined) {
                setLocalGain(config.gain);
            }

            // 3. Синхронизируем Авто-режим
            if (config.auto_exposure !== undefined) {
                setIsAuto(config.auto_exposure);
            }
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [config.exposure, config.gain, config.auto_exposure]);
    // ^ Мы следим только за изменением значений, а не всего объекта config

    const sendUpdate = (updates, force = false) => {
        const now = Date.now();
        if (force || (now - lastSentTime.current > THROTTLE_MS)) {
            sendCommand('camera_0', 'SET_CONFIG', updates);
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

    const handleExposureMove = (e) => {
        if (isAuto) return;
        const idx = Number(e.target.value);
        setLocalExpIdx(idx);
        const realValue = EXPOSURE_STEPS[idx];
        sendUpdate({ exposure: realValue }, false);
    };

    const handleExposureCommit = (e) => {
        if (isAuto) return;
        const idx = Number(e.target.value);
        const realValue = EXPOSURE_STEPS[idx];
        onDragEnd();
        sendUpdate({ exposure: realValue }, true);
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

            {/* HEADER WITH TOGGLE BUTTON */}
            <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 15,
                borderBottom: '1px solid #334155',
                paddingBottom: 8
            }}>
                <h4 style={{margin: 0, color: '#94a3b8', fontSize: '0.9em', textTransform: 'uppercase', letterSpacing: 1}}>
                    📸 Hardware
                </h4>

                <button
                    onClick={toggleAuto}
                    style={{
                        background: isAuto ? '#10b981' : '#f59e0b',
                        color: isAuto ? '#064e3b' : '#451a03',
                        border: 'none',
                        borderRadius: 4,
                        padding: '4px 10px',
                        fontSize: '0.75em',
                        cursor: 'pointer',
                        fontWeight: 'bold',
                        boxShadow: '0 2px 5px rgba(0,0,0,0.2)',
                        transition: 'all 0.2s'
                    }}
                >
                    {isAuto ? 'AUTO' : 'MANUAL'}
                </button>
            </div>

            {/* EXPOSURE */}
            <div style={{marginBottom: 15, ...disabledStyle}}>
                <div style={{display:'flex', justifyContent:'space-between', fontSize: '0.8em', marginBottom: 4, color: '#94a3b8'}}>
                    <span>Exposure Time</span>
                    <span style={{color: '#fbbf24', fontWeight: 'bold'}}>{EXPOSURE_STEPS[localExpIdx]} µs</span>
                </div>
                <input
                    type="range"
                    min={0}
                    max={EXPOSURE_STEPS.length - 1}
                    step={1}
                    value={localExpIdx}
                    disabled={isAuto}
                    onMouseDown={onDragStart} onTouchStart={onDragStart}
                    onChange={handleExposureMove}
                    onMouseUp={handleExposureCommit} onTouchEnd={handleExposureCommit}
                    style={{width: '100%', cursor: isAuto ? 'not-allowed' : 'pointer', accentColor: '#fbbf24'}}
                />
            </div>

            {/* GAIN */}
            <div style={disabledStyle}>
                <div style={{display:'flex', justifyContent:'space-between', fontSize: '0.8em', marginBottom: 4, color: '#94a3b8'}}>
                    <span>Sensor Gain</span>
                    <span style={{color: '#fff', fontWeight: 'bold'}}>{localGain}</span>
                </div>
                <input
                    type="range"
                    min={0} max={255} step={1}
                    value={localGain}
                    disabled={isAuto}
                    onMouseDown={onDragStart} onTouchStart={onDragStart}
                    onChange={handleGainMove}
                    onMouseUp={handleGainCommit} onTouchEnd={handleGainCommit}
                    style={{width: '100%', cursor: isAuto ? 'not-allowed' : 'pointer', accentColor: '#38bdf8'}}
                />
            </div>
        </div>
    );
};