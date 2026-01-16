import cv2
import cv2.aruco as aruco


def generate_board():
    # Те же параметры, что в src/stages/calibration.py
    dictionary = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    # (5 столбцов, 7 строк, размер клетки 0.04м, размер маркера 0.02м)
    board = aruco.CharucoBoard((5, 7), 0.04, 0.02, dictionary)

    # Создаем картинку с высоким разрешением для печати (2000x2800 пикселей)
    img = board.generateImage((2000, 2800), marginSize=100, borderBits=1)

    filename = "charuco_board_A4.png"
    cv2.imwrite(filename, img)
    print(f"✅ Готово! Файл {filename} создан.")
    print("Распечатай его на A4 (Scale: 100%) и наклей на твердую картонку.")


if __name__ == "__main__":
    generate_board()