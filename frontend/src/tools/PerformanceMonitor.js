// frontend/src/tools/PerformanceMonitor.js
import React from 'react';

export const PerformanceMonitor = {
    id: 'perf_monitor',
    name: 'System Profiler',
    icon: '⏱️',
    draw: null,

    Controls: ({ allPluginsStatus }) => {
        if (!allPluginsStatus || allPluginsStatus.length === 0) {
            return <div style={{color: '#666', fontSize:'0.8em'}}>Collecting data...</div>;
        }

        // Сортируем: самые тяжелые сверху
        const sorted = [...allPluginsStatus].sort((a, b) => b.performance_ms - a.performance_ms);

        // Находим максимум для масштаба графика
        const maxMs = Math.max(...sorted.map(p => p.performance_ms), 10); // Минимум 10мс шкала

        return (
            <div style={{
                background: '#0f172a', border: '1px solid #334155',
                borderRadius: 6, padding: 10, fontSize: '0.8em'
            }}>
                <div style={{fontWeight:'bold', marginBottom:10, color:'#e2e8f0', display:'flex', justifyContent:'space-between'}}>
                    <span>Module Execution</span>
                    <span>ms / frame</span>
                </div>

                {sorted.map(p => {
                    // Цвет полоски зависит от тяжести
                    let barColor = '#3b82f6'; // Blue
                    if (p.performance_ms > 5) barColor = '#f59e0b'; // Orange
                    if (p.performance_ms > 15) barColor = '#ef4444'; // Red

                    const widthPercent = (p.performance_ms / maxMs) * 100;

                    return (
                        <div key={p.id} style={{marginBottom: 8}}>
                            <div style={{display:'flex', justifyContent:'space-between', marginBottom:2}}>
                                <span style={{color: '#94a3b8'}}>{p.id}</span>
                                <span style={{color: '#f1f5f9', fontFamily:'monospace'}}>
                                    {p.performance_ms.toFixed(2)}
                                </span>
                            </div>
                            {/* Фон полоски */}
                            <div style={{width: '100%', height: 4, background: '#1e293b', borderRadius: 2}}>
                                {/* Активная полоска */}
                                <div style={{
                                    width: `${widthPercent}%`,
                                    height: '100%',
                                    background: barColor,
                                    borderRadius: 2,
                                    transition: 'width 0.3s ease'
                                }}/>
                            </div>
                        </div>
                    );
                })}

                <div style={{marginTop: 10, borderTop: '1px solid #334155', paddingTop: 5, fontSize: '0.75em', color: '#64748b', textAlign:'right'}}>
                    Target: 11.11 ms (90 FPS)
                </div>
            </div>
        );
    }
};