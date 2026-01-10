// src/widgets/registry.js
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

// --- WRAPPERS (Связующий слой) ---
const CameraWrapper = ({ id }) => {
    const { framesBuffer } = useRobot();
    return <VideoPlayer camId={id} bufferRef={framesBuffer} />;
};

const CalibrationWrapper = () => {
    const { sendCommand, widgetsData } = useRobot();
    // Важно: ID виджета должен совпадать с тем, что шлет бэкенд (calibration_widget)
    const data = widgetsData['calibration_widget'] || {};
    return <CalibrationWidget data={data} sendCommand={sendCommand} />;
};

// [FIX] Создаем обертку для Тестового Виджета
const TestWrapper = () => {
    const { sendCommand, widgetsData } = useRobot();
    // Бэкенд будет слать данные с ID "test_widget"
    const data = widgetsData['test_widget'] || {};
    return <TestWidget data={data} sendCommand={sendCommand} />;
};
// [FIX] ИСПРАВЛЕННЫЙ WRAPPER ДЛЯ ДИСТАНЦИИ
const DistanceTrackerWrapper = () => {
    const { sendCommand, widgetsData } = useRobot();

    // 1. Получаем системный объект виджета
    const widgetObj = widgetsData['distance_tracker'] || {};

    // 2. [FIX] Достаем полезную нагрузку из свойства .data
    // Если данных еще нет, передаем пустой объект, чтобы виджет не падал
    const rawData = widgetObj.data || {};

    const sendToPlugin = (cmd, args = {}) => {
        if (sendCommand) {
            sendCommand('distance_tracker', cmd, args);
        }
    };

    // 3. Передаем в виджет уже "чистые" данные
    return <DistanceTrackerWidget data={rawData} sendCommand={sendToPlugin} />;
}

// --- REGISTRY ---

export const WIDGET_REGISTRY = {
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
    // [FIX] Регистрируем через Wrapper
    'test_ping': {
        component: TestWrapper,
        title: 'Ping Test',
        defaultW: 4, defaultH: 6
    }
};