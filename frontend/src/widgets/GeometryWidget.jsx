// frontend/src/widgets/GeometryWidget.jsx
import React from 'react';

// Принимаем props от Wrapper'а (Dumb Component Pattern)
export const GeometryWidget = ({ data, sendCommand }) => {

    const tools = data?.tools || {};
    const toolsList = Object.entries(tools);

    const handleDelete = (id) => {
        if (sendCommand) {
            sendCommand('geometry_manager', 'cmd_remove_tool', { id });
        }
    };

    return (
        <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#1e293b', color: 'white', padding: '10px', overflow: 'hidden' }}>
            <div style={{ paddingBottom: '10px', borderBottom: '1px solid #334155', marginBottom: '10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3 style={{ margin: 0, fontSize: '0.9em', textTransform: 'uppercase', color: '#94a3b8', letterSpacing: '0.05em' }}>
                    Активные замеры
                </h3>
                <span style={{ fontSize: '0.8em', background: '#334155', padding: '2px 6px', borderRadius: '4px', color: '#e2e8f0' }}>
                    {toolsList.length}
                </span>
            </div>

            <div style={{ flex: 1, overflowY: 'auto' }}>
                {toolsList.length === 0 ? (
                    <div style={{ color: '#64748b', textAlign: 'center', marginTop: '30px', fontSize: '0.85em', lineHeight: '1.5' }}>
                        Инструменты не созданы.<br/>
                        <span style={{ fontSize: '0.8em', opacity: 0.7 }}>Кликните ПКМ по точке на видео<br/>для начала измерений.</span>
                    </div>
                ) : (
                    toolsList.map(([id, tool]) => (
                        <div key={id} style={{
                            background: '#0f172a',
                            marginBottom: '8px',
                            padding: '10px',
                            borderRadius: '6px',
                            borderLeft: `3px solid ${tool.color || '#fbbf24'}`,
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            boxShadow: '0 1px 2px rgba(0,0,0,0.2)'
                        }}>
                            <div>
                                <div style={{ fontSize: '0.75em', color: '#94a3b8', textTransform: 'uppercase', marginBottom: '2px' }}>
                                    {tool.type === 'angle' ? 'Угол' : 'Длина'}
                                </div>
                                <div style={{ fontSize: '1.2em', fontWeight: 'bold', fontFamily: 'monospace', color: '#f1f5f9' }}>
                                    {tool.current ? tool.current.toFixed(1) : '0.0'}
                                    {/* ✅ Используем unit от бэкенда, или фоллбэк */}
                                    <span style={{ fontSize: '0.6em', color: '#64748b', marginLeft: '4px', fontWeight: 'normal' }}>
                                        {tool.unit || (tool.type === 'angle' ? '°' : 'px')}
                                    </span>
                                </div>
                                <div style={{ fontSize: '0.7em', color: '#475569', marginTop: '2px' }}>
                                    {tool.points && tool.points.join(' → ')}
                                </div>
                            </div>

                            <button
                                onClick={() => handleDelete(id)}
                                title="Удалить"
                                style={{
                                    background: 'transparent',
                                    border: '1px solid #334155',
                                    color: '#94a3b8',
                                    cursor: 'pointer',
                                    width: '28px',
                                    height: '28px',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    borderRadius: '4px',
                                    transition: 'all 0.2s'
                                }}
                                onMouseEnter={(e) => { e.currentTarget.style.background = '#ef4444'; e.currentTarget.style.color = 'white'; e.currentTarget.style.borderColor = '#ef4444'; }}
                                onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = '#94a3b8'; e.currentTarget.style.borderColor = '#334155'; }}
                            >
                                ✕
                            </button>
                        </div>
                    ))
                )}
            </div>
        </div>
    );
};