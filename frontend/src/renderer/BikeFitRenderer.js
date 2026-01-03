export class BikeFitRenderer {
    constructor(canvas) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d', { alpha: false }); // alpha: false для ускорения

        // Внутреннее состояние масштаба (нужно для hitTest)
        this.transform = { scale: 1, offsetX: 0, offsetY: 0 };
    }

    /**
     * Главный метод отрисовки кадра
     * @param {ImageBitmap} videoFrame - кадр видео
     * @param {Array} points - массив точек [{id, x, y, label, ...}]
     * @param {Object} options - настройки (показывать ли скелет, зоны и т.д.)
     */
    draw(videoFrame, points = [], options = {}) {
        const { width, height } = this.canvas;

        // 1. Очистка (на всякий случай, хотя видео перекроет)
        this.ctx.clearRect(0, 0, width, height);

        // 2. Расчет пропорций (Letterboxing)
        // Предполагаем, что исходное видео 1920x1200 (можно передавать в options)
        const vW = videoFrame.width || 1920;
        const vH = videoFrame.height || 1200;

        const scale = Math.min(width / vW, height / vH);
        const drawW = vW * scale;
        const drawH = vH * scale;
        const offsetX = (width - drawW) / 2;
        const offsetY = (height - drawH) / 2;

        // Сохраняем для hitTest
        this.transform = { scale, offsetX, offsetY };

        // 3. Рисуем ВИДЕО
        this.ctx.drawImage(videoFrame, offsetX, offsetY, drawW, drawH);

        // 4. Рисуем ГРАФИКУ поверх
        this.ctx.save();
        // Сдвигаем систему координат, чтобы рисовать точки "как есть"
        this.ctx.translate(offsetX, offsetY);
        this.ctx.scale(scale, scale);

        // Теперь координаты (x, y) точек совпадают с видео!
        this._drawPoints(points);

        if (options.showSkeleton) {
            this._drawSkeleton(points);
        }

        if (options.showAngles) {
            // this._drawAngles(points); // Реализуем позже
        }

        this.ctx.restore();
    }

    _drawPoints(points) {
        for (const p of points) {
            const { x, y, id, label } = p;

            // Точка
            this.ctx.beginPath();
            this.ctx.arc(x, y, 6, 0, Math.PI * 2);
            this.ctx.fillStyle = '#4ade80'; // Зеленый
            this.ctx.fill();

            // Обводка
            this.ctx.lineWidth = 2;
            this.ctx.strokeStyle = '#ffffff';
            this.ctx.stroke();

            // Текст ID (для отладки)
            this.ctx.fillStyle = 'white';
            this.ctx.font = '12px monospace';
            this.ctx.fillText(label || `ID:${id}`, x + 10, y - 5);
        }
    }

    _drawSkeleton(points) {
        // Тут будет логика соединения точек линиями
        // Например: connect(Hip, Knee), connect(Knee, Ankle)
    }

    /**
     * Проверка клика (Hit Test)
     * Преобразует координаты мыши (экранные) в координаты видео
     */
    hitTest(screenX, screenY, points) {
        const { scale, offsetX, offsetY } = this.transform;

        // Переводим клик в систему координат видео
        const videoX = (screenX - offsetX) / scale;
        const videoY = (screenY - offsetY) / scale;
        const hitRadius = 15; // Чуть больше, чем радиус точки, чтобы легче попасть

        for (const p of points) {
            const dx = videoX - p.x;
            const dy = videoY - p.y;
            // Простая проверка расстояния (теорема Пифагора)
            if (Math.sqrt(dx*dx + dy*dy) <= hitRadius) {
                return p; // Вернули найденную точку!
            }
        }
        return null;
    }
}