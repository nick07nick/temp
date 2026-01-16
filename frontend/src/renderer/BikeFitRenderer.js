// frontend/src/renderer/BikeFitRenderer.js

export class BikeFitRenderer {
    constructor(canvas) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d', { alpha: false });
        this.lastPoints = [];
    }

    draw(videoFrame, pointsInput = [], options = {}) {
        const { width, height } = this.canvas;

        // 1. Подготовка точек
        let pointsToDraw = [];
        if (Array.isArray(pointsInput)) {
            pointsToDraw = pointsInput;
        } else if (typeof pointsInput === 'object' && pointsInput !== null) {
            pointsToDraw = Object.entries(pointsInput).map(([key, val]) => ({
                ...val, id: key, label: val.label || key
            }));
        }

        this.lastPoints = pointsToDraw;

        // Карта для линий и геометрии
        const pointsMap = {};
        pointsToDraw.forEach(p => pointsMap[String(p.id)] = p);

        // 2. Очистка
        this.ctx.fillStyle = '#000000';
        this.ctx.fillRect(0, 0, width, height);

        // 3. Рисуем ВИДЕО
        if (videoFrame) {
            this.ctx.drawImage(videoFrame, 0, 0, width, height);
        }

        // 4. Рисуем СВЯЗИ (скелет)
        if (options.connections) {
            this._drawConnections(options.connections, pointsMap);
        }

        // 🆕 5. Рисуем ГЕОМЕТРИЮ (Инструменты: углы, линейки)
        if (options.geometry) {
            this._drawGeometry(options.geometry, pointsMap);
        }

        // 6. Рисуем ТОЧКИ
        pointsToDraw.forEach(p => this._drawPoint(p));

        // 7. Ошибки
        if (options.errors && options.errors.length > 0) {
            this._drawErrors(options.errors);
        }
    }

    // ... (Методы _drawPoint, _drawConnections, _drawErrors оставляем без изменений) ...

    _drawPoint(p) {
        const radius = 9;
        const lineWidth = 3;
        const fontSize = 28;

        this.ctx.beginPath();
        this.ctx.arc(p.x, p.y, radius, 0, 2 * Math.PI);
        this.ctx.fillStyle = p.color || '#00ff00';
        this.ctx.fill();

        this.ctx.lineWidth = lineWidth;
        this.ctx.strokeStyle = '#000000';
        this.ctx.stroke();

        if (p.label) {
            this.ctx.font = `bold ${fontSize}px monospace`;
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'bottom';
            const labelY = p.y - (radius + 5);
            this.ctx.lineJoin = 'round';
            this.ctx.lineWidth = 6;
            this.ctx.strokeStyle = 'black';
            this.ctx.strokeText(p.label, p.x, labelY);
            this.ctx.fillStyle = 'white';
            this.ctx.fillText(p.label, p.x, labelY);
        }
    }

    _drawConnections(connections, pointsMap) {
        this.ctx.beginPath();
        this.ctx.strokeStyle = 'rgba(0, 255, 0, 0.6)';
        this.ctx.lineWidth = 4;

        connections.forEach(([id1, id2]) => {
            const p1 = pointsMap[id1];
            const p2 = pointsMap[id2];
            if (p1 && p2) {
                this.ctx.moveTo(p1.x, p1.y);
                this.ctx.lineTo(p2.x, p2.y);
            }
        });
        this.ctx.stroke();
    }

    _drawErrors(errors) {
        this.ctx.save();
        let y = 40;
        this.ctx.font = 'bold 24px sans-serif';
        this.ctx.textAlign = 'left';
        this.ctx.textBaseline = 'top';

        errors.forEach(err => {
            const text = `⚠️ ${err.source}: ${err.message}`;
            const metrics = this.ctx.measureText(text);
            const bgWidth = metrics.width + 40;

            this.ctx.fillStyle = 'rgba(220, 38, 38, 0.9)';
            this.ctx.fillRect(20, y, bgWidth, 36);

            this.ctx.fillStyle = 'white';
            this.ctx.fillText(text, 40, y + 8);
            y += 45;
        });
        this.ctx.restore();
    }

    // 🆕 Новый метод для отрисовки инструментов
    _drawGeometry(tools, pointsMap) {
        this.ctx.save();
        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'middle';
        this.ctx.font = 'bold 24px monospace'; // Крупный шрифт для читаемости

        Object.values(tools).forEach(tool => {
            // Находим реальные координаты точек по их ID
            const pts = tool.points.map(id => pointsMap[id]).filter(Boolean);

            // Если какие-то точки не найдены (например, закрыты телом), не рисуем инструмент
            if (pts.length !== tool.points.length) return;

            const color = tool.color || '#facc15';
            this.ctx.strokeStyle = color;
            this.ctx.fillStyle = color;
            this.ctx.lineWidth = 3;

            // --- Дистанция (2 точки) ---
            if (tool.type === 'distance' && pts.length === 2) {
                const [p1, p2] = pts;

                // Линия
                this.ctx.beginPath();
                this.ctx.moveTo(p1.x, p1.y);
                this.ctx.lineTo(p2.x, p2.y);
                this.ctx.stroke();

                // Текст по центру
                const midX = (p1.x + p2.x) / 2;
                const midY = (p1.y + p2.y) / 2;

                // Значение с округлением. Если придет из калибровки в мм, будет логично.
                // Пока считаем, что это пиксели, но бэк может слать что угодно.
                const text = tool.current ? tool.current.toFixed(0) : "0";

                // Подложка под текст для контраста
                const metrics = this.ctx.measureText(text);
                this.ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
                this.ctx.fillRect(midX - metrics.width / 2 - 6, midY - 14, metrics.width + 12, 28);

                this.ctx.fillStyle = color;
                this.ctx.fillText(text, midX, midY);
            }

            // --- Угол (3 точки: A -> Vertex -> C) ---
            else if (tool.type === 'angle' && pts.length === 3) {
                const [p1, vertex, p2] = pts;

                // Линии к вершине
                this.ctx.beginPath();
                this.ctx.moveTo(p1.x, p1.y);
                this.ctx.lineTo(vertex.x, vertex.y);
                this.ctx.lineTo(p2.x, p2.y);
                this.ctx.stroke();

                // Текст возле вершины (чуть выше)
                const text = tool.current ? `${tool.current.toFixed(1)}°` : "0°";

                const labelY = vertex.y - 35; // Отступ вверх

                const metrics = this.ctx.measureText(text);
                this.ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
                this.ctx.fillRect(vertex.x - metrics.width / 2 - 6, labelY - 14, metrics.width + 12, 28);

                this.ctx.fillStyle = color;
                this.ctx.fillText(text, vertex.x, labelY);
            }
        });

        this.ctx.restore();
    }

    hitTestVirtual(x, y) {
        let closest = null;
        let minDist = 40;

        for (const p of this.lastPoints) {
            const dx = p.x - x;
            const dy = p.y - y;
            const dist = Math.sqrt(dx*dx + dy*dy);

            if (dist < minDist) {
                minDist = dist;
                closest = p;
            }
        }
        return closest;
    }
}