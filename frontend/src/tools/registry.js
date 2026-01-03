// frontend/src/tools/registry.js
import { DemoTool } from './DemoTool';

// Сюда будем добавлять новые инструменты: Ruler, Angle и т.д.
export const TOOLS = {
    [DemoTool.id]: DemoTool,
};