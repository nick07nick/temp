// frontend/src/App.jsx
import React, { useState, useEffect, useRef } from 'react';
import GridLayout from 'react-grid-layout';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';

import { VideoPlayer } from './components/video/VideoPlayer';
import { TOOLS } from './tools/registry'; // Импортируем реестр инструментов

const styles = {
  container: { minHeight: '100vh', backgroundColor: '#0f172a', color: 'white', fontFamily: 'system-ui, sans-serif', display: 'flex', flexDirection: 'column', overflow: 'hidden' },
  header: { padding: '0.75rem 1.5rem', borderBottom: '1px solid #1e293b', display: 'flex', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#1e293b', zIndex: 10 },
  title: { fontSize: '1.25rem', fontWeight: 'bold', color: '#38bdf8', display: 'flex', alignItems: 'center', gap: '0.5rem' },
  controls: { display: 'flex', gap: '1rem', alignItems: 'center' },
  btn: { backgroundColor: '#334155', color: 'white', border: 'none', padding: '0.5rem 1rem', borderRadius: '0.375rem', cursor: 'pointer', fontSize: '0.875rem', transition: 'background 0.2s' },
  status: { fontSize: '0.75rem', color: '#94a3b8', fontFamily: 'monospace' },
  card: { backgroundColor: '#1e293b', borderRadius: '0.5rem', overflow: 'hidden', border: '1px solid #334155', display: 'flex', flexDirection: 'column', height: '100%', width: '100%', position: 'relative' },
  cardHeader: { padding: '0.5rem', backgroundColor: '#0f172a', borderBottom: '1px solid #334155', fontSize: '0.75rem', fontWeight: 'bold', display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'grab' },
  canvasContainer: { flex: 1, position: 'relative', backgroundColor: '#000', minHeight: 0 },
};

const API_URL = 'http://localhost:8000';
const WS_URL = 'ws://localhost:8000/ws/stream';

const defaultLayout = [
  { i: 'cam_0', x: 0, y: 0, w: 9, h: 10 }, // Камера побольше
  // Можно добавить другие камеры
];

export default function App() {
  const [status, setStatus] = useState('disconnected');
  const [layout, setLayout] = useState(defaultLayout);
  const [isPaused, setIsPaused] = useState(false);
  const [selectedPoint, setSelectedPoint] = useState(null);

  // Храним последние данные плагинов (для отображения в UI сайдбара)
  const [latestPluginData, setLatestPluginData] = useState({});

  const wsRef = useRef(null);
  const framesBuffer = useRef({ cam_0: {}, cam_1: {}, cam_2: {} });

  // === 1. WebSocket Logic ===
  useEffect(() => {
    function connect() {
      if (wsRef.current?.readyState === WebSocket.OPEN) return;
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;
      ws.onopen = () => setStatus('connected');
      ws.onclose = () => { setStatus('disconnected'); setTimeout(() => connect(), 3000); };
      ws.onmessage = (event) => {
        try {
            const packets = JSON.parse(event.data);
            const dataList = Array.isArray(packets) ? packets : [packets];

            dataList.forEach(packet => {
                if (packet.cameras && packet.frame_id) {
                    const fid = packet.frame_id;
                    const pluginsData = packet.plugins || {};

                    // Сохраняем данные для отрисовки видео (синхронизация по кадрам)
                    Object.keys(packet.cameras).forEach(cam => {
                        if (!framesBuffer.current[cam]) framesBuffer.current[cam] = {};
                        framesBuffer.current[cam][fid] = {
                            points: packet.cameras[cam],
                            plugins: pluginsData // Прикрепляем данные плагинов к кадру
                        };
                    });

                    // Сохраняем самые свежие данные плагинов для UI (React State)
                    // Делаем это не каждый кадр, чтобы не убить рендер React, а, скажем, раз в 10 кадров
                    if (fid % 5 === 0) {
                        setLatestPluginData(pluginsData);
                    }
                }
            });

            // Чистка буфера
            const keys = Object.keys(framesBuffer.current.cam_0 || {});
            if (keys.length > 100) {
                 const minKey = Math.min(...keys.map(Number));
                 delete framesBuffer.current.cam_0[minKey];
            }
        } catch (e) { console.error(e); }
      };
    }
    connect();
    return () => { if (wsRef.current) wsRef.current.close(); };
  }, []);

  // === 2. UI Handlers ===
  const handlePointClick = (point, screenX, screenY) => {
      if (point) {
          setSelectedPoint({ point, x: screenX, y: screenY });
      } else {
          setSelectedPoint(null);
      }
  };

  const togglePause = () => {
      setIsPaused(!isPaused);
      if (isPaused) setSelectedPoint(null);
  };

  // Отправка команд плагинам
  const sendPluginCommand = (targetId, cmd, args = {}) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
          const payload = JSON.stringify({
              target: targetId,
              payload: { cmd, args }
          }); // Формат сообщения должен совпадать с тем, что ждет server.py
          wsRef.current.send(payload);
          console.log(`Sent command to ${targetId}:`, cmd);
      }
  };

  return (
    <div style={styles.container}>
      <header style={styles.header}>
        <div style={styles.title}>BikeFit Pro <span style={{fontSize:'0.7em', color:'#64748b'}}>v3.0 Modular</span></div>
        <div style={styles.controls}>
          <div style={styles.status}>Status: <span style={{color: status==='connected'?'#4ade80':'#f87171'}}>{status}</span></div>
          <button style={styles.btn} onClick={togglePause}>{isPaused ? "▶ RESUME" : "⏸ PAUSE"}</button>
          <button style={styles.btn} onClick={() => setLayout(defaultLayout)}>Reset Layout</button>
        </div>
      </header>

      <div style={{flex: 1, display: 'flex', overflow: 'hidden'}}>

        {/* MAIN AREA (Video Grid) */}
        <div style={{flex: 1, overflow: 'auto', padding: '10px'}}>
            <GridLayout className="layout" layout={layout} cols={12} rowHeight={30} width={window.innerWidth - 300} onLayoutChange={setLayout} draggableHandle=".drag-handle">
            <div key="cam_0">
                <CameraCard id={0} title="Front View">
                    <VideoPlayer
                        camId={0}
                        bufferRef={framesBuffer}
                        isPaused={isPaused}
                        onPointClick={handlePointClick}
                    />
                </CameraCard>
            </div>
            </GridLayout>
        </div>

        {/* RIGHT SIDEBAR (Tools UI) */}
        <div style={{
            width: 280,
            backgroundColor: '#1e293b',
            borderLeft: '1px solid #334155',
            display: 'flex',
            flexDirection: 'column',
            zIndex: 20
        }}>
            <div style={{padding: 15, borderBottom: '1px solid #334155', fontWeight: 'bold'}}>
                Active Tools
            </div>
            <div style={{padding: 15, overflowY: 'auto', flex: 1}}>
                {/* Рендерим контролы для каждого плагина из реестра */}
                {Object.values(TOOLS).map(Tool => (
                    <div key={Tool.id} style={{marginBottom: 20}}>
                        {Tool.Controls && (
                            <Tool.Controls
                                // Передаем данные конкретно этого плагина
                                data={latestPluginData[Tool.id] || {}}
                                sendCommand={(cmd, args) => sendPluginCommand(Tool.id, cmd, args)}
                            />
                        )}
                    </div>
                ))}
            </div>
        </div>

      </div>

      {/* Context Menu (Показывается при клике на точку) */}
      {selectedPoint && (
          <div style={{
              position: 'fixed', top: selectedPoint.y + 10, left: selectedPoint.x + 10,
              backgroundColor: '#1e293b', border: '1px solid #475569', padding: '12px',
              borderRadius: '6px', zIndex: 1000, boxShadow: '0 4px 12px rgba(0,0,0,0.5)'
          }}>
              <div style={{fontWeight: 'bold', marginBottom: '8px', color: '#fff'}}>
                  ID: {selectedPoint.point.id}
              </div>
              <button style={{...styles.btn, backgroundColor: '#ef4444', width: '100%'}} onClick={() => setSelectedPoint(null)}>Close</button>
          </div>
      )}
    </div>
  );
}

const CameraCard = ({ id, title, children }) => {
  return (
    <div style={styles.card}>
      <div className="drag-handle" style={styles.cardHeader}>
        <span>{title}</span>
        <span>CAM {id}</span>
      </div>
      <div style={styles.canvasContainer}>
          {children}
      </div>
    </div>
  );
};