// src/widgets/TestMultiCameraWidget.jsx
import React, { useState, useEffect } from 'react';
import { useRobot } from '../context/RobotContext';

const API_URL = 'http://localhost:8000';

export const TestMultiCameraWidget = () => {
    const { pluginData } = useRobot();
    
    // 1. Берем сырые данные монитора
    const monitorData = pluginData?.system_monitor || {};
    const camerasMap = monitorData.cameras || {};
    
    // Получаем ID всех доступных камер
    // Ключи приходят как строки "0", "1" (благодаря фиксу оркестратора)
    const availableIds = Object.keys(camerasMap).sort();

    // Локальный стейт выбора
    const [selectedId, setSelectedId] = useState(availableIds[0] || "0");

    // Данные от нашего тестового плагина (счетчики кадров)
    // pluginData.test_multicam_widget должен содержать данные с полями camera_id
    const widgetData = pluginData?.test_multicam_widget || {};
    
    // Фильтруем данные плагина: берем только те, что от выбранной камеры
    // (Если наш фикс pipeline.py работает, там будет поле camera_id)
    const currentPluginData = widgetData.camera_id == selectedId ? widgetData : { status: "No data from worker" };

    // Авто-выбор при загрузке, если ничего не выбрано
    useEffect(() => {
        if (availableIds.length > 0 && !availableIds.includes(selectedId)) {
            setSelectedId(availableIds[0]);
        }
    }, [availableIds.length]);

    return (
        <div style={{ padding: 20, background: '#111', color: '#eee', fontFamily: 'monospace', border: '2px solid magenta' }}>
            <h3>🕵️ MULTI-CAMERA DEBUGGER</h3>

            {/* Блок 1: Список камер (Проверка Оркестратора) */}
            <div style={{ marginBottom: 20, border: '1px solid #444', padding: 10 }}>
                <div style={{ color: '#aaa', marginBottom: 5 }}>1. ORCHESTRATOR DISCOVERY</div>
                
                {availableIds.length === 0 ? (
                    <div style={{ color: 'red' }}>⚠️ NO CAMERAS FOUND IN SYSTEM_MONITOR</div>
                ) : (
                    <select 
                        value={selectedId} 
                        onChange={(e) => setSelectedId(e.target.value)}
                        style={{ padding: 10, fontSize: '1.2em', width: '100%', background: '#222', color: 'white' }}
                    >
                        {availableIds.map(id => (
                            <option key={id} value={id}>
                                📹 Camera {id} ({camerasMap[id]?.role || 'Unknown'}) [{camerasMap[id]?.status}]
                            </option>
                        ))}
                    </select>
                )}
                <div style={{ fontSize: '0.8em', color: '#666', marginTop: 5 }}>
                    Raw IDs: {JSON.stringify(availableIds)}
                </div>
            </div>

            <div style={{ display: 'flex', gap: 20 }}>
                
                {/* Блок 2: Видеопоток (Проверка Сервера и SHM) */}
                <div style={{ flex: 1, border: '1px solid #444', padding: 10 }}>
                    <div style={{ color: '#aaa', marginBottom: 5 }}>2. API VIDEO STREAM</div>
                    <div style={{ background: 'black', minHeight: 200, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                        {/* Используем простой IMG tag для теста MJPEG */}
                        <img 
                            src={`${API_URL}/video_feed/${selectedId}`} 
                            style={{ maxWidth: '100%', maxHeight: 400, border: '1px solid lime' }}
                            alt="Live Feed"
                        />
                    </div>
                    <div style={{ fontSize: '0.8em', marginTop: 5, color: '#4ade80' }}>
                        Source: {`${API_URL}/video_feed/${selectedId}`}
                    </div>
                </div>

                {/* Блок 3: Данные Воркера (Проверка EventBus и Pipeline) */}
                <div style={{ flex: 1, border: '1px solid #444', padding: 10 }}>
                    <div style={{ color: '#aaa', marginBottom: 5 }}>3. WORKER DATA LOOP</div>
                    
                    <div style={{ marginBottom: 10 }}>
                        <strong>Active ID:</strong> {selectedId}
                    </div>
                    
                    <div style={{ background: '#222', padding: 10, borderRadius: 5 }}>
                        <div>Worker Counter: {currentPluginData.data?.counter || 0}</div>
                        <div>Worker Cam ID: {currentPluginData.data?.worker_cam_id ?? "N/A"}</div>
                        <div>Packet Cam ID: {currentPluginData.camera_id ?? "MISSING"}</div>
                    </div>

                    <div style={{ marginTop: 20, fontSize: '0.7em', color: '#888' }}>
                        <strong>Raw Plugin Data:</strong>
                        <pre>{JSON.stringify(currentPluginData, null, 2)}</pre>
                    </div>
                </div>
            </div>
        </div>
    );
};