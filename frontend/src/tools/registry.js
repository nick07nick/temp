import { DemoTool } from './DemoTool';
import { FPSMeter } from './FPSMeter';
import { CameraControl } from './CameraControl';
import { PerformanceMonitor } from './PerformanceMonitor';


export const TOOLS = {
    [DemoTool.id]: DemoTool,
    [FPSMeter.id]: FPSMeter,
    [CameraControl.id]: CameraControl,
    [PerformanceMonitor.id]: PerformanceMonitor,
};