// frontend/src/widgets/registry.js
import React from 'react';
import { CalibrationWidget } from './CalibrationWidget';
import { VideoPlayer } from '../components/video/VideoPlayer';
import { SystemControlWidget } from './SystemControlWidget';
import { useRobot } from '../context/RobotContext';
import { CameraSettingsWidget } from './CameraSettingsWidget';
import { MetricsWidget } from './MetricsWidget';
import { LayoutManagerWidget } from './LayoutManagerWidget';
import { DistanceTrackerWidget } from './DistanceTrackerWidget';
import { AlgorithmSettingsWidget } from './AlgorithmSettingsWidget';
import { HardwareControlWidget} from "./HardwareControlWidget";
import { TestWidget } from './TestWidget';
import { GeometryWidget } from './GeometryWidget';
import { TestMultiCameraWidget } from './TestMultiCameraWidget'; // Путь проверь

// --- WRAPPERS ---
const CameraWrapper = ({ id }) => {
    const { framesBuffer } = useRobot();
    return <VideoPlayer camId={id} bufferRef={framesBuffer} />;
};

const CalibrationWrapper = () => {
    const { sendCommand, widgetsData } = useRobot();
    const data = widgetsData['calibration_widget'] || {};
    return <CalibrationWidget data={data} sendCommand={sendCommand} />;
};

const TestWrapper = () => {
    const { sendCommand, widgetsData } = useRobot();
    const data = widgetsData['test_widget'] || {};
    return <TestWidget data={data} sendCommand={sendCommand} />;
};

const DistanceTrackerWrapper = () => {
    const { sendCommand, widgetsData } = useRobot();
    const widgetObj = widgetsData['distance_tracker'] || {};
    const rawData = widgetObj.data || {};
    const sendToPlugin = (cmd, args = {}) => {
        if (sendCommand) sendCommand('distance_tracker', cmd, args);
    };
    return <DistanceTrackerWidget data={rawData} sendCommand={sendToPlugin} />;
}

// ✅ ВОССТАНОВЛЕННЫЙ WRAPPER ДЛЯ ГЕОМЕТРИИ
const GeometryWrapper = () => {
    const { widgetsData, sendCommand } = useRobot();

    // Бэкенд шлет ID "geometry_control" через ctx.ui.update_widget
    const widgetObj = widgetsData['geometry_control'] || {};

    // Данные лежат в .data (стандартный формат пакета виджета)
    const rawData = widgetObj.data || {};

    return <GeometryWidget data={rawData} sendCommand={sendCommand} />;
};

// --- REGISTRY ---

export const WIDGET_REGISTRY = {
    'test_multicam_debug': {
        title: 'MultiCam Debugger',
        component: TestMultiCameraWidget, // Wrapper не нужен, т.к. мы используем useRobot внутри
        defaultW: 6,
        defaultH: 8
    },
    'camera_0': {
        title: 'Camera Main',
        component: () => <CameraWrapper id={0} />,
        defaultW: 8, defaultH: 10
    },
    'calibration': {
        title: 'Calibration Tool',
        component: CalibrationWrapper,
        defaultW: 6, defaultH: 10
    },
    'system_control': {
        title: 'System Core',
        component: SystemControlWidget,
        defaultW: 4, defaultH: 6
    },
    'camera_settings': {
        title: 'Cam Settings',
        component: CameraSettingsWidget,
        defaultW: 4, defaultH: 8
    },
    'metrics': {
        title: 'Performance',
        component: MetricsWidget,
        defaultW: 4, defaultH: 8
    },
    'layout_manager': {
        title: 'Workspaces',
        component: LayoutManagerWidget,
        defaultW: 4, defaultH: 6
    },
    'distance_tracker': {
        title: 'DistanceTracker',
        component: DistanceTrackerWrapper,
        defaultW: 4, defaultH: 6
    },
    'algo_settings': {
        component: AlgorithmSettingsWidget,
        title: "Algorithm Tuning",
        defaultW: 4, defaultH: 6
    },
    'hardware_settings' :{
        component: HardwareControlWidget,
        title: 'Hardware settings',
        defaultW: 4, defaultH: 6
    },
    'test_ping': {
        component: TestWrapper,
        title: 'Ping Test',
        defaultW: 4, defaultH: 6
    },
    'geometry_control': {
        title: 'Geometry & Tools',
        component: GeometryWrapper, // ✅ Используем Wrapper, как в test_ping
        defaultW: 4,
        defaultH: 8
    }
};

export const getWidgetComponent = (id) => {
    const entry = WIDGET_REGISTRY[id];
    return entry ? entry.component : null;
};