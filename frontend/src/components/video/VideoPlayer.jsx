// frontend/src/components/video/VideoPlayer.jsx
import React, { useEffect, useRef, useState } from 'react';
import { BikeFitRenderer } from '../../renderer/BikeFitRenderer';
import { useRobot } from '../../context/RobotContext';
import MarkerContextMenu from './MarkerContextMenu';

const API_URL = 'http://localhost:8000';

export const VideoPlayer = ({
    camId: initialCamId = 0,
    bufferRef,
    isPaused,
    onPointClick,
    enableSwitching = true
}) => {
    const canvasRef = useRef(null);
    const containerRef = useRef(null);
    const rendererRef = useRef(null);
    const lastFrameRef = useRef(null);
    const lastDataRef = useRef(null);

    // === 1. Multi-Camera Logic ===
    const { sendCommand, pluginData } = useRobot();
    const [activeCamId, setActiveCamId] = useState(initialCamId);

    const knownCameras = pluginData?.system_monitor?.cameras || {};
    const cameraIds = Object.keys(knownCameras).length > 0
        ? Object.keys(knownCameras).map(Number).sort((a,b)=>a-b)
        : [0];

    useEffect(() => {
        setActiveCamId(initialCamId);
    }, [initialCamId]);

    // UI States
    const [menu, setMenu] = useState({ visible: false, x: 0, y: 0, point: null });
    const [toolCreation, setToolCreation] = useState({ active: false, type: null, points: [], step: 0 });

    // === 2. Init Renderer ===
    useEffect(() => {
        if (canvasRef.current) {
            canvasRef.current.width = 1920;
            canvasRef.current.height = 1200;
            rendererRef.current = new BikeFitRenderer(canvasRef.current);
        }
        // Cleanup renderer resources if needed
        return () => {
            if (lastFrameRef.current) {
                lastFrameRef.current.close();
                lastFrameRef.current = null;
            }
        };
    }, []);

    // === 3. Stream Loop (Optimized with AbortController) ===
    useEffect(() => {
        let isRunning = true;

        // [FIX] Создаем контроллер для отмены запроса fetch
        const abortController = new AbortController();

        const startStream = async () => {
            // Очистка данных старой камеры из буфера контекста
            if (bufferRef && bufferRef.current) {
                // Чистим ВСЕ старые ключи, чтобы не было смешивания
                Object.keys(bufferRef.current).forEach(k => {
                    if (k !== `cam_${activeCamId}`) delete bufferRef.current[k];
                });
            }

            try {
                // Передаем signal в fetch
                const response = await fetch(`${API_URL}/video_feed/${activeCamId}?t=${Date.now()}`, {
                    signal: abortController.signal
                });

                if (!response.body) throw new Error("No body");

                const reader = response.body.getReader();
                let buffer = new Uint8Array(0);
                let state = 0; // 0=Header, 1=Body
                let requiredBytes = 12;

                while (isRunning) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    const newBuffer = new Uint8Array(buffer.length + value.length);
                    newBuffer.set(buffer);
                    newBuffer.set(value, buffer.length);
                    buffer = newBuffer;

                    while (true) {
                        if (buffer.length < requiredBytes) break;

                        if (state === 0) { // Header
                            const view = new DataView(buffer.buffer, buffer.byteOffset, buffer.byteLength);
                            const jpgSize = view.getUint32(8, true);
                            buffer = buffer.slice(12);
                            state = 1;
                            requiredBytes = jpgSize;
                        } else if (state === 1) { // Body
                            const jpgBytes = buffer.slice(0, requiredBytes);
                            buffer = buffer.slice(requiredBytes);

                            if (!isPaused) {
                                try {
                                    const blob = new Blob([jpgBytes], { type: 'image/jpeg' });
                                    const bitmap = await createImageBitmap(blob);

                                    // Закрываем старый bitmap сразу же
                                    if (lastFrameRef.current) {
                                        lastFrameRef.current.close();
                                    }
                                    lastFrameRef.current = bitmap;

                                    if (canvasRef.current && (canvasRef.current.width !== bitmap.width || canvasRef.current.height !== bitmap.height)) {
                                        canvasRef.current.width = bitmap.width;
                                        canvasRef.current.height = bitmap.height;
                                    }
                                } catch (err) {
                                    // Игнорируем ошибки декодирования одного кадра
                                    // console.warn("Frame decode error", err);
                                }
                            }
                            state = 0;
                            requiredBytes = 12;
                        }
                    }
                }
            } catch (e) {
                if (e.name === 'AbortError') {
                    // Это нормальная ошибка при смене камеры, просто выходим
                    console.log(`⏹️ Stream ${activeCamId} aborted by user.`);
                } else {
                    console.warn(`Stream ${activeCamId} error:`, e);
                    // Retry logic only if not aborted
                    if (isRunning) setTimeout(startStream, 1000);
                }
            }
        };

        startStream();

        return () => {
            isRunning = false;
            // [FIX] Жестко обрываем соединение при размонтировании или смене ID
            abortController.abort();
        };
    }, [activeCamId, isPaused]); // Важно: activeCamId в зависимостях

    // === 4. Render Loop ===
    useEffect(() => {
        let animationId;
        const draw = () => {
            if (rendererRef.current && !isPaused) {
                // Данные
                if (bufferRef && bufferRef.current) {
                    const camKey = `cam_${activeCamId}`;
                    const camData = bufferRef.current[camKey];
                    if (camData) {
                         const keys = Object.keys(camData).sort((a,b) => b-a);
                         // Берем самый свежий кадр данных
                         if (keys.length > 0) lastDataRef.current = camData[keys[0]];
                    }
                }

                const bitmap = lastFrameRef.current;

                // Если битмап закрыт или null - не рисуем
                if (bitmap && bitmap.width > 0) {
                    const sysState = lastDataRef.current || {};
                    const results = sysState.results || {};
                    const points = results.vision?.keypoints || [];
                    const errors = sysState.errors || [];
                    const geometry = results.overlay?.geometry || {};

                    rendererRef.current.draw(bitmap, points, {
                        errors: errors,
                        geometry: geometry
                    });
                }
            }
            animationId = requestAnimationFrame(draw);
        };
        draw();
        return () => cancelAnimationFrame(animationId);
    }, [isPaused, bufferRef, activeCamId]);

    // === 5. Interaction Handlers (Без изменений) ===
    const handleClick = (e) => {
        if (!canvasRef.current || !rendererRef.current) return;
        if (menu.visible) { setMenu({ ...menu, visible: false }); return; }

        const rect = canvasRef.current.getBoundingClientRect();
        const canvasW = canvasRef.current.width;
        const canvasH = canvasRef.current.height;
        const scale = Math.min(rect.width / canvasW, rect.height / canvasH);
        const displayW = canvasW * scale;
        const displayH = canvasH * scale;
        const offsetX = (rect.width - displayW) / 2;
        const offsetY = (rect.height - displayH) / 2;
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        if (mouseX < offsetX || mouseX > offsetX + displayW || mouseY < offsetY || mouseY > offsetY + displayH) return;

        const videoX = (mouseX - offsetX) / scale;
        const videoY = (mouseY - offsetY) / scale;
        const hit = rendererRef.current.hitTestVirtual(videoX, videoY);

        if (toolCreation.active) {
            if (hit && !toolCreation.points.includes(hit.id)) {
                 const newPoints = [...toolCreation.points, hit.id];
                 let isComplete = false;
                 if (toolCreation.type === 'distance' && newPoints.length === 2) isComplete = true;
                 if (toolCreation.type === 'angle' && newPoints.length === 3) isComplete = true;

                 if (isComplete) {
                     finalizeTool(newPoints, toolCreation.type);
                 } else {
                     setToolCreation({...toolCreation, points: newPoints, step: toolCreation.step + 1});
                 }
            }
            return;
        }

        if (hit) {
            setMenu({ visible: true, x: e.clientX, y: e.clientY, point: hit });
        } else if (onPointClick) {
            onPointClick(null, e.clientX, e.clientY);
        }
    };

    const handleMenuAction = (action, pt) => {
        setMenu({ ...menu, visible: false });
        if (action === 'create_angle') setToolCreation({ active: true, type: 'angle', points: [pt.id], step: 1 });
        if (action === 'create_distance') setToolCreation({ active: true, type: 'distance', points: [pt.id], step: 1 });
        if (action === 'delete_tools') sendCommand('geometry_manager', 'cmd_remove_by_point', { point_id: pt.id });
    };

    const finalizeTool = (pts, type) => {
        sendCommand('geometry_manager', 'cmd_add_tool', {
            id: `tool_${Date.now()}`, type, points: pts, color: '#fbbf24'
        });
        setToolCreation({ active: false, type: null, points: [], step: 0 });
    };

    const getInstructionText = () => {
         if (!toolCreation.active) return null;
         if (toolCreation.type === 'distance') return "Выберите вторую точку";
         if (toolCreation.type === 'angle' && toolCreation.step === 1) return "Выберите вершину угла";
         if (toolCreation.type === 'angle' && toolCreation.step === 2) return "Выберите третью точку";
         return "Выберите точку";
    };

    return (
        <div ref={containerRef} style={{ width: '100%', height: '100%', position: 'relative', background: '#050505', overflow: 'hidden' }}>
            {enableSwitching && (
                <div style={{ position: 'absolute', top: 10, right: 10, zIndex: 20 }}>
                    <select
                        value={activeCamId}
                        onChange={(e) => setActiveCamId(Number(e.target.value))}
                        style={{
                            background: 'rgba(0,0,0,0.7)',
                            color: '#e2e8f0',
                            border: '1px solid #475569',
                            borderRadius: 4,
                            padding: '4px 8px',
                            fontSize: '0.8rem',
                            cursor: 'pointer',
                            outline: 'none',
                            backdropFilter: 'blur(4px)'
                        }}
                    >
                        {cameraIds.map(id => (
                            <option key={id} value={id}>
                                CAM {id} {knownCameras[id]?.role ? `(${knownCameras[id].role})` : ''}
                            </option>
                        ))}
                    </select>
                </div>
            )}

            {toolCreation.active && (
                <div style={{ position: 'absolute', top: 20, left: '50%', transform: 'translateX(-50%)', background: 'rgba(0,0,0,0.8)', color: '#4ade80', padding: '8px 16px', borderRadius: '20px', zIndex: 10 }}>
                    🎯 {getInstructionText()} <span style={{fontSize: 12, color: '#888'}}>(Esc отмена)</span>
                </div>
            )}

            <canvas
                ref={canvasRef}
                onClick={handleClick}
                style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
            />

            {menu.visible && (
                <MarkerContextMenu
                    position={{ x: menu.x, y: menu.y }}
                    point={menu.point}
                    onClose={() => setMenu({ ...menu, visible: false })}
                    onAction={handleMenuAction}
                />
            )}
        </div>
    );
};