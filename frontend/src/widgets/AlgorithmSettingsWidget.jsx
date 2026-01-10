import React, { useState, useEffect, useRef } from 'react';
import { useRobot } from '../context/RobotContext';

export const AlgorithmSettingsWidget = () => {
    const { sendCommand, pluginData } = useRobot();
    const config = pluginData?.camera_config || {};

    const [threshold, setThreshold] = useState(200);
    const isDragging = useRef(false);
    const lastSentTime = useRef(0);
    const THROTTLE_MS = 150;

    useEffect(() => {
        if (!isDragging.current && config.threshold !== undefined) {
            setThreshold(config.threshold);
        }
    }, [config]);

    const sendUpdate = (updates, force = false) => {
        const now = Date.now();
        if (force || (now - lastSentTime.current > THROTTLE_MS)) {
            // Threshold тоже живет в SET_CONFIG (CameraConfig),
            // так как он применяется на уровне ProcessorContext
            sendCommand('camera_0', 'SET_CONFIG', updates);
            lastSentTime.current = now;
        }
    };

    const onDragStart = () => { isDragging.current = true; };
    const onDragEnd = () => { isDragging.current = false; };

    const handleThreshMove = (e) => {
        const val = Number(e.target.value);
        setThreshold(val);
        sendUpdate({ threshold: val }, false);
    };

    const handleThreshCommit = (e) => {
        const val = Number(e.target.value);
        onDragEnd();
        sendUpdate({ threshold: val }, true);
    };

    return (
        <div style={{padding: 10, color: '#e2e8f0', fontFamily: 'monospace', background: '#0f172a', borderRadius: 8, border: '1px solid #334155'}}>
            <h4 style={{margin: '0 0 10px', color: '#94a3b8', fontSize: '0.9em', textTransform: 'uppercase', letterSpacing: 1}}>
                🧠 Algorithms (Software)
            </h4>

            {/* THRESHOLD */}
            <div>
                <div style={{display:'flex', justifyContent:'space-between', fontSize: '0.8em', marginBottom: 4, color: '#94a3b8'}}>
                    <span>Blob Threshold</span>
                    <span style={{color: '#a5b4fc', fontWeight: 'bold'}}>{threshold}</span>
                </div>
                <input
                    type="range"
                    min={0} max={255} step={1}
                    value={threshold}
                    onMouseDown={onDragStart} onTouchStart={onDragStart}
                    onChange={handleThreshMove}
                    onMouseUp={handleThreshCommit} onTouchEnd={handleThreshCommit}
                    style={{width: '100%', cursor: 'pointer', accentColor: '#a5b4fc'}}
                />
                <div style={{fontSize: '0.7em', color: '#64748b', marginTop: 5}}>
                    Lower = More sensitivity (more noise)
                </div>
            </div>
        </div>
    );
};