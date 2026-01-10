import React from 'react';
import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';

import { RobotProvider, useRobot } from './context/RobotContext';
import { Workspace } from './components/Workspace';

const StatusBar = () => {
    const { status } = useRobot();
    return (
        <div style={{ 
            height: 30, background: '#1e293b', borderBottom: '1px solid #334155', 
            display: 'flex', alignItems: 'center', padding: '0 15px', justifyContent: 'space-between',
            fontSize: '0.8em', color: '#94a3b8'
        }}>
            <div style={{fontWeight: 'bold', color: '#e2e8f0'}}>BikeFit Pro <span style={{color: '#38bdf8'}}>Workstation</span></div>
            <div>
                Server: <span style={{ color: status === 'connected' ? '#4ade80' : '#ef4444' }}>{status.toUpperCase()}</span>
            </div>
        </div>
    );
};

export default function App() {
  return (
    <RobotProvider>
        <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden', background: '#0f172a', color: 'white' }}>
            <ToastContainer position="top-right" theme="dark" limit={3} />
            <StatusBar />
            <Workspace />
        </div>
    </RobotProvider>
  );
}