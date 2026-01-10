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

        // Карта для линий
        const pointsMap = {};
        pointsToDraw.forEach(p => pointsMap[String(p.id)] = p);

        // 2. Очистка
        this.ctx.fillStyle = '#000000';
        this.ctx.fillRect(0, 0, width, height);

        // 3. Рисуем ВИДЕО
        // Мы растягиваем видео на весь холст.
        // Так как в VideoPlayer мы подгоним размер холста под размер видео, искажений не будет.
        if (videoFrame) {
            this.ctx.drawImage(videoFrame, 0, 0, width, height);
        }

        // 4. Рисуем СВЯЗИ
        if (options.connections) {
            this._drawConnections(options.connections, pointsMap);
        }

        // 5. Рисуем ТОЧКИ
        pointsToDraw.forEach(p => this._drawPoint(p));

        // 6. Ошибки
        if (options.errors && options.errors.length > 0) {
            this._drawErrors(options.errors);
        }
    }

    _drawPoint(p) {
        // Константы для отрисовки (крупные, чтобы было видно на больших разрешениях)
        const radius = 9;
        const lineWidth = 3;
        const fontSize = 28;

        // Точка
        this.ctx.beginPath();
        this.ctx.arc(p.x, p.y, radius, 0, 2 * Math.PI);
        this.ctx.fillStyle = p.color || '#00ff00';
        this.ctx.fill();

        this.ctx.lineWidth = lineWidth;
        this.ctx.strokeStyle = '#000000';
        this.ctx.stroke();

        // Текст
        if (p.label) {
            this.ctx.font = `bold ${fontSize}px monospace`;
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'bottom';

            const labelY = p.y - (radius + 5);

            this.ctx.lineJoin = 'round';
            this.ctx.lineWidth = 6;
            this.ctx.strokeStyle = 'black'; // Обводка
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

    // [FIX] Переименовал в hitTestVirtual, чтобы соответствовать вызову в VideoPlayer
    hitTestVirtual(x, y) {
        let closest = null;
        let minDist = 40; // Радиус поиска

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