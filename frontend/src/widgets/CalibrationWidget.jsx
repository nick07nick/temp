// frontend/src/widgets/CalibrationWidget.jsx
import React, { useEffect, useRef, useState, useMemo } from 'react';
import { useRobot } from '../context/RobotContext';

export const CalibrationWidget = ({ data, sendCommand }) => {
    const { status } = useRobot();
    const videoContainerRef = useRef(null);
    const heatmapCanvasRef = useRef(null);

    // 1. Data Parsing
    const payload = data?.data || {};
    const previewSrc = payload.preview_img || null;

    // Session
    const sessionName = payload.session_name || "Loading...";
    const sessionList = payload.session_list || [];
    const heatmap = payload.heatmap || [];
    const framesStats = payload.frames_stats || {}; // {id: error | null}
    const capturedCount = payload.session_count || 0;

    const isAutoCapture = payload.is_autocapture || false;
    const minMarkersVal = payload.min_markers || 20;

    // Statuses
    const isTuning = payload.is_tuning || false;
    const isAligning = payload.is_aligning || false;
    const isMaintenance = payload.is_maintenance || false;
    const isPaused = payload.is_paused || false;

    const markersCount = payload.markers_on_frame || 0;
    const lockTarget = payload.lock_target || 0;
    const currentBright = payload.current_bright || 0;
    const worldScale = payload.world_scale || 0.0;
    const lensRms = payload.lens_rms || 0.0;
    const alignError = payload.align_error || 0.0;
    const showGridStatus = payload.show_grid || false;
    const [viewMode, setViewMode] = useState('session');
    const [showHeatmap, setShowHeatmap] = useState(true);
    const [newSessionName, setNewSessionName] = useState('');
    const [minMarkersInput, setMinMarkersInput] = useState(20);
    const isMounted = useRef(false);
    const TARGET = "calibration_tool";

    // 2. Lifecycle

    useEffect(() => {
        // Логика ПРИ МОНТИРОВАНИИ (один раз)
        // Проверяем, что робот подключен и мы еще не инициализировали виджет
        if (status === 'connected' && !isMounted.current) {
            console.log("🟢 Calibration Widget Mounted -> Sending OPEN");
            if (sendCommand) sendCommand(TARGET, 'wizard_opened', {});
            isMounted.current = true;
        }

        // Логика ПРИ РАЗМОНТИРОВАНИИ (один раз)
        return () => {
            if (isMounted.current) {
                console.log("🔴 Calibration Widget Unmounted -> Sending CLOSE");
                if (sendCommand) sendCommand(TARGET, 'wizard_closed', {});
                isMounted.current = false;
            }
        };
        // Убираем зависимости, чтобы эффект сработал строго на Mount/Unmount
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [status]);

    // 3. Heatmap
    useEffect(() => {
        const container = videoContainerRef.current;
        const canvas = heatmapCanvasRef.current;

        if (container && canvas && previewSrc) {
            const renderHeatmap = () => {
                const videoRatio = 16 / 9;
                const containerRatio = container.clientWidth / container.clientHeight;

                let drawW, drawH, offX, offY;

                if (containerRatio > videoRatio) {
                    drawH = container.clientHeight;
                    drawW = drawH * videoRatio;
                    offY = 0;
                    offX = (container.clientWidth - drawW) / 2;
                } else {
                    drawW = container.clientWidth;
                    drawH = drawW / videoRatio;
                    offX = 0;
                    offY = (container.clientHeight - drawH) / 2;
                }

                canvas.width = drawW;
                canvas.height = drawH;
                canvas.style.left = `${offX}px`;
                canvas.style.top = `${offY}px`;
                canvas.style.width = `${drawW}px`;
                canvas.style.height = `${drawH}px`;

                if (heatmap.length > 0 && showHeatmap) {
                    const ctx = canvas.getContext('2d');
                    const rows = heatmap.length;
                    const cols = heatmap[0].length;
                    const cellW = drawW / cols;
                    const cellH = drawH / rows;

                    ctx.clearRect(0, 0, drawW, drawH);

                    for (let r = 0; r < rows; r++) {
                        for (let c = 0; c < cols; c++) {
                            const val = heatmap[r][c];
                            if (val > 0) {
                                let color = `rgba(220, 38, 38, 0.4)`;
                                if (val > 80) color = `rgba(34, 197, 94, 0.4)`;
                                else if (val > 40) color = `rgba(234, 179, 8, 0.4)`;

                                ctx.fillStyle = color;
                                ctx.fillRect(c * cellW, r * cellH, cellW, cellH);
                                ctx.strokeStyle = 'rgba(255,255,255,0.1)';
                                ctx.strokeRect(c * cellW, r * cellH, cellW, cellH);
                            }
                        }
                    }
                }
            };

            const resizeObserver = new ResizeObserver(() => renderHeatmap());
            resizeObserver.observe(container);
            renderHeatmap();
            return () => resizeObserver.disconnect();
        }
    }, [heatmap, showHeatmap, previewSrc]);
    // 4. Handlers
    const handleCreateSession = () => {
        if (!newSessionName) return;
        sendCommand(TARGET, 'create_session', { name: newSessionName });
        setViewMode('session');
        setNewSessionName('');
    };

    const handleLoadSession = (name) => {
        sendCommand(TARGET, 'load_session', { name });
        setViewMode('session');
    };

    const handleToggleAutoCapture = () => {
        sendCommand(TARGET, 'set_autocapture', {
            active: !isAutoCapture,
            min_markers: minMarkersInput
        });
    };

    const handleCompute = () => sendCommand(TARGET, 'compute_calibration', {});
    const handleToggleFrame = (fid) => sendCommand(TARGET, 'toggle_frame', { frame_id: fid });

    const handleAutoTune = () => sendCommand(TARGET, 'toggle_tuning', {});
    const handleMeasure = () => sendCommand(TARGET, 'measure_brightness', {});
    const handleToggleMaint = () => sendCommand(TARGET, 'toggle_maintenance', {});
    const handleAlignWorld = () => sendCommand(TARGET, 'align_world', {});
    const handleTogglePause = () => sendCommand(TARGET, 'toggle_pause', {});
    const handleApplyCalibration = () => sendCommand(TARGET, 'apply_calibration', {});
    const handleResetSession = () => sendCommand(TARGET, 'reset_session', {});
    const handleToggleGrid = (e) => {
        sendCommand(TARGET, 'set_grid_visible', { visible: e.target.checked });
    };




    const sortedFrames = useMemo(() => {
        return Object.entries(framesStats).sort(([, a], [, b]) => {
            // Treat null (pending) as -1 for sorting
            const valA = a === null ? -1 : a;
            const valB = b === null ? -1 : b;
            return valB - valA;
        });
    }, [framesStats]);

    return (
        <div style={styles.container}>
            <div style={styles.sidebar}>
                {/* HEADER */}
                <div style={styles.group}>
                    {viewMode === 'session' ? (
                        <>
                            <button onClick={() => setViewMode('list')} style={styles.btnSmall}>
                                ⬅ SESSION LIST
                            </button>
                            <div style={{display: 'flex', gap: 5, marginTop: 10}}>
                                {/* NEW BUTTON */}
                                <button
                                    onClick={() => sendCommand(TARGET, 'apply_calibration', {})}
                                    style={styles.btnSuccess}
                                    title="Apply to System"
                                >
                                    ✅ APPLY TO SYSTEM
                                </button>
                            </div>
                            <div style={{
                                marginTop: 8,
                                fontSize: '0.8em',
                                color: '#4ade80',
                                fontWeight: 'bold',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis'
                            }}>
                                📂 {sessionName}
                            </div>
                            <div style={styles.statRow}>
                                <span>RMS:</span>
                                <span style={{
                                    color: lensRms > 0 && lensRms < 1.0 ? '#4ade80' : '#f87171',
                                    fontWeight: 'bold'
                                }}>
                                    {lensRms > 0 ? lensRms.toFixed(4) : "--"}
                                </span>
                            </div>


                        </>
                    ) : (
                        <div style={{display: 'flex', flexDirection: 'column', gap: 5}}>
                            <div style={styles.label}>NEW SESSION</div>
                            <input
                                style={styles.input}
                                placeholder="Name..."
                                value={newSessionName}
                                onChange={(e) => setNewSessionName(e.target.value)}
                            />
                            <button onClick={handleCreateSession} style={styles.btnSuccess}>CREATE</button>
                        </div>


                    )}


                </div>

                {viewMode === 'session' && (
                    <>
                        {/* CAPTURE */}
                        <div style={styles.group}>
                            <div style={styles.label}>CAPTURE</div>
                            <div style={{display: 'flex', gap: 5}}>
                                <button onClick={() => sendCommand(TARGET, 'capture_frame', {})} style={styles.btnBlue}
                                        disabled={isPaused}>
                                    📸 SNAP
                                </button>
                                <button onClick={handleToggleAutoCapture}
                                        style={isAutoCapture ? styles.btnWarn : styles.btn} disabled={isPaused}>
                                    {isAutoCapture ? "STOP AUTO" : "AUTO REC"}
                                </button>
                            </div>


                            <div style={{display:'flex', alignItems:'center', gap:5, marginTop:5, fontSize:'0.75em', color:'#94a3b8'}}>
                                <span>Min Markers:</span>
                                <input
                                    type="number"
                                    style={{...styles.input, width: 40}}
                                    value={minMarkersInput}
                                    onChange={(e) => setMinMarkersInput(Number(e.target.value))}
                                />
                                <span>(Vis: {markersCount})</span>
                            </div>

                            <div style={{marginTop:5, display:'flex', alignItems:'center', gap:5}}>
                                <input type="checkbox" checked={showHeatmap} onChange={(e) => setShowHeatmap(e.target.checked)} />
                                <span style={{fontSize:'0.75em'}}>Show Heatmap</span>
                            </div>
                        </div>

                        {/* ADVANCED */}
                        <div style={styles.group}>
                            <div style={styles.label}>CAM & WORLD</div>
                            <div style={styles.row}>
                                <span style={{fontSize: '0.7em', color: '#94a3b8'}}>Bright (Cur/Lock):</span>
                                <span style={{
                                    fontSize: '0.7em',
                                    fontWeight: 'bold'
                                }}>{currentBright} / {lockTarget}</span>
                            </div>
                            <div style={{display: 'flex', gap: 5, marginBottom: 5}}>
                                <button onClick={handleAutoTune} style={isTuning ? styles.btnWarn : styles.btn}
                                        title="Auto Exposure" disabled={isPaused}>
                                    {isTuning ? "STOP" : "TUNE"}
                                </button>
                                <button onClick={handleMeasure} style={styles.btn} title="Set Target"
                                        disabled={isPaused}>SET
                                </button>
                                <button onClick={handleToggleMaint}
                                        style={isMaintenance ? styles.btnActive : styles.btn} title="Lock Settings"
                                        disabled={isPaused}>
                                    {isMaintenance ? "LOCK" : "UNLOCK"}
                                </button>
                            </div>
                            <div style={styles.row}>
                                <span style={{fontSize: '0.7em', color: '#94a3b8'}}>Scale:</span>
                                <span style={{
                                    fontSize: '0.7em',
                                    fontWeight: 'bold',
                                    color: worldScale > 0 ? '#4ade80' : '#ccc'
                                }}>
                                    {worldScale > 0 ? `${worldScale.toFixed(2)} px/cm` : "N/A"}
                                </span>
                            </div>
                            <div style={{marginTop: 8, display: 'flex', alignItems: 'center', gap: 5}}>
                                <input
                                    type="checkbox"
                                    checked={showGridStatus}
                                    onChange={handleToggleGrid}
                                />
                                <span style={{fontSize: '0.75em', color: '#4ade80'}}>Show World Grid</span>
                            </div>
                            <button onClick={handleAlignWorld} style={isAligning ? styles.btnWarn : styles.btnSuccess}
                                    disabled={isPaused}>
                                {isAligning ? "STOP ALIGN" : "🌍 ALIGN WORLD"}
                            </button>
                        </div>

                        {/* FRAMES */}
                        <div style={{
                            ...styles.group,
                            flex: 1,
                            overflow: 'hidden',
                            display: 'flex',
                            flexDirection: 'column'
                        }}>
                            <div style={styles.label}>
                                FRAMES ({capturedCount})
                                <button onClick={handleCompute} style={{
                                    ...styles.btnPurple,
                                    float: 'right',
                                    padding: '2px 6px',
                                    fontSize: '0.9em'
                                }}>CALC</button>
                            </div>
                            <div style={{overflowY:'auto', flex:1, paddingRight:2}}>
                                {sortedFrames.map(([fid, err]) => (
                                    <div key={fid} style={styles.frameItem}>
                                        <div style={{fontSize:'0.7em', color:'#ccc'}} title={fid}>
                                            ..{fid.split('_')[1].slice(-4)}
                                        </div>
                                        <div style={{fontSize:'0.7em', fontWeight:'bold',
                                            color: err === null ? '#facc15' : (err > 1.0 ? '#f87171' : '#4ade80')
                                        }}>
                                            {err === null ? "PENDING" : err.toFixed(2)}
                                        </div>
                                        <button onClick={() => handleToggleFrame(fid)} style={styles.btnTiny}>❌</button>
                                    </div>
                                ))}
                            </div>
                        </div>

                        <button onClick={handleTogglePause} style={{marginTop:5, ...isPaused ? styles.btnPlay : styles.btnPause}}>
                            {isPaused ? "▶ RESUME" : "⏸ PAUSE"}
                        </button>
                    </>
                )}

                {viewMode === 'list' && (
                    <div style={{...styles.group, flex:1, overflowY:'auto'}}>
                        <div style={styles.label}>SAVED SESSIONS</div>
                        {sessionList.map(sess => (
                            <button
                                key={sess.id}
                                onClick={() => handleLoadSession(sess.name)}
                                style={styles.sessionItem}
                            >
                                <div>📁 {sess.name}</div>
                                <div style={{fontSize:'0.75em', color:'#94a3b8'}}>
                                    RMS: <span style={{color: sess.rms > 0 && sess.rms < 1 ? '#4ade80' : '#f87171'}}>{sess.rms.toFixed(3)}</span> | Frames: {sess.count}
                                </div>
                            </button>
                        ))}
                    </div>
                )}

            </div>


            {/* VIDEO */}
            <div style={styles.videoArea} ref={videoContainerRef}>
                {previewSrc && !isPaused ? (
                    <img src={previewSrc} style={styles.img} alt="Preview" />
                ) : (
                    <div style={{color:'#64748b', fontSize:'1.5em'}}>{isPaused ? "⏸ PAUSED" : "NO SIGNAL"}</div>
                )}

                {!isPaused && <canvas ref={heatmapCanvasRef} style={styles.overlayCanvas} />}

                <div style={{position:'absolute', top:10, left:10, display:'flex', gap:5}}>
                    {isAutoCapture && <div style={styles.badgeWarn}>🔴 REC</div>}
                    {isTuning && <div style={styles.badgeInfo}>🤖 TUNING</div>}
                </div>
            </div>
        </div>
    );
};

const styles = {
    container: { display: 'flex', height: '100%', background: '#0f172a', color: '#e2e8f0', overflow: 'hidden' },
    sidebar: { width: '240px', padding: 10, display: 'flex', flexDirection: 'column', gap: 8, borderRight: '1px solid #1e293b', background: '#0f172a' },
    videoArea: { flex: 1, background: 'black', position: 'relative', display: 'flex', justifyContent: 'center', alignItems: 'center', overflow:'hidden' },

    img: { width: '100%', height: '100%', objectFit: 'contain', display: 'block' },
    overlayCanvas: { position: 'absolute', pointerEvents: 'none' },

    group: { background: '#1e293b', padding: 8, borderRadius: 6, border: '1px solid #334155' },
    label: { fontSize: '0.65em', fontWeight: 'bold', color: '#64748b', marginBottom: 6, textTransform:'uppercase' },
    row: { display: 'flex', justifyContent: 'space-between', alignItems:'center', marginBottom: 4 },
    statRow: { display: 'flex', justifyContent: 'space-between', fontSize: '0.8em', marginBottom: 3 },

    input: { background: '#0f172a', border: '1px solid #334155', color: 'white', padding: '2px 4px', borderRadius: 4, fontSize:'0.8em' },

    btn: { padding: 6, background: '#334155', color: '#cbd5e1', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize:'0.7em', fontWeight:'bold', flex:1 },
    btnSmall: { padding: 6, background: '#475569', color: 'white', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize:'0.7em', width:'100%' },
    btnSuccess: { padding: 8, background: '#059669', color: 'white', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize:'0.8em', fontWeight:'bold', width:'100%' },
    btnBlue: { padding: 8, background: '#3b82f6', color: 'white', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize:'0.8em', fontWeight:'bold', flex:1 },
    btnWarn: { padding: 8, background: '#ef4444', color: 'white', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize:'0.8em', fontWeight:'bold', flex:1, animation: 'pulse 1s infinite' },
    btnPurple: { background: '#7c3aed', color: 'white', border: 'none', borderRadius: 4, cursor: 'pointer', fontWeight:'bold' },
    btnTiny: { padding: '2px 5px', background: 'transparent', color:'#ef4444', border:'1px solid #ef4444', borderRadius:4, cursor:'pointer', fontSize:'0.7em' },
    btnActive: { padding: 6, background: '#10b981', color: 'white', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize:'0.7em', fontWeight:'bold', flex:1 },

    btnPause: { padding: 10, background: '#f59e0b', color: 'black', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize:'0.8em', fontWeight:'bold', width: '100%' },
    btnPlay: { padding: 10, background: '#10b981', color: 'white', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize:'0.8em', fontWeight:'bold', width: '100%' },

    frameItem: { display:'flex', alignItems:'center', justifyContent:'space-between', padding:'4px 0', borderBottom:'1px solid #334155' },
    sessionItem: { width:'100%', textAlign:'left', padding: 8, background:'transparent', borderBottom:'1px solid #334155', color:'#cbd5e1', cursor:'pointer', display:'flex', flexDirection:'column', gap:2 },

    badgeWarn: { background: '#ef4444', color:'white', padding:'2px 6px', borderRadius:4, fontSize:'0.7em', fontWeight:'bold' },
    badgeInfo: { background: '#3b82f6', color:'white', padding:'2px 6px', borderRadius:4, fontSize:'0.7em', fontWeight:'bold' }
};