import React, { useEffect } from 'react';
import { useRobot } from '../context/RobotContext';

export const CalibrationWidget = ({ data, sendCommand }) => {
    const { status } = useRobot();

    // 1. Распаковка
    const payload = data?.data || {};
    const previewSrc = payload.preview_img || null;

    // Метрики
    const markersCount = payload.markers_on_frame || 0;
    const capturedCount = payload.captured_count || 0;
    const boardAngle = payload.board_angle || 0;
    const lensRms = payload.lens_rms || 0;

    // Статусы
    const hasLens = payload.has_calibration || false;
    const hasWorld = payload.has_world || false;
    const worldScale = payload.world_scale || 0.0;

    // Алгоритмы
    const isTuning = payload.is_tuning || false;
    const isAligning = payload.is_aligning || false;
    const isMaintenance = payload.is_maintenance || false;
    const isPaused = payload.is_paused || false;

    const lockTarget = payload.lock_target || 0;
    const currentBright = payload.current_bright || 0;

    const TARGET = "calibration_tool";

    // 2. Auto-Start
    useEffect(() => {
        if (status === 'connected') {
            if(sendCommand) sendCommand(TARGET, 'wizard_opened', {});
        }
    }, [status, sendCommand]);

    useEffect(() => {
        return () => {
            if(sendCommand) sendCommand(TARGET, 'wizard_closed', {});
        };
    }, [sendCommand]);

    // 3. Обработчики
    const handleCalibrate = () => sendCommand(TARGET, 'calibrate_lens', {});

    const handleReset = () => {
        // eslint-disable-next-line no-restricted-globals
        if(confirm("Сбросить ВСЕ калибровки?")) sendCommand(TARGET, 'reset_data', {});
    };

    const handleAlignWorld = () => sendCommand(TARGET, 'align_world', {});
    const handleAutoTune = () => sendCommand(TARGET, 'toggle_tuning', {});

    // [FIXED] Исправлено имя функции
    const handleMeasure = () => sendCommand(TARGET, 'measure_brightness', {});

    const handleToggleMaintenance = () => sendCommand(TARGET, 'toggle_maintenance', {});
    const handleTogglePause = () => sendCommand(TARGET, 'toggle_pause', {});

    return (
        <div style={styles.container}>
            {/* === SIDEBAR === */}
            <div style={styles.sidebar}>

                {/* PAUSE BUTTON */}
                <button
                    onClick={handleTogglePause}
                    style={isPaused ? styles.btnPlay : styles.btnPause}
                >
                    {isPaused ? "▶ RESUME STREAM" : "⏸ PAUSE PROCESS"}
                </button>

                {/* STATUS */}
                <div style={styles.group}>
                    <div style={styles.label}>SYSTEM STATUS</div>
                    <div style={styles.statRow}>
                        <span>Lens RMS:</span>
                        <span style={{color: hasLens ? '#4ade80' : '#f87171', fontWeight:'bold', fontFamily:'monospace'}}>
                            {hasLens ? lensRms.toFixed(6) : "N/A"}
                        </span>
                    </div>
                    <div style={styles.statRow}>
                        <span>World Scale:</span>
                        <span style={{color: hasWorld ? '#4ade80' : '#94a3b8'}}>
                            {hasWorld ? `${worldScale.toFixed(2)} px/cm` : "N/A"}
                        </span>
                    </div>
                </div>

                {/* METRICS */}
                <div style={styles.group}>
                    <div style={styles.label}>REALTIME METRICS</div>
                    <div style={styles.bigStat}>
                        {typeof boardAngle === 'number' ? boardAngle.toFixed(1) : '0.0'}°
                        <div style={styles.subStat}>Angle</div>
                    </div>
                    <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap: 5, marginTop: 5}}>
                        <div style={styles.boxStat}>
                            <div style={styles.val}>{markersCount}</div>
                            <div style={styles.sub}>Markers</div>
                        </div>
                        <div style={styles.boxStat}>
                            <div style={styles.val}>{capturedCount}</div>
                            <div style={styles.sub}>Captures</div>
                        </div>
                    </div>
                </div>

                {/* AI CONTROL */}
                <div style={styles.group}>
                    <div style={styles.label}>CAMERA AI CONTROL</div>

                    <button
                        onClick={handleAutoTune}
                        style={isTuning ? styles.btnWarn : styles.btnBlue}
                        disabled={isPaused}
                    >
                        {isTuning ? "🛑 STOP TUNING" : "🪄 AUTO TUNE"}
                    </button>

                    <div style={{height: 1, background:'#334155', margin:'8px 0'}}></div>

                    <div style={{fontSize:'0.75em', color:'#94a3b8', marginBottom: 4}}>
                        Brightness: <span style={{color:'white'}}>{lockTarget}</span>
                    </div>
                    <div style={{display:'flex', gap: 5}}>
                        <button onClick={handleMeasure} style={styles.btnSmall} disabled={isPaused} title="Measure Current">🎯 SET</button>
                        <button
                            onClick={handleToggleMaintenance}
                            style={isMaintenance ? styles.btnActive : styles.btn}
                            disabled={isPaused}
                        >
                            {isMaintenance ? "🔒 ON" : "🔓 OFF"}
                        </button>
                    </div>
                    {isMaintenance && (
                        <div style={{fontSize:'0.7em', color:'#4ade80', marginTop:2}}>
                            Current: {currentBright}
                        </div>
                    )}
                </div>

                {/* ACTIONS */}
                <div style={{marginTop: 'auto', display:'flex', flexDirection:'column', gap: 5}}>
                     <button
                        onClick={handleCalibrate}
                        disabled={capturedCount < 10 || isPaused}
                        style={capturedCount < 10 ? styles.btnDisabled : styles.btnPurple}
                    >
                        🧮 CALC LENS
                    </button>
                    <div style={{display:'flex', gap: 5}}>
                         <button
                            onClick={handleAlignWorld}
                            style={isAligning ? styles.btnWarn : styles.btnSuccess}
                            disabled={isPaused}
                         >
                            {isAligning ? "🔍..." : "🌍 ALIGN"}
                         </button>
                         <button onClick={handleReset} style={styles.btnDanger}>🗑️</button>
                    </div>
                </div>

            </div>

            {/* === VIDEO === */}
            <div style={styles.videoArea}>
                {previewSrc && !isPaused ? (
                    <img src={previewSrc} style={styles.img} alt="Preview" />
                ) : (
                    <div style={{color: '#64748b', display:'flex', flexDirection:'column', alignItems:'center'}}>
                        <div style={{fontSize:'2em'}}>{isPaused ? "⏸" : "📷"}</div>
                    </div>
                )}

                {!isPaused && (
                    <div style={styles.overlay}>
                        {isTuning ? "🤖 AI TUNING..." :
                         isAligning ? "🌍 SEARCHING..." :
                         isMaintenance ? "🔒 LOCKED" : "🖐 MANUAL"}
                    </div>
                )}
            </div>
        </div>
    );
};

const styles = {
    container: { display: 'flex', height: '100%', background: '#0f172a', color: '#e2e8f0', overflow: 'hidden' },
    sidebar: { width: '200px', padding: 10, display: 'flex', flexDirection: 'column', gap: 8, borderRight: '1px solid #1e293b', overflowY: 'auto' },
    videoArea: { flex: 1, background: 'black', position: 'relative', display: 'flex', justifyContent: 'center', alignItems: 'center' },
    img: { width: '100%', height: '100%', objectFit: 'contain' },

    group: { background: '#1e293b', padding: 8, borderRadius: 6, border: '1px solid #334155' },
    label: { fontSize: '0.65em', fontWeight: 'bold', color: '#64748b', marginBottom: 6 },

    statRow: { display: 'flex', justifyContent: 'space-between', fontSize: '0.8em', marginBottom: 2 },
    bigStat: { fontSize: '1.5em', fontWeight: 'bold', color: '#facc15', textAlign: 'center', lineHeight: 1 },
    subStat: { fontSize: '0.6em', color: '#94a3b8', textAlign: 'center' },

    boxStat: { background: '#0f172a', padding: 4, borderRadius: 4, textAlign: 'center' },
    val: { fontWeight: 'bold', fontSize: '1em', color: 'white' },
    sub: { fontSize: '0.6em', color: '#64748b' },

    btn: { padding: 8, background: '#334155', color: '#cbd5e1', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize:'0.75em', fontWeight:'bold', width: '100%' },
    btnSmall: { padding: 8, background: '#d97706', color: 'white', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize:'0.75em', fontWeight:'bold', flex: 1 },
    btnActive: { padding: 8, background: '#10b981', color: 'white', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize:'0.75em', fontWeight:'bold', flex: 1 },
    btnBlue: { padding: 8, background: '#3b82f6', color: 'white', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize:'0.75em', fontWeight:'bold', width: '100%' },
    btnWarn: { padding: 8, background: '#ef4444', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontSize:'0.75em', fontWeight:'bold', width: '100%', animation: 'pulse 1s infinite' },
    btnPurple: { padding: 10, background: '#7c3aed', color: 'white', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize:'0.8em', fontWeight:'bold' },
    btnSuccess: { flex: 2, padding: 8, background: '#059669', color: 'white', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize:'0.75em', fontWeight:'bold' },
    btnDanger: { flex: 1, padding: 8, background: '#be123c', color: 'white', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize:'0.75em', fontWeight:'bold' },
    btnDisabled: { padding: 10, background: '#334155', color: '#64748b', border: 'none', borderRadius: '4px', cursor: 'not-allowed', fontSize:'0.8em', fontWeight:'bold' },

    btnPause: { padding: 10, background: '#f59e0b', color: 'black', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize:'0.9em', fontWeight:'bold', width: '100%' },
    btnPlay: { padding: 10, background: '#10b981', color: 'white', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize:'0.9em', fontWeight:'bold', width: '100%' },

    overlay: { position: 'absolute', top: 10, left: 50, transform: 'translateX(-50%)', background: 'rgba(0,0,0,0.6)', padding: '4px 10px', borderRadius: 20, fontSize: '0.7em', color: 'white', border: '1px solid rgba(255,255,255,0.2)' }
};