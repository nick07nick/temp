import React, { useEffect, useRef, useState } from 'react';
import { BikeFitRenderer } from '../../renderer/BikeFitRenderer';
import { useRobot } from '../../context/RobotContext';
import MarkerContextMenu from './MarkerContextMenu';

const API_URL = 'http://localhost:8000';

export const VideoPlayer = ({ camId, bufferRef, isPaused, onPointClick }) => {
    const canvasRef = useRef(null);
    const containerRef = useRef(null);
    const rendererRef = useRef(null);

    const lastFrameRef = useRef(null);
    const lastDataRef = useRef(null);

    const { sendCommand } = useRobot();
    const [menu, setMenu] = useState({ visible: false, x: 0, y: 0, point: null });
    const [toolCreation, setToolCreation] = useState({ active: false, type: null, points: [], step: 0 });

    // 1. Init
    useEffect(() => {
        if (canvasRef.current) {
            // Изначально ставим хоть что-то, но потом подстроимся под видео
            canvasRef.current.width = 1920;
            canvasRef.current.height = 1080;
            rendererRef.current = new BikeFitRenderer(canvasRef.current);
        }
    }, []);

    // 2. Fetch Loop
    useEffect(() => {
        let isRunning = true;
        const startStream = async () => {
            try {
                const response = await fetch(`${API_URL}/video_feed/${camId}`);
                if (!response.body) throw new Error("No body");

                const reader = response.body.getReader();
                let buffer = new Uint8Array(0);
                let state = 0;
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
                                const blob = new Blob([jpgBytes], { type: 'image/jpeg' });
                                createImageBitmap(blob).then(bitmap => {
                                    if (lastFrameRef.current) lastFrameRef.current.close();
                                    lastFrameRef.current = bitmap;

                                    // [FIX] Синхронизация размера холста с реальным размером видео
                                    // Если видео 1280x720, холст станет 1280x720.
                                    // Точки лягут идеально.
                                    if (canvasRef.current && (canvasRef.current.width !== bitmap.width || canvasRef.current.height !== bitmap.height)) {
                                        canvasRef.current.width = bitmap.width;
                                        canvasRef.current.height = bitmap.height;
                                    }
                                }).catch(console.error);
                            }
                            state = 0;
                            requiredBytes = 12;
                        }
                    }
                }
            } catch (e) {
                console.error("Stream error", e);
                if (isRunning) setTimeout(startStream, 2000);
            }
        };
        startStream();
        return () => { isRunning = false; };
    }, [camId, isPaused]);

    // 3. Render Loop
    useEffect(() => {
        let animationId;
        const draw = () => {
            if (rendererRef.current && !isPaused) {
                if (bufferRef && bufferRef.current) {
                    const camKey = `cam_${camId}`;
                    const camData = bufferRef.current[camKey];
                    if (camData) {
                         const keys = Object.keys(camData).sort((a,b) => b-a);
                         if (keys.length > 0) lastDataRef.current = camData[keys[0]];
                    }
                }

                const bitmap = lastFrameRef.current;
                const sysState = lastDataRef.current || {};
                const points = sysState.results?.vision?.keypoints || [];
                const errors = sysState.errors || [];

                rendererRef.current.draw(bitmap, points, { errors: errors });
            }
            animationId = requestAnimationFrame(draw);
        };
        draw();
        return () => cancelAnimationFrame(animationId);
    }, [isPaused, bufferRef, camId]);

    // 4. Click Handler (Исправленный расчет координат для object-fit: contain)
    const handleClick = (e) => {
        if (!canvasRef.current || !rendererRef.current) return;
        if (menu.visible) { setMenu({ ...menu, visible: false }); return; }

        const rect = canvasRef.current.getBoundingClientRect(); // Размер элемента на экране (включая черные полосы)
        const canvasW = canvasRef.current.width; // Реальное разрешение видео (например, 1920)
        const canvasH = canvasRef.current.height; // (например, 1080)

        // Рассчитываем, как именно видео вписано в элемент (Letterboxing)
        const scale = Math.min(rect.width / canvasW, rect.height / canvasH);
        const displayW = canvasW * scale;
        const displayH = canvasH * scale;

        const offsetX = (rect.width - displayW) / 2;
        const offsetY = (rect.height - displayH) / 2;

        // Координаты мыши внутри элемента
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        // Проверяем, кликнули ли мы в видео или в черную полосу
        if (mouseX < offsetX || mouseX > offsetX + displayW || mouseY < offsetY || mouseY > offsetY + displayH) {
            // Клик в черную полосу - игнорируем
            return;
        }

        // Переводим в координаты видео
        const videoX = (mouseX - offsetX) / scale;
        const videoY = (mouseY - offsetY) / scale;

        // [FIX] Вызов правильного метода
        const hit = rendererRef.current.hitTestVirtual(videoX, videoY);

        if (toolCreation.active) {
            if (hit && !toolCreation.points.includes(hit.id)) {
                 const newPoints = [...toolCreation.points, hit.id];
                 if ((toolCreation.type === 'distance' && newPoints.length === 2) || (toolCreation.type === 'angle' && newPoints.length === 3)) {
                     finalizeTool(newPoints, toolCreation.type);
                 } else {
                     setToolCreation({...toolCreation, points: newPoints, step: toolCreation.step + 1});
                 }
            }
            return;
        }

        if (hit) setMenu({ visible: true, x: e.clientX, y: e.clientY, point: hit });
        else if (onPointClick) onPointClick(null, e.clientX, e.clientY);
    };

    const handleSaveMarker = (id, data) => sendCommand('marker_manager', 'cmd_update_marker', { id, data });
    const handleMenuAction = (action, pt) => {
        setMenu({ ...menu, visible: false });
        if (action === 'create_angle') setToolCreation({ active: true, type: 'angle', points: [pt.id], step: 1 });
        if (action === 'create_distance') setToolCreation({ active: true, type: 'distance', points: [pt.id], step: 1 });
    };
    const finalizeTool = (pts, type) => {
        sendCommand('geometry_manager', 'cmd_add_tool', { id: `tool_${Date.now()}`, type, points: pts, color: '#fbbf24' });
        setToolCreation({ active: false, type: null, points: [], step: 0 });
    };
    const getInstructionText = () => {
         if (!toolCreation.active) return null;
         if (toolCreation.type === 'distance') return "Выберите вторую точку";
         return "Выберите следующую точку";
    };

    return (
        <div ref={containerRef} style={{ width: '100%', height: '100%', position: 'relative', background: '#000', overflow: 'hidden' }}>
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
            {menu.visible && <MarkerContextMenu visible={menu.visible} x={menu.x} y={menu.y} point={menu.point} onClose={() => setMenu({ ...menu, visible: false })} onSave={handleSaveMarker} onAction={handleMenuAction} />}
        </div>
    );
};