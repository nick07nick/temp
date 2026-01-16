// frontend/src/widgets/LayoutManagerWidget.jsx
import React, { useState } from 'react';

export const LayoutManagerWidget = ({
    currentLayoutName,
    savedLayouts,
    onSave,
    onLoad,
    onDelete,
    onSetDefault,
    defaultLayoutName
}) => {
    const [newName, setNewName] = useState('');

    const handleSave = () => {
        if (!newName.trim()) return;
        onSave(newName);
        setNewName('');
    };

    return (
        <div style={{ padding: 15, background: '#1e293b', height: '100%', color: 'white', overflowY: 'auto' }}>
            <h3 style={{ marginTop: 0, color: '#38bdf8', fontSize: '1em' }}>Layout Manager</h3>

            {/* Save Current */}
            <div style={{ display: 'flex', gap: 5, marginBottom: 15 }}>
                <input
                    type="text"
                    placeholder="New layout name..."
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    style={{
                        flex: 1, background: '#0f172a', border: '1px solid #334155',
                        color: 'white', padding: '5px 8px', borderRadius: 4
                    }}
                />
                <button
                    onClick={handleSave}
                    style={{
                        background: '#22c55e', border: 'none', borderRadius: 4,
                        color: 'white', cursor: 'pointer', fontWeight: 'bold'
                    }}
                >
                    Save
                </button>
            </div>

            {/* List */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {Object.keys(savedLayouts).map(name => (
                    <div key={name} style={{
                        background: name === currentLayoutName ? '#334155' : '#0f172a',
                        padding: 10, borderRadius: 6, border: '1px solid #475569',
                        display: 'flex', alignItems: 'center', justifyContent: 'space-between'
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <span
                                onClick={() => onSetDefault(name)}
                                style={{
                                    cursor: 'pointer',
                                    color: name === defaultLayoutName ? '#fbbf24' : '#64748b',
                                    fontSize: '1.2em'
                                }}
                                title={name === defaultLayoutName ? "Default on startup" : "Set as default"}
                            >
                                ★
                            </span>
                            <span style={{ fontWeight: name === currentLayoutName ? 'bold' : 'normal' }}>
                                {name}
                            </span>
                        </div>

                        <div style={{ display: 'flex', gap: 5 }}>
                            <button
                                onClick={() => onLoad(name)}
                                disabled={name === currentLayoutName}
                                style={{
                                    background: '#3b82f6', border: 'none', padding: '4px 8px',
                                    borderRadius: 4, color: 'white', cursor: 'pointer', fontSize: '0.8em',
                                    opacity: name === currentLayoutName ? 0.5 : 1
                                }}
                            >
                                Load
                            </button>
                            <button
                                onClick={() => onDelete(name)}
                                style={{
                                    background: '#ef4444', border: 'none', padding: '4px 8px',
                                    borderRadius: 4, color: 'white', cursor: 'pointer', fontSize: '0.8em'
                                }}
                            >
                                ✕
                            </button>
                        </div>
                    </div>
                ))}

                {Object.keys(savedLayouts).length === 0 && (
                    <div style={{ color: '#64748b', textAlign: 'center', fontSize: '0.8em' }}>
                        No saved layouts yet.
                    </div>
                )}
            </div>
        </div>
    );
};