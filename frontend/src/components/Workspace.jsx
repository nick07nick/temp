// frontend/src/components/Workspace.jsx
import React, { useState, useEffect, useRef } from 'react';
// [FIX] Импортируем WidthProvider
import GridLayout, { WidthProvider } from 'react-grid-layout';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';
import { WIDGET_REGISTRY } from '../widgets/registry';

// [FIX] Создаем обертку, которая автоматически считает ширину
const AutoGridLayout = WidthProvider(GridLayout);

const API_URL = 'http://localhost:8000/api/layouts';
const DEFAULT_KEY_NAME = 'bikefit_default_layout_name'; // Имя дефолтного храним в браузере

const initialDefaultLayout = [
    { i: 'win_cam', x: 0, y: 0, w: 8, h: 10, type: 'camera_0' },
    { i: 'win_sys', x: 8, y: 0, w: 4, h: 6, type: 'system_control' },
];

// --- WINDOW FRAME COMPONENT ---
const WindowFrame = ({ children, title, onClose, onReset, isWidget }) => {
    const [isHovered, setIsHovered] = useState(false);
    const hideTimer = useRef(null);

    const HIDE_DELAY = 1000;

    const handleMouseEnter = () => {
        if (hideTimer.current) clearTimeout(hideTimer.current);
        setIsHovered(true);
    };

    const startHideTimer = () => {
        if (hideTimer.current) clearTimeout(hideTimer.current);
        hideTimer.current = setTimeout(() => {
            setIsHovered(false);
        }, HIDE_DELAY);
    };

    const handleMouseLeave = () => {
        startHideTimer();
    };

    useEffect(() => {
        return () => { if (hideTimer.current) clearTimeout(hideTimer.current); };
    }, []);

    useEffect(() => {
        if (isHovered) {
            startHideTimer();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [title, isWidget]);

    const baseDotSize = 10;
    const posOffset = isHovered ? 6 : 2;
    const paddingLeft = isHovered ? 8 : 3;

    return (
        <div
            style={{
                height: '100%', width: '100%', position: 'relative',
                background: '#0f172a', border: '1px solid #334155', borderRadius: 8,
                overflow: 'hidden', boxShadow: '0 4px 6px rgba(0,0,0,0.3)'
            }}
        >
            <div style={{ width: '100%', height: '100%', overflow: 'hidden' }}>
                {children}
            </div>

            {/* Ghost Header */}
            <div
                className="drag-handle"
                onMouseEnter={handleMouseEnter}
                onMouseLeave={handleMouseLeave}
                style={{
                    position: 'absolute',
                    zIndex: 100,
                    top: posOffset,
                    left: posOffset,
                    height: isHovered ? 32 : 16,
                    display: 'flex', alignItems: 'center',
                    background: isHovered ? 'rgba(15, 23, 42, 0.95)' : 'transparent',
                    backdropFilter: isHovered ? 'blur(4px)' : 'none',
                    border: isHovered ? '1px solid rgba(255,255,255,0.2)' : '1px solid transparent',
                    boxShadow: isHovered ? '0 4px 12px rgba(0,0,0,0.5)' : 'none',
                    borderRadius: 20,
                    paddingLeft: paddingLeft,
                    paddingRight: isHovered ? 12 : 0,
                    cursor: 'grab',
                    width: isHovered ? 'auto' : `${baseDotSize + (paddingLeft * 2)}px`,
                    maxWidth: isHovered ? '300px' : '20px',
                    transition: 'all 0.5s cubic-bezier(0.2, 0.8, 0.2, 1)',
                    overflow: 'hidden',
                    whiteSpace: 'nowrap'
                }}
            >
                {/* ТОЧКА */}
                <div style={{
                    flexShrink: 0,
                    width: baseDotSize,
                    height: baseDotSize,
                    borderRadius: '50%',
                    background: isWidget ? '#38bdf8' : '#94a3b8',
                    border: '1px solid white',
                    boxShadow: '0 0 4px rgba(0,0,0,0.3)',
                    transform: isHovered ? 'scale(1.4)' : 'scale(1)',
                    transition: 'transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)',
                    marginRight: isHovered ? 12 : 0,
                }} />

                {/* КОНТЕНТ */}
                <div style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    opacity: isHovered ? 1 : 0,
                    transform: isHovered ? 'translateX(0)' : 'translateX(-10px)',
                    transition: 'all 0.4s ease',
                    transitionDelay: isHovered ? '0.1s' : '0s'
                }}>
                    <span style={{ fontSize: '0.75em', fontWeight: 'bold', color: '#e2e8f0', textTransform: 'uppercase' }}>
                        {title}
                    </span>

                    <div style={{ width: 1, height: 12, background: '#334155' }} />

                    <div style={{ display: 'flex', gap: 6 }}>
                        {onReset && (
                            <button
                                onMouseDown={(e) => e.stopPropagation()}
                                onClick={onReset}
                                style={{ background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: '14px', lineHeight: 1, padding: 0 }}
                                title="Menu"
                            >
                                ↩
                            </button>
                        )}
                        <button
                            onMouseDown={(e) => e.stopPropagation()}
                            onClick={onClose}
                            style={{
                                background: '#ef4444', border: 'none', color: 'white',
                                borderRadius: 4, width: 16, height: 16, display: 'flex', alignItems: 'center', justifyContent: 'center',
                                cursor: 'pointer', fontSize: '10px', fontWeight: 'bold'
                            }}
                            title="Close"
                        >
                            ✕
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};

// --- WORKSPACE LOGIC ---
export const Workspace = () => {
    // State
    const [savedLayouts, setSavedLayouts] = useState({});
    const [layout, setLayout] = useState(initialDefaultLayout);
    const [currentLayoutName, setCurrentLayoutName] = useState('Loading...');
    const [isLoaded, setIsLoaded] = useState(false);

    // 1. ЗАГРУЗКА С СЕРВЕРА ПРИ СТАРТЕ
    useEffect(() => {
        const fetchLayouts = async () => {
            try {
                const response = await fetch(API_URL);
                if (!response.ok) throw new Error('Failed to fetch layouts');

                const data = await response.json(); // { "name": [items], ... }
                setSavedLayouts(data);

                // Логика выбора стартового лейаута
                const defName = localStorage.getItem(DEFAULT_KEY_NAME);
                const keys = Object.keys(data);

                if (defName && data[defName]) {
                    setLayout(data[defName]);
                    setCurrentLayoutName(defName);
                    console.log(`[Workspace] Loaded Default: ${defName}`);
                } else if (keys.length > 0) {
                    setLayout(data[keys[0]]);
                    setCurrentLayoutName(keys[0]);
                    console.log(`[Workspace] Loaded First: ${keys[0]}`);
                } else {
                    setLayout(initialDefaultLayout);
                    setCurrentLayoutName('Unsaved');
                    console.log(`[Workspace] Loaded Factory Defaults`);
                }
            } catch (err) {
                console.error("API Error:", err);
                setLayout(initialDefaultLayout);
                setCurrentLayoutName('Offline Mode');
            } finally {
                setIsLoaded(true);
            }
        };

        fetchLayouts();
    }, []);

    // 2. СОХРАНЕНИЕ НА СЕРВЕР
    const handleSaveLayout = async (name) => {
        try {
            // Оптимистичное обновление UI
            setSavedLayouts(prev => ({ ...prev, [name]: layout }));
            setCurrentLayoutName(name);

            // Отправка на бэкенд
            await fetch(API_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: name, data: layout })
            });
            console.log(`[Workspace] Saved '${name}' to disk.`);
        } catch (err) {
            console.error("Save Failed:", err);
            alert("Error saving layout to server!");
        }
    };

    // 3. ЗАГРУЗКА ИЗ ПАМЯТИ (уже загруженной с сервера)
    const handleLoadLayout = (name) => {
        if (savedLayouts[name]) {
            setLayout(savedLayouts[name]);
            setCurrentLayoutName(name);
        }
    };

    // 4. УДАЛЕНИЕ С СЕРВЕРА
    const handleDeleteLayout = async (name) => {
        try {
            // Оптимистичное удаление
            const newLayouts = { ...savedLayouts };
            delete newLayouts[name];
            setSavedLayouts(newLayouts);

            if (currentLayoutName === name) setCurrentLayoutName('Unsaved');
            if (localStorage.getItem(DEFAULT_KEY_NAME) === name) localStorage.removeItem(DEFAULT_KEY_NAME);

            // Запрос на удаление
            await fetch(`${API_URL}/${name}`, { method: 'DELETE' });
            console.log(`[Workspace] Deleted '${name}' from disk.`);
        } catch (err) {
            console.error("Delete Failed:", err);
        }
    };

    const handleSetDefault = (name) => {
        localStorage.setItem(DEFAULT_KEY_NAME, name);
        // Форсируем обновление UI для звездочки
        setSavedLayouts({ ...savedLayouts });
    };

    const handleChangeWidget = (itemId, newType) => {
        const config = WIDGET_REGISTRY[newType];
        setLayout(prevLayout => prevLayout.map(item => {
            if (item.i !== itemId) return item;
            if (config) {
                return {
                    ...item,
                    type: newType,
                    w: config.defaultW || item.w,
                    h: config.defaultH || item.h
                };
            }
            return { ...item, type: newType };
        }));

        if (currentLayoutName !== 'Unsaved*' && currentLayoutName !== 'Unsaved') {
            setCurrentLayoutName(prev => prev.endsWith('*') ? prev : prev + '*');
        }
    };

    const renderContent = (item) => {
        const widgetConfig = WIDGET_REGISTRY[item.type];

        if (!widgetConfig) {
            return (
                <WindowFrame title="Empty" onClose={() => setLayout(layout.filter(l => l.i !== item.i))} isWidget={false}>
                     <div style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10, padding: 20 }}>
                        <div style={{ color: '#64748b', fontSize: '0.85em' }}>Select Module:</div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, width: '100%' }}>
                            {Object.keys(WIDGET_REGISTRY).map(key => (
                                <button
                                    key={key}
                                    onClick={() => handleChangeWidget(item.i, key)}
                                    style={{
                                        padding: '10px', background: '#1e293b', color: '#e2e8f0',
                                        border: '1px solid #334155', borderRadius: 6, cursor: 'pointer', textAlign: 'center', fontSize: '0.8em',
                                        transition: 'background 0.2s'
                                    }}
                                    onMouseEnter={e => e.currentTarget.style.background = '#334155'}
                                    onMouseLeave={e => e.currentTarget.style.background = '#1e293b'}
                                >
                                    {WIDGET_REGISTRY[key].title}
                                </button>
                            ))}
                        </div>
                    </div>
                </WindowFrame>
            );
        }

        const Component = widgetConfig.component;

        const extraProps = {};
        if (item.type === 'layout_manager') {
            extraProps.currentLayoutName = currentLayoutName;
            extraProps.savedLayouts = savedLayouts;
            extraProps.onSave = handleSaveLayout;
            extraProps.onLoad = handleLoadLayout;
            extraProps.onDelete = handleDeleteLayout;
            extraProps.onSetDefault = handleSetDefault;
            extraProps.defaultLayoutName = localStorage.getItem(DEFAULT_KEY_NAME);
        }

        return (
            <WindowFrame
                title={widgetConfig.title}
                onClose={() => setLayout(layout.filter(l => l.i !== item.i))}
                onReset={() => handleChangeWidget(item.i, 'empty')}
                isWidget={true}
            >
                <div style={{height: '100%', width: '100%'}}>
                    <Component {...extraProps} />
                </div>
            </WindowFrame>
        );
    };

    if (!isLoaded) {
        return (
            <div style={{
                flex: 1, background: '#020617', color: '#94a3b8',
                display: 'flex', alignItems: 'center', justifyContent: 'center'
            }}>
                Loading Workspaces...
            </div>
        );
    }

    return (
        // [FIX] Убедились, что контейнер занимает 100vh и 100vw без отступов
        <div style={{ height: '100vh', width: '100vw', overflow: 'hidden', background: '#020617', position: 'relative' }}>
             {/* [FIX] AutoGridLayout теперь сам считает width, убрали window.innerWidth */}
             <AutoGridLayout
                className="layout"
                layout={layout}
                cols={12} rowHeight={40} margin={[10, 10]}
                onLayoutChange={(newLayout) => {
                    const merged = newLayout.map(l => {
                        const original = layout.find(o => o.i === l.i);
                        return { ...l, type: original?.type || 'empty' };
                    });
                    setLayout(merged);
                    if (currentLayoutName !== 'Unsaved*' && currentLayoutName !== 'Unsaved') {
                         setCurrentLayoutName(prev => prev.endsWith('*') ? prev : prev + '*');
                    }
                }}
                draggableHandle=".drag-handle"
            >
                {layout.map(item => (
                    <div key={item.i}>{renderContent(item)}</div>
                ))}
            </AutoGridLayout>

            <button
                onClick={() => setLayout([...layout, { i: 'win_' + Date.now(), x: 0, y: Infinity, w: 4, h: 4, type: 'empty' }])}
                style={{
                    position: 'fixed', bottom: 30, right: 30, width: 56, height: 56, borderRadius: '50%',
                    background: '#3b82f6', color: 'white', border: 'none', fontSize: 28,
                    boxShadow: '0 4px 15px rgba(59, 130, 246, 0.5)', cursor: 'pointer', zIndex: 100,
                    display: 'flex', alignItems: 'center', justifyContent: 'center'
                }}
            >
                +
            </button>
        </div>
    );
};