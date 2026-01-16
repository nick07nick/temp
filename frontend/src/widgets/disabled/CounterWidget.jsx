import React, { useState, useEffect, useRef } from 'react';
import { useRobot } from '../context/RobotContext';

export const CounterWidget = () => {
    const { pluginData, sendCommand } = useRobot();
    const [count, setCount] = useState(0);
    const [loading, setLoading] = useState(false);
    const [logMessages, setLogMessages] = useState([]);
    const logEndRef = useRef(null);

    // Логирование
    const addLog = (message, type = 'info') => {
        const timestamp = new Date().toLocaleTimeString();
        const logEntry = `[${timestamp}] ${message}`;

        setLogMessages(prev => {
            const newLogs = [...prev, { message: logEntry, type, timestamp }];
            return newLogs.slice(-10);
        });

        console.log(`[CounterWidget] ${logEntry}`);
    };

    // Автопрокрутка логов
    useEffect(() => {
        logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [logMessages]);

    // Подписываемся на данные от бэкенда
    useEffect(() => {
        const counterData = pluginData?.counter;

        // Проверяем разные форматы данных
        let receivedValue;
        if (counterData) {
            if (typeof counterData === 'object' && counterData.value !== undefined) {
                receivedValue = counterData.value;
            } else if (typeof counterData === 'number') {
                receivedValue = counterData;
            } else if (typeof counterData === 'string') {
                receivedValue = parseInt(counterData);
            }
        }

        if (receivedValue !== undefined && receivedValue !== count) {
            addLog(`📥 Received from backend: ${receivedValue}`, 'success');
            setCount(receivedValue);
        }

        // Логируем структуру для отладки
        if (pluginData && logMessages.length === 0) {
            const counterKeys = Object.keys(pluginData).filter(key => key.includes('counter'));
            if (counterKeys.length > 0) {
                addLog(`🔍 Found counter data in pluginData`, 'info');
                addLog(`🔍 Counter data structure: ${JSON.stringify(counterData)}`, 'debug');
            } else {
                addLog(`⚠️ No 'counter' key in pluginData`, 'warning');
                addLog(`🔍 Available keys: ${Object.keys(pluginData).join(', ')}`, 'debug');
            }
        }
    }, [pluginData]);

    // ОТПРАВКА КОМАНДЫ В ПРАВИЛЬНОМ ФОРМАТЕ ДЛЯ RobotContext
    const handleIncrement = () => {
        // Шлем сразу на три возможных имени, чтобы поймать цель
        sendCommand('counter', 'increment', {});
        sendCommand('CounterPlugin', 'increment', {});
        sendCommand('all', 'increment', {});
    };

    const handleReset = () => {
        addLog(`🔄 Sending 'reset' command...`, 'warning');
        sendCommand('counter', 'reset', {});
    };

    const handleSetValue = (value) => {
        const numValue = parseInt(value);
        if (!isNaN(numValue)) {
            addLog(`⚙️ Sending 'set_value' command with value: ${numValue}`, 'info');
            sendCommand('counter', 'set_value', { value: numValue });
        } else {
            addLog(`❌ Invalid number: ${value}`, 'error');
        }
    };

    // Получение текущего значения
    const handleGetValue = () => {
        addLog(`📤 Requesting current value...`, 'info');
        sendCommand('counter', 'get_value', {});
    };

    // Тестовая команда для проверки пути
    const handleTestPath = () => {
        addLog(`🧪 Testing command path...`, 'info');

        // Отправляем тестовую команду по разным путям
        const testCommands = [
            { target: 'counter', cmd: 'test', args: { test: 'path' } },
            { target: 'broadcast', cmd: 'test', args: { test: 'broadcast' } },
            { target: 'all', cmd: 'test', args: { test: 'all' } }
        ];

        testCommands.forEach((cmd, i) => {
            setTimeout(() => {
                sendCommand(cmd.target, cmd.cmd, cmd.args);
                addLog(`📤 Sent test command ${i+1}: ${cmd.target}.${cmd.cmd}`, 'debug');
            }, i * 500);
        });
    };

    // Очистка логов
    const clearLogs = () => {
        setLogMessages([]);
        addLog('🧹 Logs cleared', 'info');
    };

    // Проверяем подключение WebSocket
    useEffect(() => {
        const checkConnection = () => {
            const ws = document.querySelector('[data-ws-status]');
            if (ws) {
                addLog(`🔌 WebSocket status: ${ws.dataset.wsStatus}`, 'info');
            }
        };

        // Даем время на подключение
        setTimeout(checkConnection, 2000);
    }, []);

    // Создаем кастомный CSS для виджета
    const widgetStyles = {
        container: {
            padding: '20px',
            background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)',
            borderRadius: '12px',
            border: '1px solid #334155',
            color: 'white',
            fontFamily: 'monospace',
            maxWidth: '550px',
            margin: '20px auto',
            boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
            display: 'flex',
            flexDirection: 'column',
            height: '700px',
            overflow: 'hidden'
        },
        header: {
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '15px',
            borderBottom: '1px solid #334155',
            paddingBottom: '10px'
        },
        counterDisplay: {
            fontSize: '5em',
            fontWeight: 'bold',
            color: '#60a5fa',
            textShadow: '0 0 30px rgba(96, 165, 250, 0.5)',
            transition: 'all 0.3s',
            height: '80px',
            textAlign: 'center',
            margin: '20px 0'
        },
        button: (color, disabled = false) => ({
            padding: '12px',
            background: disabled ? '#475569' : color,
            color: 'white',
            border: 'none',
            borderRadius: '8px',
            cursor: disabled ? 'not-allowed' : 'pointer',
            transition: 'all 0.2s',
            fontWeight: 'bold',
            opacity: disabled ? 0.7 : 1
        }),
        logEntry: (type) => ({
            padding: '4px 8px',
            marginBottom: '4px',
            borderRadius: '4px',
            background: type === 'error' ? '#7f1d1d20' :
                      type === 'warning' ? '#854d0e20' :
                      type === 'success' ? '#14532d20' :
                      type === 'debug' ? '#1e3a8a20' : '#1e293b',
            color: type === 'error' ? '#f87171' :
                  type === 'warning' ? '#fbbf24' :
                  type === 'success' ? '#4ade80' :
                  type === 'debug' ? '#93c5fd' : '#cbd5e1',
            borderLeft: `3px solid ${type === 'error' ? '#ef4444' : 
                        type === 'warning' ? '#f59e0b' : 
                        type === 'success' ? '#10b981' : 
                        type === 'debug' ? '#3b82f6' : '#3b82f6'}`
        })
    };

    return (
        <div style={widgetStyles.container}>
            {/* Заголовок */}
            <div style={widgetStyles.header}>
                <h3 style={{ margin: 0, color: '#94a3b8', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span>🧮</span>
                    <span>Counter Widget</span>
                </h3>
                <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                        onClick={handleTestPath}
                        style={{
                            background: '#8b5cf6',
                            color: 'white',
                            border: 'none',
                            padding: '6px 12px',
                            borderRadius: '6px',
                            cursor: 'pointer',
                            fontSize: '0.8em'
                        }}
                    >
                        Test Path
                    </button>
                    <button
                        onClick={clearLogs}
                        style={{
                            background: '#475569',
                            color: 'white',
                            border: 'none',
                            padding: '6px 12px',
                            borderRadius: '6px',
                            cursor: 'pointer',
                            fontSize: '0.8em'
                        }}
                    >
                        Clear Logs
                    </button>
                </div>
            </div>

            {/* Основной счетчик */}
            <div style={{ textAlign: 'center' }}>
                <div style={widgetStyles.counterDisplay}>
                    {loading ? (
                        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '10px' }}>
                            <div className="spinner"></div>
                            <span style={{ fontSize: '0.3em', color: '#94a3b8' }}>Sending...</span>
                        </div>
                    ) : (
                        count
                    )}
                </div>
                <div style={{ color: '#64748b', marginTop: '5px' }}>
                    Current value • Frame: {pluginData?._active_plugins?.length || 0} plugins active
                </div>
            </div>

            {/* Панель управления */}
            <div style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: '10px',
                marginBottom: '20px'
            }}>
                <button
                    onClick={handleIncrement}
                    disabled={loading}
                    style={widgetStyles.button('#3b82f6', loading)}
                >
                    {loading ? 'Sending...' : '➕ Increment (+1)'}
                </button>

                <button
                    onClick={handleReset}
                    style={widgetStyles.button('#dc2626')}
                >
                    🔄 Reset to 0
                </button>

                <button
                    onClick={() => handleSetValue(10)}
                    style={widgetStyles.button('#7c3aed')}
                >
                    ⚡ Set to 10
                </button>

                <button
                    onClick={() => handleSetValue(100)}
                    style={widgetStyles.button('#7c3aed')}
                >
                    ⚡ Set to 100
                </button>
            </div>

            {/* Панель ручного управления */}
            <div style={{ marginBottom: '20px' }}>
                <div style={{ color: '#94a3b8', marginBottom: '8px', fontSize: '0.9em' }}>
                    Manual Input:
                </div>
                <div style={{ display: 'flex', gap: '10px' }}>
                    <input
                        type="number"
                        value={count}
                        onChange={(e) => setCount(e.target.value)}
                        style={{
                            flex: 1,
                            padding: '10px',
                            background: '#0f172a',
                            border: '1px solid #334155',
                            borderRadius: '6px',
                            color: 'white',
                            fontSize: '1em'
                        }}
                    />
                    <button
                        onClick={() => handleSetValue(count)}
                        style={widgetStyles.button('#10b981')}
                    >
                        Set Value
                    </button>
                    <button
                        onClick={handleGetValue}
                        style={widgetStyles.button('#0891b2')}
                    >
                        Refresh
                    </button>
                </div>
            </div>

            {/* Информация о пути команды */}
            <div style={{
                background: '#0f172a',
                borderRadius: '8px',
                padding: '12px',
                marginBottom: '15px',
                fontSize: '0.8em',
                color: '#94a3b8',
                borderLeft: '3px solid #3b82f6'
            }}>
                <div style={{ fontWeight: 'bold', marginBottom: '5px', color: '#cbd5e1' }}>
                    📡 Command Path:
                </div>
                <div style={{ fontSize: '0.75em', lineHeight: '1.5' }}>
                    Frontend → WebSocket → Server → EventBus → Orchestrator → CameraWorker → Processor → Plugin
                </div>
                <div style={{ marginTop: '8px', fontFamily: 'monospace', wordBreak: 'break-all' }}>
                    sendCommand('counter', 'increment', {})
                </div>
            </div>

            {/* Лог панель */}
            <div style={{
                flex: 1,
                background: '#0f172a',
                borderRadius: '8px',
                padding: '15px',
                overflow: 'hidden',
                display: 'flex',
                flexDirection: 'column'
            }}>
                <div style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: '10px',
                    color: '#94a3b8',
                    fontSize: '0.9em'
                }}>
                    <span>📋 Event Log</span>
                    <span>{logMessages.length} messages</span>
                </div>

                <div style={{
                    flex: 1,
                    overflowY: 'auto',
                    background: '#020617',
                    borderRadius: '4px',
                    padding: '10px',
                    fontSize: '0.75em',
                    fontFamily: 'monospace'
                }}>
                    {logMessages.length === 0 ? (
                        <div style={{ color: '#64748b', textAlign: 'center', padding: '20px' }}>
                            <div>No logs yet.</div>
                            <div style={{ marginTop: '10px' }}>Click buttons to send commands...</div>
                        </div>
                    ) : (
                        logMessages.map((log, index) => (
                            <div
                                key={index}
                                style={widgetStyles.logEntry(log.type)}
                            >
                                {log.message}
                            </div>
                        ))
                    )}
                    <div ref={logEndRef} />
                </div>
            </div>

            {/* Статусная строка */}
            <div style={{
                marginTop: '15px',
                padding: '8px 12px',
                background: '#0f172a',
                borderRadius: '6px',
                fontSize: '0.8em',
                color: '#94a3b8',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center'
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div style={{
                        width: '8px',
                        height: '8px',
                        borderRadius: '50%',
                        background: loading ? '#f59e0b' : '#10b981'
                    }}></div>
                    <div>
                        Value: <span style={{ color: '#60a5fa', fontWeight: 'bold' }}>{count}</span>
                    </div>
                </div>
                <div style={{ display: 'flex', gap: '10px' }}>
                    <div>📡 {new Date().toLocaleTimeString()}</div>
                </div>
            </div>
        </div>
    );
};

// Добавим CSS для спиннера
if (!document.querySelector('#counter-widget-styles')) {
    const style = document.createElement('style');
    style.id = 'counter-widget-styles';
    style.textContent = `
        .spinner {
            display: inline-block;
            width: 16px;
            height: 16px;
            border: 2px solid rgba(255,255,255,.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 1s ease-in-out infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        /* Анимация для счетчика при изменении */
        @keyframes pulse {
            0% { transform: scale(1); }
            50% { transform: scale(1.05); }
            100% { transform: scale(1); }
        }
        
        .counter-updated {
            animation: pulse 0.3s ease-in-out;
        }
    `;
    document.head.appendChild(style);
}