// src/context/RobotContext.jsx
import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import { toast } from 'react-toastify';

const RobotContext = createContext(null);

export const useRobot = () => useContext(RobotContext);

export const RobotProvider = ({ children }) => {
    const [status, setStatus] = useState('disconnected');
    const [widgetsData, setWidgetsData] = useState({}); // Данные для графиков/метрик
    const [pluginData, setPluginData] = useState({});   // Данные от плагинов (sidebars)

    // Refs для высокочастотных данных (чтобы не рендерить React 60 раз в сек)
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
            // 1. Видео
            if (packet.frame_id !== undefined) {
                const camKey = `cam_${packet.camera_id}`;
                if (!framesBuffer.current[camKey]) framesBuffer.current[camKey] = {};
                framesBuffer.current[camKey][packet.frame_id] = packet;

                // Прореживание буфера
                const keys = Object.keys(framesBuffer.current[camKey]);
                if (keys.length > 60) delete framesBuffer.current[camKey][Math.min(...keys)];

                // Обновляем данные плагинов редко (раз в 10 кадров), чтобы не грузить UI
                if (packet.frame_id % 10 === 0 && packet.results) {
                    setPluginData(prev => ({ ...prev, ...packet.results, _active_plugins: packet.active_plugins }));
                }
            }

            // 2. Виджеты
            if (packet.widgets) {
                setWidgetsData(prev => {
                    const next = { ...prev };
                    packet.widgets.forEach(w => next[w.widget_id] = w);
                    return next;
                });
            }

            // 3. Уведомления
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
        // ПРОВЕРЯЕМ: cmd не должен равняться targetId
        if (cmd === targetId) {
            console.error(`⚠️ Invalid command: cmd='${cmd}' equals target='${targetId}'`);
            return;
        }

        wsRef.current.send(JSON.stringify({
            target: targetOverride || targetId,
            payload: { cmd, args }  // Всегда используем payload
        }));
    }
};

    return (
        <RobotContext.Provider value={{
            status,
            framesBuffer,
            widgetsData,
            pluginData,
            sendCommand
        }}>
            {children}
        </RobotContext.Provider>
    );
};