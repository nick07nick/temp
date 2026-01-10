import React from 'react';
import { useRobot } from '../context/RobotContext';

export const MetricsWidget = () => {
    const { pluginData } = useRobot();

    // 1. FPS
    // [FIX] Читаем правильное поле 'fps' из плагина fps_meter
    const fpsValue = pluginData?.fps_meter?.fps || pluginData?.fps_meter?.value || 0;

    // 2. Execution Times
    const perfList = pluginData?._active_plugins || [];
    const sorted = [...perfList].sort((a, b) => b.performance_ms - a.performance_ms);
    const maxMs = Math.max(...sorted.map(p => p.performance_ms), 16);

    // 3. System Load (из нашего нового плагина)
    const sysData = pluginData?.sys_load || {};
    const cpuVal = sysData.cpu || 0;
    const ramVal = sysData.ram || 0;

    // Цвет шкалы CPU
    let cpuColor = '#3b82f6'; // Blue (< 50%)
    if (cpuVal > 50) cpuColor = '#f59e0b'; // Orange
    if (cpuVal > 80) cpuColor = '#ef4444'; // Red

    return (
        <div style={{ padding: 15, color: 'white', height: '100%', overflowY: 'auto', background: '#1e293b' }}>

            {/* --- FPS --- */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20, paddingBottom: 15, borderBottom: '1px solid #334155' }}>
                <div>
                    <div style={{ fontSize: '0.8em', color: '#94a3b8' }}>Pipeline FPS</div>
                    <div style={{ fontSize: '2.5em', fontWeight: 'bold', color: fpsValue > 25 ? '#4ade80' : '#f87171', lineHeight: 1 }}>
                        {typeof fpsValue === 'number' ? fpsValue.toFixed(1) : fpsValue}
                    </div>
                </div>
                <div style={{ textAlign: 'right', fontSize: '0.75em', color: '#64748b' }}>
                   Target: 60 FPS<br/>(~16.6ms)
                </div>
            </div>

            {/* --- MODULE EXECUTION --- */}
            <div style={{ marginBottom: 20 }}>
                <div style={{ fontWeight: 'bold', marginBottom: 10, color: '#e2e8f0', display: 'flex', justifyContent: 'space-between', fontSize: '0.9em' }}>
                    <span>Module Execution</span>
                    <span>ms / frame</span>
                </div>

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

            {/* --- SYSTEM RESOURCES (NEW) --- */}
            <div style={{ paddingTop: 15, borderTop: '1px solid #334155' }}>
                <div style={{ fontWeight: 'bold', marginBottom: 12, color: '#e2e8f0', fontSize: '0.9em' }}>
                    System Load (Worker Process)
                </div>

                {/* CPU Bar */}
                <div style={{ marginBottom: 12 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, fontSize: '0.8em' }}>
                        <span style={{ color: '#94a3b8' }}>CPU Usage</span>
                        <span style={{ color: cpuColor, fontWeight: 'bold', fontFamily: 'monospace' }}>
                            {cpuVal.toFixed(1)}%
                        </span>
                    </div>
                    <div style={{ width: '100%', height: 6, background: '#0f172a', borderRadius: 3, overflow: 'hidden' }}>
                        <div style={{
                            width: `${Math.min(cpuVal, 100)}%`,
                            height: '100%',
                            background: cpuColor,
                            borderRadius: 3,
                            transition: 'width 0.5s ease',
                            boxShadow: `0 0 10px ${cpuColor}40`
                        }} />
                    </div>
                </div>

                {/* RAM Bar (Условно считаем 1GB как базу для визуализации, хотя лимит выше) */}
                <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, fontSize: '0.8em' }}>
                        <span style={{ color: '#94a3b8' }}>RAM Usage</span>
                        <span style={{ color: '#a5b4fc', fontFamily: 'monospace' }}>
                            {ramVal} MB
                        </span>
                    </div>
                    <div style={{ width: '100%', height: 4, background: '#0f172a', borderRadius: 2 }}>
                        {/* Визуальная шкала до 1024 МБ */}
                        <div style={{
                            width: `${Math.min((ramVal / 1024) * 100, 100)}%`,
                            height: '100%',
                            background: '#6366f1',
                            borderRadius: 2,
                            transition: 'width 0.5s ease'
                        }} />
                    </div>
                </div>
            </div>

        </div>
    );
};