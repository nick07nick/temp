// frontend/src/components/video/VideoPlayer.jsx
import React, { useEffect, useRef } from 'react';
import { BikeFitRenderer } from '../../renderer/BikeFitRenderer';
import { TOOLS } from '../../tools/registry'; // <--- ИМПОРТ РЕЕСТРА

const API_URL = 'http://localhost:8000';

export const VideoPlayer = ({ camId, bufferRef, isPaused, onPointClick }) => {
    const canvasRef = useRef(null);
    const containerRef = useRef(null);
    const rendererRef = useRef(null);

    // Храним последний кадр (битмап + точки + данные плагинов)
    const lastFrameRef = useRef({ bitmap: null, points: [], plugins: {} });

    useEffect(() => {
        if (canvasRef.current) {
            rendererRef.current = new BikeFitRenderer(canvasRef.current);
        }

        // Авто-ресайз
        const resizeObserver = new ResizeObserver(() => {
            if (containerRef.current && canvasRef.current) {
                canvasRef.current.width = containerRef.current.clientWidth;
                canvasRef.current.height = containerRef.current.clientHeight;

                // Если на паузе - перерисовываем старый кадр при ресайзе
                if (isPaused && lastFrameRef.current.bitmap) {
                    drawScene(
                        lastFrameRef.current.bitmap,
                        lastFrameRef.current.points,
                        lastFrameRef.current.plugins
                    );
                }
            }
        });

        if (containerRef.current) resizeObserver.observe(containerRef.current);
        return () => resizeObserver.disconnect();
    }, [isPaused]);

    // === ГЛАВНАЯ ФУНКЦИЯ ОТРИСОВКИ ===
    const drawScene = (bitmap, points, pluginsData = {}) => {
        if (!rendererRef.current) return;

        // 1. Рисуем видео и точки (База)
        rendererRef.current.draw(bitmap, points);

        // 2. Рисуем ПЛАГИНЫ (Слой дополненной реальности)
        Object.keys(pluginsData).forEach(pluginId => {
            const tool = TOOLS[pluginId];     // Ищем инструмент в реестре по ID
            const data = pluginsData[pluginId]; // Данные для этого инструмента

            // Если инструмент есть и у него есть метод draw
            if (tool && tool.draw) {
                tool.draw(rendererRef.current, data);
            }
        });
    };

    useEffect(() => {
        let isRunning = true;

        const startStream = async () => {
            try {
                const response = await fetch(`${API_URL}/video_feed/${camId}`);
                if (!response.body) return;
                const reader = response.body.getReader();

                let buffer = new Uint8Array(0);
                let state = 0; // 0 = Header, 1 = Body
                let requiredBytes = 12; // Header size
                let currentFrameId = 0;

                while (isRunning) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    const newBuffer = new Uint8Array(buffer.length + value.length);
                    newBuffer.set(buffer);
                    newBuffer.set(value, buffer.length);
                    buffer = newBuffer;

                    while (true) {
                        if (buffer.length < requiredBytes) break;

                        if (state === 0) {
                            // Parse Header
                            const view = new DataView(buffer.buffer, buffer.byteOffset, buffer.byteLength);
                            currentFrameId = Number(view.getBigUint64(0, true));
                            const jpgSize = view.getUint32(8, true);

                            buffer = buffer.slice(12);
                            state = 1;
                            requiredBytes = jpgSize;
                        } else if (state === 1) {
                            // Parse Body (JPEG)
                            const jpgBytes = buffer.slice(0, requiredBytes);
                            buffer = buffer.slice(requiredBytes);

                            if (!isPaused) {
                                const blob = new Blob([jpgBytes], { type: 'image/jpeg' });
                                const bitmap = await createImageBitmap(blob);

                                // Достаем данные из буфера (точки + плагины)
                                const camKey = `cam_${camId}`;
                                let framePoints = [];
                                let framePlugins = {};

                                if (bufferRef.current[camKey] && bufferRef.current[camKey][currentFrameId]) {
                                    const frameData = bufferRef.current[camKey][currentFrameId];
                                    framePoints = frameData.points || [];
                                    framePlugins = frameData.plugins || {}; // <--- ВОТ ТУТ МЫ БЕРЕМ ДАННЫЕ ПЛАГИНОВ
                                }

                                drawScene(bitmap, framePoints, framePlugins);

                                if (lastFrameRef.current.bitmap) lastFrameRef.current.bitmap.close();
                                lastFrameRef.current = { bitmap, points: framePoints, plugins: framePlugins };
                            } else {
                                // Если пауза, просто игнорим кадры
                            }

                            state = 0;
                            requiredBytes = 12;
                        }
                    }
                }
            } catch (e) { console.log(e); }
        };

        startStream();
        return () => { isRunning = false; };
    }, [camId, bufferRef, isPaused]);

    const handleClick = (e) => {
        if (!isPaused || !onPointClick || !rendererRef.current) return;
        const rect = canvasRef.current.getBoundingClientRect();
        // Используем старые точки для хит-теста
        const hitPoint = rendererRef.current.hitTest(e.clientX - rect.left, e.clientY - rect.top, lastFrameRef.current.points);
        onPointClick(hitPoint ? hitPoint : null, e.clientX, e.clientY);
    };

    return (
        <div ref={containerRef} style={{ width: '100%', height: '100%', position: 'relative', overflow: 'hidden' }}>
            <canvas
                ref={canvasRef}
                onClick={handleClick}
                // БЫЛО: cursor: isPaused ? 'default' : 'none'
                // СТАЛО: Всегда показываем курсор (например, прицел или обычный)
                style={{ display: 'block', cursor: 'crosshair' }}
            />
        </div>
    );
};