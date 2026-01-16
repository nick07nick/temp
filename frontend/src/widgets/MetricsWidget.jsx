// frontend/src/widgets/MetricsWidget.jsx
import React, { useState, useEffect } from 'react';
import { useRobot } from '../context/RobotContext';

export const MetricsWidget = () => {
    const { pluginData } = useRobot();

    // 1. Получаем список камер из System Monitor (как везде)
    const monitor = pluginData?.system_monitor || {};
    const cameras = monitor.cameras || {};
    const availableIds = Object.keys(cameras).sort();

    // Стейт выбора камеры
    const [selectedId, setSelectedId] = useState(availableIds[0] || "0");

    // Авто-выбор первой доступной
    useEffect(() => {
        if (availableIds.length > 0 && !availableIds.includes(selectedId)) {
            setSelectedId(availableIds[0]);
        }
    }, [availableIds.length]); // eslint-disable-line

    // [FIX] Достаем данные КОНКРЕТНОГО воркера
    const camKey = `cam_${selectedId}`;
    const workerData = pluginData[camKey] || {};

    // Распаковка метрик из данных воркера
    const fpsValue = workerData.fps_meter?.fps || 0;
    const sysData = workerData.sys_load || {};
    const cpuVal = sysData.cpu || 0;
    const ramVal = sysData.ram || 0;

    // Времена выполнения стадий
    const perfList = workerData._active_plugins || [];
    const sorted = [...perfList].sort((a, b) => b.performance_ms - a.performance_ms);
    const maxMs = Math.max(...sorted.map(p => p.performance_ms), 16);

    // Цвета
    let cpuColor = '#3b82f6';
    if (cpuVal > 50) cpuColor = '#f59e0b';
    if (cpuVal > 80) cpuColor = '#ef4444';

    return (
        <div style={{ padding: 15, color: 'white', height: '100%', overflowY: 'auto', background: '#1e293b', display: 'flex', flexDirection: 'column' }}>

            {/* --- HEADER: Camera Selector --- */}
            <div style={{ marginBottom: 15, paddingBottom: 10, borderBottom: '1px solid #334155' }}>
                <div style={{ fontSize: '0.7em', color: '#94a3b8', marginBottom: 5, fontWeight: 'bold' }}>SOURCE WORKER</div>
                <select
                    value={selectedId}
                    onChange={(e) => setSelectedId(e.target.value)}
                    style={{
                        width: '100%', background: '#0f172a', color: 'white',
                        border: '1px solid #475569', padding: 6, borderRadius: 4, fontWeight: 'bold'
                    }}
                >
                    {availableIds.map(id => (
                        <option key={id} value={id}>
                            CAM {id} — {cameras[id]?.role || 'Unknown'}
                        </option>
                    ))}
                </select>
            </div>

            {/* --- FPS --- */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
                <div>
                    <div style={{ fontSize: '0.8em', color: '#94a3b8' }}>Pipeline FPS</div>
                    <div style={{ fontSize: '2.5em', fontWeight: 'bold', color: fpsValue > 25 ? '#4ade80' : '#f87171', lineHeight: 1 }}>
                        {fpsValue.toFixed(1)}
                    </div>
                </div>
                <div style={{ textAlign: 'right', fontSize: '0.75em', color: '#64748b' }}>
                   PID: {cameras[selectedId]?.status === 'fake' ? 'FAKE' : 'Active'}<br/>
                   Target: 60
                </div>
            </div>

            {/* --- SYSTEM RESOURCES --- */}
            <div style={{ marginBottom: 20 }}>
                <div style={{ fontWeight: 'bold', marginBottom: 8, color: '#e2e8f0', fontSize: '0.9em' }}>
                    Process Load
                </div>

                {/* CPU */}
                <div style={{ marginBottom: 8 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75em', marginBottom: 2 }}>
                        <span style={{ color: '#94a3b8' }}>CPU</span>
                        <span style={{ color: cpuColor, fontWeight: 'bold' }}>{cpuVal.toFixed(1)}%</span>
                    </div>
                    <div style={{ width: '100%', height: 6, background: '#0f172a', borderRadius: 3, overflow: 'hidden' }}>
                        <div style={{ width: `${Math.min(cpuVal, 100)}%`, height: '100%', background: cpuColor, borderRadius: 3, transition: 'width 0.5s ease' }} />
                    </div>
                </div>

                {/* RAM */}
                <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75em', marginBottom: 2 }}>
                        <span style={{ color: '#94a3b8' }}>RAM</span>
                        <span style={{ color: '#a5b4fc', fontWeight: 'bold' }}>{ramVal} MB</span>
                    </div>
                    <div style={{ width: '100%', height: 4, background: '#0f172a', borderRadius: 2 }}>
                        <div style={{ width: `${Math.min(ramVal / 2048 * 100, 100)}%`, height: '100%', background: '#6366f1', borderRadius: 2, transition: 'width 0.5s ease' }} />
                    </div>
                </div>
            </div>

            {/* --- TIMINGS --- */}
            <div style={{ flex: 1, overflowY: 'auto' }}>
                <div style={{ fontWeight: 'bold', marginBottom: 10, color: '#e2e8f0', display: 'flex', justifyContent: 'space-between', fontSize: '0.9em' }}>
                    <span>Stage Latency</span>
                    <span>ms</span>
                </div>

                {sorted.length === 0 && <div style={{color: '#64748b', textAlign: 'center', fontSize: '0.8em'}}>Waiting for data...</div>}

                {sorted.map(p => {
                    let barColor = '#3b82f6';
                    if (p.performance_ms > 5) barColor = '#f59e0b';
                    if (p.performance_ms > 15) barColor = '#ef4444';
                    const widthPercent = Math.min((p.performance_ms / maxMs) * 100, 100);

                    return (
                        <div key={p.id} style={{ marginBottom: 8 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2, fontSize: '0.8em' }}>
                                <span style={{ color: '#94a3b8' }}>{p.id}</span>
                                <span style={{ color: '#f1f5f9', fontFamily: 'monospace' }}>
                                    {p.performance_ms.toFixed(2)}
                                </span>
                            </div>
                            <div style={{ width: '100%', height: 4, background: '#0f172a', borderRadius: 2 }}>
                                <div style={{
                                    width: `${widthPercent}%`,
                                    height: '100%',
                                    background: barColor,
                                    borderRadius: 2,
                                    transition: 'width 0.2s ease'
                                }} />
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
};