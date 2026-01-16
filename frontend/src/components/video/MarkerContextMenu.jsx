import React from 'react';

const MarkerContextMenu = ({ position, point, onClose, onAction }) => {
    if (!position) return null;

    // Стили (можно вынести в CSS module, но пока так)
    const style = {
        position: 'absolute',
        top: position.y,
        left: position.x,
        background: '#111827',
        border: '1px solid #374151',
        borderRadius: '6px',
        padding: '4px',
        zIndex: 100,
        boxShadow: '0 4px 6px rgba(0,0,0,0.5)',
        minWidth: '150px',
        color: '#e5e7eb',
        fontSize: '13px'
    };

    const itemStyle = {
        padding: '6px 10px',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        borderRadius: '4px'
    };

    const handleHover = (e, active) => {
        e.currentTarget.style.background = active ? '#374151' : 'transparent';
    };

    return (
        <div style={style} onMouseLeave={onClose}>
            <div style={{...itemStyle, borderBottom: '1px solid #374151', cursor: 'default', fontWeight: 'bold', color: '#60a5fa'}}>
                📍 Точка {point?.id}
            </div>

            <div
                style={itemStyle}
                onClick={() => onAction('create_distance', point)}
                onMouseEnter={(e) => handleHover(e, true)}
                onMouseLeave={(e) => handleHover(e, false)}
            >
                📏 Измерить длину
            </div>

            <div
                style={itemStyle}
                onClick={() => onAction('create_angle', point)}
                onMouseEnter={(e) => handleHover(e, true)}
                onMouseLeave={(e) => handleHover(e, false)}
            >
                📐 Измерить угол
            </div>

            <div style={{height: '1px', background: '#374151', margin: '4px 0'}}></div>

            {/* ✅ Кнопка удаления */}
            <div
                style={{...itemStyle, color: '#f87171'}}
                onClick={() => onAction('delete_tools', point)}
                onMouseEnter={(e) => { e.currentTarget.style.background = '#450a0a'; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
            >
                🗑️ Остановить замеры
            </div>
        </div>
    );
};

export default MarkerContextMenu;