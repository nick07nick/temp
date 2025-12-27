import React, { useState, useEffect, useRef } from 'react';
import GridLayout from 'react-grid-layout';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';

// --- STYLES ---
const styles = {
  container: {
    minHeight: '100vh',
    backgroundColor: '#0f172a', // Slate-900
    color: 'white',
    fontFamily: 'system-ui, sans-serif',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  },
  header: {
    padding: '0.75rem 1.5rem',
    borderBottom: '1px solid #1e293b',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#1e293b',
    zIndex: 10,
  },
  title: {
    fontSize: '1.25rem',
    fontWeight: 'bold',
    color: '#38bdf8',
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
  },
  controls: {
    display: 'flex',
    gap: '1rem',
    alignItems: 'center',
  },
  btn: {
    backgroundColor: '#334155',
    color: 'white',
    border: 'none',
    padding: '0.5rem 1rem',
    borderRadius: '0.375rem',
    cursor: 'pointer',
    fontSize: '0.875rem',
    transition: 'background 0.2s',
  },
  btnPrimary: {
    backgroundColor: '#0ea5e9',
    fontWeight: '600',
  },
  select: {
    backgroundColor: '#334155',
    color: 'white',
    padding: '0.5rem',
    borderRadius: '0.375rem',
    border: '1px solid #475569',
  },
  status: {
    fontSize: '0.75rem',
    color: '#94a3b8',
    fontMono: 'monospace',
  },
  card: {
    backgroundColor: '#1e293b',
    borderRadius: '0.5rem',
    overflow: 'hidden',
    border: '1px solid #334155',
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    width: '100%',
  },
  cardHeader: {
    padding: '0.5rem',
    backgroundColor: '#0f172a',
    borderBottom: '1px solid #334155',
    fontSize: '0.75rem',
    fontWeight: 'bold',
    display: 'flex',
    justifyContent: 'space-between',
    cursor: 'grab',
  },
  canvasContainer: {
    flex: 1,
    position: 'relative',
    backgroundColor: '#000',
    minHeight: 0, // Важно для flex контейнера
  },
};

const API_URL = 'http://localhost:8000';
const WS_URL = 'ws://localhost:8000/ws/stream';

// Увеличил высоту блоков по умолчанию, чтобы видео было крупнее
const defaultLayout = [
  { i: 'cam_0', x: 0, y: 0, w: 4, h: 8 },
  { i: 'cam_1', x: 4, y: 0, w: 4, h: 8 },
  { i: 'cam_2', x: 8, y: 0, w: 4, h: 8 },
];

export default function App() {
  const [status, setStatus] = useState('disconnected');
  const [workspaces, setWorkspaces] = useState([]);
  const [activeWorkspace, setActiveWorkspace] = useState('');
  // Инициализируем пустыми массивами, чтобы не было ошибок undefined
  const [frames, setFrames] = useState({ cam_0: [], cam_1: [], cam_2: [] });
  const [fps, setFps] = useState(0);

  const [layout, setLayout] = useState(defaultLayout);
  const lastTimeRef = useRef(Date.now());
  const frameCountRef = useRef(0);
  const wsRef = useRef(null);

  // 1. Инициализация
  useEffect(() => {
    fetch(`${API_URL}/workspaces`)
      .then(res => res.json())
      .then(data => {
        setWorkspaces(data.workspaces || []);
        if (data.workspaces.length > 0) setActiveWorkspace(data.workspaces[0]);
      })
      .catch(console.error);

    const saved = localStorage.getItem('bikefit_layout');
    if (saved) {
      try { setLayout(JSON.parse(saved)); } catch(e) {}
    }
  }, []);

  // 2. WebSocket (Стабильный)
  useEffect(() => {
    function connect() {
      if (wsRef.current?.readyState === WebSocket.OPEN) return;

      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('WS Connected');
        setStatus('connected');
      };

      ws.onclose = () => {
        console.log('WS Disconnected');
        setStatus('disconnected');
        setTimeout(() => connect(), 3000);
      };

      ws.onerror = (err) => {
        console.error('WS Error:', err);
        ws.close();
      };

      ws.onmessage = (event) => {
        try {
          const packet = JSON.parse(event.data);
          if (packet.cameras) {
            setFrames(packet.cameras);
          }

          // Считаем FPS входящего потока
          frameCountRef.current++;
          const now = Date.now();
          if (now - lastTimeRef.current >= 1000) {
            setFps(frameCountRef.current);
            frameCountRef.current = 0;
            lastTimeRef.current = now;
          }
        } catch (e) {}
      };
    }

    connect();
    return () => { if (wsRef.current) wsRef.current.close(); };
  }, []);

  // 3. Хендлеры
  const handleWorkspaceChange = async (e) => {
    const newName = e.target.value;
    setActiveWorkspace(newName);
    fetch(`${API_URL}/workspaces/active`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newName }),
    }).catch(console.error);
  };

  const saveLayout = () => {
    localStorage.setItem('bikefit_layout', JSON.stringify(layout));
    alert('Layout saved!');
  };

  const resetLayout = () => {
    setLayout(defaultLayout);
    localStorage.removeItem('bikefit_layout');
  };

  return (
    <div style={styles.container}>
      <header style={styles.header}>
        <div style={styles.title}>
          <span>BikeFit Pro</span>
          <span style={{fontSize:'0.7em', color:'#64748b', fontWeight:'normal'}}>v0.7 Visual Fix</span>
        </div>

        <div style={styles.controls}>
          <div style={styles.status}>
            WS: <span style={{color: status==='connected'?'#4ade80':'#f87171'}}>{status}</span> | FPS: {fps}
          </div>

          <select style={styles.select} value={activeWorkspace} onChange={handleWorkspaceChange}>
            {workspaces.map(ws => <option key={ws} value={ws}>{ws.replace(/_/g, ' ')}</option>)}
          </select>

          <button style={styles.btn} onClick={resetLayout}>Reset Grid</button>
          <button style={{...styles.btn, ...styles.btnPrimary}} onClick={saveLayout}>Save Grid</button>
        </div>
      </header>

      <div style={{flex: 1, overflow: 'auto', padding: '10px'}}>
        <GridLayout
          className="layout"
          layout={layout}
          cols={12}
          rowHeight={30}
          width={window.innerWidth - 20}
          onLayoutChange={setLayout}
          draggableHandle=".drag-handle"
        >
          <div key="cam_0"><CameraCard id={0} title="Front View" points={frames.cam_0} /></div>
          <div key="cam_1"><CameraCard id={1} title="Side View" points={frames.cam_1} /></div>
          <div key="cam_2"><CameraCard id={2} title="Back View" points={frames.cam_2} /></div>
        </GridLayout>
      </div>
    </div>
  );
}

const CameraCard = ({ id, title, points = [] }) => {
  return (
    <div style={styles.card}>
      <div className="drag-handle" style={styles.cardHeader}>
        <span>{title}</span>
        <span style={{opacity: 0.5}}>CAM {id} • {points.length} pts</span>
      </div>
      <div style={styles.canvasContainer}>
        <AutoResizingCanvas points={points} />
      </div>
    </div>
  );
};

// Канвас с авто-ресайзом и отладкой
const AutoResizingCanvas = ({ points }) => {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    // Observer следит за изменением размера DIV-а (когда тянем грид)
    const resizeObserver = new ResizeObserver(() => {
      const { clientWidth, clientHeight } = container;
      if (clientWidth > 0 && clientHeight > 0) {
        canvas.width = clientWidth;
        canvas.height = clientHeight;
        draw(); // Перерисовываем сразу при ресайзе
      }
    });

    resizeObserver.observe(container);

    const draw = () => {
      const ctx = canvas.getContext('2d');
      const w = canvas.width;
      const h = canvas.height;

      // 1. Очистка (Чистый черный)
      ctx.fillStyle = '#000000';
      ctx.fillRect(0, 0, w, h);

      // (Убрали сетку-перекрестие по просьбе заказчика)

      // 2. Масштабирование
      // Координаты приходят в 1920x1080.
      const scaleX = w / 1920;
      const scaleY = h / 1080;

      // 3. Рисуем точки
      if (points && points.length > 0) {
        points.forEach((p, idx) => {
          const x = p.x * scaleX;
          const y = p.y * scaleY;

          // Рисуем точку крупнее (радиус 8) и ярче
          ctx.beginPath();
          ctx.arc(x, y, 8, 0, Math.PI * 2);
          ctx.fillStyle = '#4ade80'; // Bright Green
          ctx.fill();

          // Обводка
          ctx.lineWidth = 2;
          ctx.strokeStyle = '#ffffff';
          ctx.stroke();

          // Подпись координат рядом с точкой
          ctx.fillStyle = '#fff';
          ctx.font = '12px monospace';
          ctx.fillText(`P${idx}`, x + 12, y - 5);
        });

        // 4. Debug инфо в углу (чтобы точно знать, что данные идут)
        ctx.fillStyle = 'rgba(0, 255, 0, 0.8)';
        ctx.font = '14px monospace';
        ctx.fillText(`DATA: ${Math.round(points[0].x)}, ${Math.round(points[0].y)}`, 10, 20);
      } else {
        // Если точек нет
        ctx.fillStyle = '#333';
        ctx.font = '14px monospace';
        ctx.fillText("NO MARKERS DETECTED", 10, 20);
      }
    };

    // Рисуем при каждом обновлении points
    draw();

    return () => resizeObserver.disconnect();
  }, [points]);

  return (
    <div ref={containerRef} style={{width: '100%', height: '100%'}}>
      <canvas ref={canvasRef} style={{display: 'block'}} />
    </div>
  );
};