// frontend/src/context/RobotContext.jsx
import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import { toast } from 'react-toastify';

const RobotContext = createContext(null);

export const useRobot = () => useContext(RobotContext);

export const RobotProvider = ({ children }) => {
    const [status, setStatus] = useState('disconnected');
    const [widgetsData, setWidgetsData] = useState({});
    // pluginData будет хранить:
    // 1. Глобальные плагины (system_monitor) -> pluginData.system_monitor
    // 2. Данные камер -> pluginData.cam_0, pluginData.cam_1
    const [pluginData, setPluginData] = useState({});

    const [lastOverlayData, setLastOverlayData] = useState({ geometry: {} });

    const framesBuffer = useRef({ cam_0: {}, cam_1: {} });
    const wsRef = useRef(null);
    const processedNotifications = useRef(new Set());

    const WS_URL = 'ws://localhost:8000/ws/stream';

    useEffect(() => {
        const connect = () => {
            if (wsRef.current?.readyState === WebSocket.OPEN) return;
            const ws = new WebSocket(WS_URL);
            wsRef.current = ws;

            ws.onopen = () => setStatus('connected');
            ws.onclose = () => {
                setStatus('disconnected');
                setTimeout(connect, 3000);
            };

            ws.onmessage = (event) => {
                try {
                    const raw = JSON.parse(event.data);
                    const packets = Array.isArray(raw) ? raw : [raw];
                    handlePackets(packets);
                } catch (e) { console.error("WS Error", e); }
            };
        };
        connect();
        return () => wsRef.current?.close();
    }, []);

    const handlePackets = (packets) => {
        packets.forEach(packet => {

            // 1. BROADCAST (Оркестратор -> Фронт)
            if (packet.type === 'plugin_data') {
                const { plugin, data } = packet.payload;
                setPluginData(prev => ({
                    ...prev,
                    [plugin]: data // system_monitor, calibration_widget и т.д.
                }));
                return;
            }

            // 2. STREAM DATA (Воркер -> Фронт)
            if (packet.frame_id !== undefined) {
                const camKey = `cam_${packet.camera_id}`;
                if (!framesBuffer.current[camKey]) framesBuffer.current[camKey] = {};

                // Видео буфер (для плеера)
                framesBuffer.current[camKey][packet.frame_id] = packet;
                const keys = Object.keys(framesBuffer.current[camKey]);
                if (keys.length > 60) delete framesBuffer.current[camKey][Math.min(...keys)];

                // [FIX] Метрики сохраняем ИЗОЛИРОВАННО для каждой камеры
                // Обновляем раз в 10 кадров, чтобы не убить React ре-рендерами
                if (packet.frame_id % 10 === 0 && packet.results) {
                    setPluginData(prev => ({
                        ...prev,
                        [camKey]: { // <--- ВОТ ГЛАВНОЕ ИЗМЕНЕНИЕ
                            ...packet.results,
                            _active_plugins: packet.active_plugins,
                            _camera_config: packet.camera_config
                        }
                    }));
                }
            }

            // 3. Виджеты (для Legacy)
            if (packet.widgets) {
                setWidgetsData(prev => {
                    const next = { ...prev };
                    packet.widgets.forEach(w => next[w.widget_id] = w);
                    return next;
                });
            }

            // 4. Уведомления
            if (packet.notifications) {
                packet.notifications.forEach(n => {
                    if (!processedNotifications.current.has(n.id)) {
                        toast(n.message, { type: n.type, autoClose: n.duration * 1000 });
                        processedNotifications.current.add(n.id);
                        if (processedNotifications.current.size > 100) processedNotifications.current.clear();
                    }
                });
            }
        });
    };

    const sendCommand = (targetId, cmd, args = {}, targetOverride = null) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({
                target: targetOverride || targetId,
                payload: { cmd, args }
            }));
        }
    };

    const updateOverlayData = (data) => setLastOverlayData(data);

    return (
        <RobotContext.Provider value={{
            status,
            framesBuffer,
            widgetsData,
            pluginData,
            sendCommand,
            lastOverlayData,
            updateOverlayData
        }}>
            {children}
        </RobotContext.Provider>
    );
};