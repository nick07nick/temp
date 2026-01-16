# src/plugins/calibration/world.py
import cv2
import numpy as np
import json
import os
from pathlib import Path
from loguru import logger
from src.core.config import ROOT_DIR


class WorldAligner:
    def __init__(self, board_def):
        self.board = board_def
        self.perspective_matrix = None
        self.px_per_cm = 0.0

        self.aligning_mode = False
        self.last_error = 0.0

        self.samples_buffer = []
        self.REQUIRED_SAMPLES = 45

        self.config_dir = ROOT_DIR / "config"
        self.file_name_tpl = "world_cam_{id}.json"

    def handle_command(self, cmd, args):
        if cmd == "align_world":
            if not self.aligning_mode:
                self.aligning_mode = True
                self.samples_buffer = []
                logger.info(f"🌍 STARTED SAMPLING: Need {self.REQUIRED_SAMPLES} frames")
            else:
                self.aligning_mode = False
                self.samples_buffer = []
                logger.info("🌍 ALIGN ABORTED")

    def reset(self):
        self.perspective_matrix = None
        self.px_per_cm = 0.0
        self.last_error = 0.0
        self.samples_buffer = []

    def process_align(self, ctx, corners, ids, vis) -> tuple[bool, float]:
        if not self.aligning_mode: return False, 0.0

        current_count = len(self.samples_buffer)
        progress = int((current_count / self.REQUIRED_SAMPLES) * 100)

        cv2.putText(vis, f"ALIGNING: {progress}% ({current_count}/{self.REQUIRED_SAMPLES})",
                    (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        cv2.putText(vis, "HOLD STILL!", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 1)

        if corners is not None and len(corners) >= 6:
            self.samples_buffer.append({'corners': corners, 'ids': ids})
        else:
            cv2.putText(vis, "LOOKING FOR BOARD...", (20, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

        if len(self.samples_buffer) >= self.REQUIRED_SAMPLES:
            try:
                if self.compute_averaged_alignment():
                    self.aligning_mode = False
                    ctx.ui.send_notification("success", f"Aligned! Scale: {self.px_per_cm:.2f} px/cm")

                    if hasattr(ctx, 'bus') and hasattr(ctx.bus, 'publish_event'):
                        ctx.bus.publish_event("command", {"target": "undistort", "cmd": "reload_config", "args": {}})

                    return True, self.last_error
                else:
                    logger.warning("Alignment calculation failed. Retrying...")
                    self.samples_buffer = []
            except Exception as e:
                logger.error(f"Align Critical Error: {e}")
                self.aligning_mode = False

        return False, 0.0

    def compute_averaged_alignment(self):
        logger.info(f"🧮 Computing average from {len(self.samples_buffer)} frames...")
        point_accumulator = {}

        for sample in self.samples_buffer:
            c_corners = sample['corners']
            c_ids = sample['ids']
            if c_ids is None or len(c_ids) == 0: continue

            flat_ids = c_ids.flatten()
            for i, point_id in enumerate(flat_ids):
                pt = c_corners[i][0]
                point_id = int(point_id)
                if point_id not in point_accumulator:
                    point_accumulator[point_id] = []
                point_accumulator[point_id].append(pt)

        final_img_pts = []
        final_obj_pts = []

        raw_obj_pts = self.board.getChessboardCorners()
        all_obj_pts = np.array(raw_obj_pts).reshape(-1, 3)

        for pt_id, points_list in point_accumulator.items():
            if len(points_list) < (self.REQUIRED_SAMPLES * 0.5): continue
            avg_pt = np.mean(points_list, axis=0)
            if pt_id < len(all_obj_pts):
                pt3d = all_obj_pts[pt_id]
                final_obj_pts.append([pt3d[0], pt3d[1]])
                final_img_pts.append(avg_pt)

        if len(final_obj_pts) < 4: return False

        obj_pts_np = np.array(final_obj_pts, dtype=np.float32).reshape(-1, 1, 2)
        img_pts_np = np.array(final_img_pts, dtype=np.float32).reshape(-1, 1, 2)

        H, mask = cv2.findHomography(img_pts_np, obj_pts_np, cv2.RANSAC, 4.0)

        if H is not None:
            self.perspective_matrix = H
            self._calc_metrics(img_pts_np, obj_pts_np, H)
            return True
        return False

    def _calc_metrics(self, img_pts, obj_pts, H):
        try:
            proj_pts = cv2.perspectiveTransform(img_pts, H)
            self.last_error = cv2.norm(obj_pts, proj_pts, cv2.NORM_L2) / len(obj_pts)
        except:
            self.last_error = 99.9

        try:
            H_inv = np.linalg.inv(H)
            p0 = np.array([[[0, 0]]], dtype=np.float32)
            p1 = np.array([[[0.04, 0]]], dtype=np.float32)
            px0 = cv2.perspectiveTransform(p0, H_inv)
            px1 = cv2.perspectiveTransform(p1, H_inv)
            dist_px = np.linalg.norm(px1 - px0)
            if dist_px > 1e-5: self.px_per_cm = dist_px / 4.0
        except:
            self.px_per_cm = 0.0

    def draw_grid(self, img):
        """
        Рисует бесконечную сетку 10x10см, покрывающую весь кадр.
        """
        if self.perspective_matrix is None: return

        h, w = img.shape[:2]

        try:
            # 1. Находим границы видимой области в Мировых координатах
            # Матрица H переводит Пиксели -> Метры

            # Берем 4 угла экрана
            screen_corners = np.array([
                [[0, 0]], [[w, 0]], [[w, h]], [[0, h]]
            ], dtype=np.float32)

            # Проецируем их на "землю" (в метры)
            world_corners = cv2.perspectiveTransform(screen_corners, self.perspective_matrix)

            # Находим прямоугольник (bounding box), который включает все видимое
            wc = world_corners.reshape(-1, 2)
            min_x, min_y = np.min(wc, axis=0)
            max_x, max_y = np.max(wc, axis=0)

            # Защита от бесконечности (если камера смотрит в горизонт)
            if (max_x - min_x) > 20 or (max_y - min_y) > 20: return  # Ограничим 20 метрами

            # 2. Генерируем линии сетки
            step = 0.10  # 10 см

            # Округляем старт до шага
            start_x = np.floor(min_x / step) * step
            start_y = np.floor(min_y / step) * step

            grid_lines_world = []

            # Вертикальные линии (X = const, Y меняется)
            curr_x = start_x
            while curr_x < max_x + step:
                grid_lines_world.append([[curr_x, min_y]])
                grid_lines_world.append([[curr_x, max_y]])
                curr_x += step

            # Горизонтальные линии (Y = const, X меняется)
            curr_y = start_y
            while curr_y < max_y + step:
                grid_lines_world.append([[min_x, curr_y]])
                grid_lines_world.append([[max_x, curr_y]])
                curr_y += step

            if not grid_lines_world: return

            # 3. Переводим линии обратно в Пиксели для отрисовки
            # Нужна обратная матрица: Метры -> Пиксели
            H_inv = np.linalg.inv(self.perspective_matrix)

            grid_points_world = np.array(grid_lines_world, dtype=np.float32)
            grid_points_px = cv2.perspectiveTransform(grid_points_world, H_inv)

            # 4. Рисуем
            for k in range(0, len(grid_points_px), 2):
                p1 = tuple(grid_points_px[k][0].astype(int))
                p2 = tuple(grid_points_px[k + 1][0].astype(int))

                # Определяем цвет
                # Восстанавливаем координату линии, чтобы узнать, ось ли это
                wx = grid_lines_world[k][0][0]
                wy = grid_lines_world[k][0][1]

                # По умолчанию синий
                color = (255, 100, 0)
                thickness = 1

                # Если рисуем вертикальную линию (X const) и X около 0 -> Ось Y
                # (Проверяем разницу координат X у начала и конца отрезка - она 0)
                # (А так как мы генерировали списки раздельно, можно просто проверить координату)

                # Простая эвристика:
                is_vertical = abs(grid_lines_world[k][0][0] - grid_lines_world[k + 1][0][0]) < 0.001

                if is_vertical:
                    if abs(wx) < 0.001:  # Ось Y (x=0)
                        color = (0, 255, 0)  # Зеленый
                        thickness = 2
                else:  # Горизонтальная
                    if abs(wy) < 0.001:  # Ось X (y=0)
                        color = (0, 0, 255)  # Красный
                        thickness = 2

                cv2.line(img, p1, p2, color, thickness)

            # Центр (0,0)
            origin_world = np.array([[[0.0, 0.0]]], dtype=np.float32)
            origin_px = cv2.perspectiveTransform(origin_world, H_inv)
            pt = tuple(origin_px[0][0].astype(int))
            cv2.circle(img, pt, 5, (0, 255, 255), -1)  # Желтая точка

        except Exception:
            pass

    def set_data(self, data: dict):
        try:
            self.perspective_matrix = np.array(data["perspective_matrix"])
            self.px_per_cm = float(data.get("px_per_cm", 0.0))
            self.last_error = float(data.get("align_error", 0.0))
        except Exception as e:
            logger.error(f"WorldAligner set_data error: {e}")

    def load_config(self, cam_id, custom_path=None):
        if custom_path:
            path = Path(custom_path)
        else:
            path = self.config_dir / self.file_name_tpl.format(id=cam_id)
        if os.path.exists(path):
            with open(path, 'r') as f:
                d = json.load(f)
                self.set_data(d)
            return True
        return False