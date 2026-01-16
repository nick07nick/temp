import os
import sys
import argparse
from pathlib import Path
import platform
import fnmatch


class TreeNode:
    """Класс для представления узла дерева"""

    def __init__(self, name, is_dir=True):
        self.name = name
        self.is_dir = is_dir
        self.children = []
        self.skip = False
        self.parent = None

    def add_child(self, child_node):
        child_node.parent = self
        self.children.append(child_node)


def is_hidden(filepath):
    """Проверяет, является ли файл или папка скрытым"""
    path = Path(filepath)

    if platform.system() != 'Windows':
        return path.name.startswith('.')

    try:
        import ctypes
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        if attrs == -1:
            return False
        return bool(attrs & 2)
    except (AttributeError, OSError):
        return path.name.startswith('.')


def should_exclude(item_name, item_path, is_dir, exclude_dirs, exclude_files, exclude_patterns):
    """Проверяет, нужно ли исключить элемент"""
    if is_hidden(item_path):
        return True

    if is_dir and exclude_dirs:
        if item_name in exclude_dirs:
            return True
        for pattern in exclude_patterns:
            if fnmatch.fnmatch(item_name, pattern):
                return True

    if not is_dir and exclude_files:
        if item_name in exclude_files:
            return True
        for pattern in exclude_patterns:
            if fnmatch.fnmatch(item_name, pattern):
                return True

    return False


def build_tree(root_dir, extensions, exclude_dirs=None, exclude_files=None,
               exclude_patterns=None):
    """Строит дерево файловой системы"""
    if exclude_dirs is None:
        exclude_dirs = set()
    if exclude_files is None:
        exclude_files = set()
    if exclude_patterns is None:
        exclude_patterns = set()

    root_path = Path(root_dir)
    root_node = TreeNode(root_path.name, is_dir=True)

    items = list(root_path.iterdir())
    visible_items = []

    for item in items:
        item_name = item.name
        if should_exclude(item_name, item, item.is_dir(), exclude_dirs, exclude_files, exclude_patterns):
            continue
        visible_items.append(item)

    visible_items.sort(key=lambda x: (not x.is_dir(), x.name.lower()))

    for item in visible_items:
        if item.is_dir():
            child_node = build_tree(item, extensions, exclude_dirs, exclude_files,
                                    exclude_patterns)
            root_node.add_child(child_node)
        else:
            child_node = TreeNode(item.name, is_dir=False)
            file_ext = item.suffix.lower()

            if file_ext in extensions:
                # Файл с нужным расширением
                pass
            else:
                child_node.skip = True

            root_node.add_child(child_node)

    return root_node


def print_tree(node, prefix="", is_last=True):
    """Выводит дерево файловой системы"""
    if node.skip:
        return

    # Создаем коннектор для текущего узла
    if prefix == "":
        # Корневой узел
        print(node.name)
        connector = ""
    else:
        connector = "└── " if is_last else "├── "
        print(f"{prefix}{connector}{node.name}")

    # Рекурсивно выводим детей
    if node.is_dir:
        # Фильтруем детей, чтобы не показывать пропускаемые файлы
        display_children = [child for child in node.children if not child.skip]

        for i, child in enumerate(display_children):
            is_last_child = (i == len(display_children) - 1)
            new_prefix = prefix + ("    " if is_last else "│   ")
            print_tree(child, new_prefix, is_last_child)


def main():
    parser = argparse.ArgumentParser(
        description="Выводит дерево файлов и папок с фильтрацией",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  %(prog)s /path/to/project py js jsx
  %(prog)s /path/to/project py js jsx --exclude-dir node_modules dist
  %(prog)s . py js --exclude-file test.py debug.py
"""
    )

    parser.add_argument("directory", nargs="?", default=".", help="Путь к папке")
    parser.add_argument("extensions", nargs="*", default=["py", "js", "txt"],
                        help="Расширения файлов для отображения")

    parser.add_argument("--exclude-dir", "-ed", nargs="+", default=[], metavar="DIR",
                        help="Исключаемые папки")
    parser.add_argument("--exclude-file", "-ef", nargs="+", default=[], metavar="FILE",
                        help="Исключаемые файлы")
    parser.add_argument("--exclude-pattern", "-ep", nargs="+", default=[], metavar="PATTERN",
                        help="Паттерны для исключения")

    args = parser.parse_args()

    if not os.path.exists(args.directory):
        print(f"Ошибка: папка '{args.directory}' не существует", file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(args.directory):
        print(f"Ошибка: '{args.directory}' не является папкой", file=sys.stderr)
        sys.exit(1)

    # Обрабатываем расширения
    processed_extensions = []
    for ext in args.extensions:
        if not ext.startswith('.'):
            processed_extensions.append(f".{ext}")
        else:
            processed_extensions.append(ext)

    exclude_dirs = set(args.exclude_dir)
    exclude_files = set(args.exclude_file)
    exclude_patterns = set(args.exclude_pattern)

    # Автоматически исключаем системные папки и файлы
    auto_exclude_dirs = {'.git', '.svn', '.hg', '.idea', '.vscode', '__pycache__', 'node_modules', 'dist', 'build'}
    auto_exclude_files = { '.env.local', '.env.production', '.env.development'}

    exclude_dirs.update(auto_exclude_dirs)
    exclude_files.update(auto_exclude_files)

    print(f"Папка: {args.directory}")
    if args.extensions:
        print(f"Показывать файлы с расширениями: {', '.join(processed_extensions)}")
    else:
        print(f"Показывать все файлы")

    if exclude_dirs:
        print(f"Исключаемые папки: {', '.join(sorted(exclude_dirs))}")
    if exclude_files:
        print(f"Исключаемые файлы: {', '.join(sorted(exclude_files))}")
    if exclude_patterns:
        print(f"Паттерны исключения: {', '.join(sorted(exclude_patterns))}")

    print("=" * 60)

    # Строим дерево
    tree_root = build_tree(args.directory, processed_extensions, exclude_dirs,
                           exclude_files, exclude_patterns)

    # Выводим дерево
    print_tree(tree_root)
    print("=" * 60)


if __name__ == "__main__":
    main()