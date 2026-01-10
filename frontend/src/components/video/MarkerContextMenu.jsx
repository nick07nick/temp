// frontend/src/components/video/MarkerContextMenu.jsx
import React from 'react';

const MarkerContextMenu = ({ position, point, onClose, onAction }) => {
    if (!point) return null;

    const btnStyle = {
        display: 'block', width: '100%', textAlign: 'left',
        padding: '6px 8px', background: 'transparent', border: 'none',
        color: '#e5e7eb', cursor: 'pointer', fontSize: '13px'
    };

    const hoverStyle = (e) => e.target.style.backgroundColor = '#374151';
    const leaveStyle = (e) => e.target.style.backgroundColor = 'transparent';

    return (
        <div style={{
            position: 'fixed', top: position.y, left: position.x,
            backgroundColor: '#1f2937', border: '1px solid #4b5563',
            borderRadius: '6px', padding: '4px 0', zIndex: 2000,
            boxShadow: '0 4px 6px rgba(0,0,0,0.3)', minWidth: '160px'
        }}>
            <div style={{ padding: '4px 8px', borderBottom: '1px solid #4b5563', marginBottom: '4px', color: '#9ca3af', fontSize: '11px', fontWeight: 'bold' }}>
                {point.label || point.id}
            </div>

            {/* Кнопки действий */}
            <button
                style={btnStyle}
                onMouseEnter={hoverStyle} onMouseLeave={leaveStyle}
                onClick={() => onAction('create_angle', point)}
            >
                📐 Измерить угол (3 точки)
            </button>

            <button
                style={btnStyle}
                onMouseEnter={hoverStyle} onMouseLeave={leaveStyle}
                onClick={() => onAction('create_distance', point)}
            >
                📏 Измерить длину (2 точки)
            </button>

            <div style={{ borderTop: '1px solid #4b5563', margin: '4px 0' }}></div>

            <button
                style={{...btnStyle, color: '#f87171'}}
                onMouseEnter={hoverStyle} onMouseLeave={leaveStyle}
                onClick={onClose}
            >
                Отмена
            </button>
        </div>
    );
};

export default MarkerContextMenu;