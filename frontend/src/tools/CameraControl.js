// frontend/src/tools/CameraControl.js
import React, { useState, useEffect, useRef } from 'react';

// Твоя "золотая" последовательность.
// Камера понимает ТОЛЬКО эти значения. Всё остальное — иллюзия.
const EXPOSURE_STEPS = [1, 2, 3, 6, 11, 21, 40, 79, 157, 313, 626, 1251, 2501, 5001];

export const CameraControl = {
    id: 'camera_control',
    name: 'Global Shutter Settings',
    icon: '⚙️',
    draw: null,

    Controls: ({ data, sendCommand }) => {
        const [localState, setLocalState] = useState(data || {});
        const [isDragging, setIsDragging] = useState(false);
        const [isManual, setIsManual] = useState(false);

        const lastSentTime = useRef(0);
        const THROTTLE_MS = 300; // Троттлинг для защиты FPS

        // === ХЕЛПЕРЫ ДЛЯ ДИСКРЕТНЫХ ШАГОВ ===

        // Найти индекс ближайшего "честного" значения (если с бэка пришло 200, вернем индекс для 157)
        const getStepIndex = (val) => {
            if (!val) return 4; // Дефолт где-то посередине (11)
            // Ищем число, к которому val ближе всего
            return EXPOSURE_STEPS.reduce((bestIdx, curr, currIdx) => {
                const bestDiff = Math.abs(EXPOSURE_STEPS[bestIdx] - val);
                const currDiff = Math.abs(curr - val);
                return currDiff < bestDiff ? currIdx : bestIdx;
            }, 0);
        };

        useEffect(() => {
            if (!isDragging) {
                setLocalState(prev => ({ ...prev, ...data }));
                if (data && typeof data.auto_exposure !== 'undefined') {
                    setIsManual(data.auto_exposure === false);
                }
            }
        }, [data, isDragging]);

        const handleInteractionStart = () => setIsDragging(true);

        // Общая функция для обычных слайдеров
        const handleLinearSlide = (key, val) => {
            const intVal = parseInt(val);
            setLocalState(prev => ({ ...prev, [key]: intVal }));
            sendThrottled(key, intVal);
        };

        // Спец-функция для экспозиции (принимает ИНДЕКС, отправляет ЗНАЧЕНИЕ)
        const handleExposureSlide = (idx) => {
            const realVal = EXPOSURE_STEPS[idx]; // Превращаем 5 -> 21
            setLocalState(prev => ({ ...prev, exposure: realVal }));

            // Сразу переключаем в Manual при касании
            setIsManual(true);
            sendThrottled('exposure', realVal, true); // true = force manual
        };

        const sendThrottled = (key, val, forceManual = false) => {
            const now = Date.now();
            if (now - lastSentTime.current > THROTTLE_MS) {
                console.log(`🌊 Throttled: ${key}=${val}`);

                const payload = { [key]: val };
                if (forceManual || key === 'exposure') {
                    payload.auto_exposure = false;
                }

                sendCommand('set_params', payload);
                lastSentTime.current = now;
            }
        };

        const handleCommit = (key, val, isExposureIndex = false) => {
            let finalVal = parseInt(val);
            if (isExposureIndex) {
                finalVal = EXPOSURE_STEPS[finalVal];
            }

            console.log(`🚀 Commit: ${key}=${finalVal}`);

            const payload = { [key]: finalVal };
            if (key === 'exposure') { // Фиксация ручного режима
                payload.auto_exposure = false;
                setIsManual(true);
            }

            sendCommand('set_params', payload);
            setTimeout(() => setIsDragging(false), 500);
        };

        const toggleAutoMode = () => {
            const newState = !isManual;
            setIsManual(newState);
            // Если включаем авто -> auto_exposure: true
            // Если выключаем авто -> auto_exposure: false
            sendCommand('set_params', { "auto_exposure": !newState });
        };

        // Вычисляем текущий индекс для слайдера
        const currentExposureIdx = getStepIndex(localState.exposure);

        return (
            <div style={{color: 'white', padding: 10, background: '#334155', borderRadius: 6}}>
                <div style={{fontWeight: 'bold', marginBottom: 15, color: '#cbd5e1', display:'flex', justifyContent:'space-between', alignItems:'center'}}>
                    <span>Camera Settings</span>
                    <button
                        onClick={toggleAutoMode}
                        style={{
                            fontSize:'0.7em', padding:'4px 12px',
                            background: isManual ? '#4ade80' : '#3b82f6',
                            border:'none', color: isManual ? '#0f172a' : 'white',
                            borderRadius:4, cursor:'pointer', fontWeight:'bold',
                            minWidth: '80px', transition: 'all 0.2s'
                        }}
                    >
                        {isManual ? "MANUAL" : "AUTO"}
                    </button>
                </div>

                {/* === ДИСКРЕТНЫЙ СЛАЙДЕР ЭКСПОЗИЦИИ === */}
                <div style={{marginBottom: 12}}>
                    <div style={{display:'flex', justifyContent:'space-between', fontSize: '0.8em', marginBottom: 2, color: '#94a3b8'}}>
                        <span>Exposure (Step)</span>
                        <span style={{color: '#fff', fontWeight: 'bold'}}>
                            {EXPOSURE_STEPS[currentExposureIdx]} µs
                        </span>
                    </div>
                    <input
                        type="range"
                        min={0}
                        max={EXPOSURE_STEPS.length - 1} // От 0 до 13
                        step={1}
                        value={currentExposureIdx}
                        onMouseDown={handleInteractionStart} onTouchStart={handleInteractionStart}
                        onChange={(e) => handleExposureSlide(e.target.value)}
                        onMouseUp={(e) => handleCommit('exposure', e.target.value, true)}
                        onTouchEnd={(e) => handleCommit('exposure', e.target.value, true)}
                        style={{width: '100%', cursor: 'pointer', accentColor: '#fbbf24'}} // Желтый цвет для особого слайдера
                    />
                    <div style={{fontSize:'0.6em', color:'#64748b', display:'flex', justifyContent:'space-between'}}>
                        <span>Fast (1µs)</span>
                        <span>Slow (5ms)</span>
                    </div>
                </div>

                {/* === ОБЫЧНЫЙ СЛАЙДЕР GAIN === */}
                <SliderControl
                    label="Gain"
                    value={localState.gain || 0}
                    min={0} max={1023} step={1}
                    onStart={handleInteractionStart}
                    onChange={(v) => handleLinearSlide('gain', v)}
                    onCommit={(v) => handleCommit('gain', v)}
                />

                <div style={{borderTop: '1px solid #475569', margin: '10px 0', paddingTop: 10}}>
                     <SliderControl
                        label="Soft Threshold"
                        value={localState.threshold || 200}
                        min={0} max={255}
                        onStart={handleInteractionStart}
                        onChange={(v) => handleLinearSlide('threshold', v)}
                        onCommit={(v) => handleCommit('threshold', v)}
                    />
                </div>
            </div>
        );
    }
};

const SliderControl = ({ label, value, min, max, step=1, onStart, onChange, onCommit }) => (
    <div style={{marginBottom: 12}}>
        <div style={{display:'flex', justifyContent:'space-between', fontSize: '0.8em', marginBottom: 2, color: '#94a3b8'}}>
            <span>{label}</span>
            <span style={{color: '#fff', fontWeight: 'bold'}}>{value}</span>
        </div>
        <input
            type="range"
            min={min} max={max} step={step}
            value={value}
            onMouseDown={onStart} onTouchStart={onStart}
            onChange={(e) => onChange(e.target.value)}
            onMouseUp={(e) => onCommit(e.target.value)} onTouchEnd={(e) => onCommit(e.target.value)}
            style={{width: '100%', cursor: 'pointer', accentColor: '#38bdf8'}}
        />
    </div>
);