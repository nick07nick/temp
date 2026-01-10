import os
import sys
import argparse
from pathlib import Path
import platform
import fnmatch
import subprocess


class TreeNode:
    """Класс для представления узла дерева"""

    def __init__(self, name, is_dir=True):
        self.name = name
        self.is_dir = is_dir
        self.children = []
        self.line_count = 0
        self.changed_lines = 0
        self.skip = False
        self.has_changes = False
        self.parent = None

    def add_child(self, child_node):
        child_node.parent = self
        self.children.append(child_node)

    def calculate_totals(self):
        """Рекурсивно вычисляет общее количество строк и изменений для папки"""
        if not self.is_dir:
            return self.line_count, self.changed_lines, self.changed_lines > 0

        total_lines = 0
        total_changed = 0
        has_changes = False

        for child in self.children:
            if child.is_dir:
                child_lines, child_changed, child_has_changes = child.calculate_totals()
                total_lines += child_lines
                total_changed += child_changed
                if child_has_changes:
                    has_changes = True
            elif not child.skip:
                total_lines += child.line_count
                total_changed += child.changed_lines
                if child.changed_lines > 0:
                    has_changes = True

        self.line_count = total_lines
        self.changed_lines = total_changed
        self.has_changes = has_changes
        return total_lines, total_changed, has_changes

    def should_display(self, only_changed=False):
        """Определяет, нужно ли отображать этот узел"""
        if not only_changed:
            return True

        # Если это файл с изменениями - показываем
        if not self.is_dir and self.changed_lines > 0:
            return True

        # Если это папка, содержащая изменения - показываем
        if self.is_dir and self.has_changes:
            return True

        return False


def count_lines_in_file(filepath):
    """Считает количество строк в файле"""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


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


def get_git_changes(root_dir, extensions):
    """Получает количество измененных строк из git diff"""
    changed_files = {}

    try:
        # Получаем имя текущей ветки
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=root_dir,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return changed_files

        current_branch = result.stdout.strip()
        remote_ref = f"origin/{current_branch}"

        # Проверяем, существует ли удаленная ветка
        result = subprocess.run(
            ["git", "ls-remote", "--exit-code", "origin", current_branch],
            cwd=root_dir,
            capture_output=True,
            text=True
        )

        diff_target = remote_ref if result.returncode == 0 else "HEAD"

        # Получаем изменения между удаленной веткой и текущим состоянием
        result = subprocess.run(
            ["git", "diff", "--numstat", diff_target],
            cwd=root_dir,
            capture_output=True,
            text=True
        )

        if result.returncode == 0 and result.stdout:
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.split('\t')
                    if len(parts) >= 3:
                        added = int(parts[0]) if parts[0].isdigit() else 0
                        deleted = int(parts[1]) if parts[1].isdigit() else 0
                        file_path = parts[2]

                        # Нормализуем путь
                        file_path = file_path.replace('\\', '/')

                        # Проверяем расширение файла
                        file_ext = Path(file_path).suffix.lower()
                        if file_ext in extensions:
                            changed_lines = added + deleted
                            changed_files[file_path] = changed_lines

        # Также получаем staged изменения
        result = subprocess.run(
            ["git", "diff", "--numstat", "--cached"],
            cwd=root_dir,
            capture_output=True,
            text=True
        )

        if result.returncode == 0 and result.stdout:
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.split('\t')
                    if len(parts) >= 3:
                        added = int(parts[0]) if parts[0].isdigit() else 0
                        deleted = int(parts[1]) if parts[1].isdigit() else 0
                        file_path = parts[2]

                        file_path = file_path.replace('\\', '/')
                        file_ext = Path(file_path).suffix.lower()

                        if file_ext in extensions:
                            changed_lines = added + deleted
                            if file_path in changed_files:
                                changed_files[file_path] += changed_lines
                            else:
                                changed_files[file_path] = changed_lines

    except Exception as e:
        print(f"Ошибка при получении git изменений: {e}", file=sys.stderr)

    return changed_files


def build_tree(root_dir, extensions, exclude_dirs=None, exclude_files=None,
               exclude_patterns=None, changed_files=None, debug=False, repo_root=None):
    """Строит дерево файловой системы"""
    if exclude_dirs is None:
        exclude_dirs = set()
    if exclude_files is None:
        exclude_files = set()
    if exclude_patterns is None:
        exclude_patterns = set()
    if changed_files is None:
        changed_files = {}

    # Если repo_root не указан, используем root_dir как корень
    if repo_root is None:
        repo_root = root_dir

    root_path = Path(root_dir)
    repo_root_path = Path(repo_root)
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
                                    exclude_patterns, changed_files, debug, repo_root)
            root_node.add_child(child_node)
        else:
            child_node = TreeNode(item.name, is_dir=False)
            file_ext = item.suffix.lower()

            if file_ext in extensions:
                child_node.line_count = count_lines_in_file(item)

                # Ключевое исправление: получаем путь относительно repo_root
                try:
                    # Получаем относительный путь от корня репозитория
                    rel_path = str(item.relative_to(repo_root_path))
                    # Нормализуем путь (для Windows)
                    rel_path = rel_path.replace('\\', '/')

                    if debug:
                        print(f"DEBUG: Файл: {item.name}, rel_path: {rel_path}")
                        if rel_path in changed_files:
                            print(f"DEBUG: Найдены изменения: {rel_path} -> {changed_files[rel_path]} строк")

                    child_node.changed_lines = changed_files.get(rel_path, 0)
                except ValueError as e:
                    # Если файл не находится внутри repo_root (маловероятно)
                    if debug:
                        print(f"DEBUG: Ошибка при получении относительного пути для {item}: {e}")
                    child_node.changed_lines = 0
                except Exception as e:
                    if debug:
                        print(f"DEBUG: Другая ошибка: {e}")
                    child_node.changed_lines = 0
            else:
                child_node.skip = True

            root_node.add_child(child_node)

    return root_node


def get_max_lengths_for_level(nodes, max_line_len=0, max_changed_len=0):
    """Находит максимальные длины чисел для текущего уровня"""
    for node in nodes:
        if node.is_dir or not node.skip:
            line_len = len(str(node.line_count))
            changed_len = len(str(node.changed_lines))
            max_line_len = max(max_line_len, line_len)
            max_changed_len = max(max_changed_len, changed_len)

    # Минимальная ширина
    max_line_len = max(max_line_len, 3)
    max_changed_len = max(max_changed_len, 3)

    return max_line_len, max_changed_len


def print_tree_aligned(node, max_line_len, max_changed_len, prefix="",
                       is_last=True, show_changes=True, only_changed=False,
                       min_name_width=20):
    """Выводит дерево с выравниванием"""

    if not node.should_display(only_changed):
        return

    # Получаем детей для текущего уровня
    current_level_nodes = []
    if node.is_dir:
        current_level_nodes = [child for child in node.children
                               if child.should_display(only_changed)]

    # Для текущего уровня вычисляем максимальные длины
    level_line_len, level_changed_len = get_max_lengths_for_level(current_level_nodes)

    # Создаем метку для узла
    if node.is_dir:
        if show_changes:
            line_str = str(node.line_count).rjust(level_line_len)
            changed_str = str(node.changed_lines).rjust(level_changed_len)
            base_label = f"{node.name} [{line_str}]   [{changed_str}]"
        else:
            base_label = f"{node.name} [{node.line_count}]"
    else:
        if node.skip:
            base_label = f"{node.name} [пропускаем]"
        else:
            if show_changes:
                line_str = str(node.line_count).rjust(level_line_len)
                changed_str = str(node.changed_lines).rjust(level_changed_len)
                base_label = f"{node.name} [{line_str}]   [{changed_str}]"
            else:
                base_label = f"{node.name} [{node.line_count}]"

    # Определяем коннектор и формируем полную метку
    if prefix == "":
        # Корневой узел
        print(base_label)
        connector = ""
        full_label = base_label
    else:
        connector = "└── " if is_last else "├── "
        full_label = f"{prefix}{connector}{base_label}"

        # Выравниваем с помощью пробелов
        # Вычисляем текущую длину имени (без учета скобок и чисел)
        if node.is_dir:
            name_part_len = len(node.name) + 3  # +3 для " [" или просто имя
        else:
            if node.skip:
                name_part_len = len(node.name) + len(" [пропускаем]")
            else:
                name_part_len = len(node.name) + 3  # +3 для " ["

        # Вычисляем общую длину префикса и имени
        total_len = len(prefix) + len(connector) + name_part_len

        # Если общая длина меньше минимальной, добавляем пробелы
        if total_len < min_name_width:
            spaces_needed = min_name_width - total_len
            # Вставляем пробелы между именем и скобкой с количеством строк
            if node.is_dir or (not node.skip):
                # Разделяем метку на имя и остальное
                if show_changes and not node.skip:
                    # Формат: имя [число]   [число]
                    name_part = node.name
                    rest = base_label[len(name_part):]
                    spaces = " " * spaces_needed
                    full_label = f"{prefix}{connector}{name_part}{spaces}{rest}"
                else:
                    # Формат: имя [число] или имя [пропускаем]
                    name_part = node.name
                    rest = base_label[len(name_part):]
                    spaces = " " * spaces_needed
                    full_label = f"{prefix}{connector}{name_part}{spaces}{rest}"

        print(full_label)

    # Рекурсивно выводим детей
    if node.is_dir:
        for i, child in enumerate(current_level_nodes):
            is_last_child = (i == len(current_level_nodes) - 1)
            new_prefix = prefix + ("    " if is_last else "│   ")
            print_tree_aligned(child, max_line_len, level_changed_len, new_prefix,
                               is_last_child, show_changes, only_changed, min_name_width)


def get_git_repo_root(start_path):
    """Находит корень git репозитория"""
    path = Path(start_path).resolve()

    while path != path.parent:
        git_dir = path / ".git"
        if git_dir.exists() and git_dir.is_dir():
            return str(path)
        path = path.parent

    return None


def filter_tree_for_display(node, only_changed=False):
    """Фильтрует дерево для отображения только измененных элементов"""
    if not only_changed:
        return node

    # Создаем копию узла
    filtered_node = TreeNode(node.name, node.is_dir)
    filtered_node.line_count = node.line_count
    filtered_node.changed_lines = node.changed_lines
    filtered_node.skip = node.skip
    filtered_node.has_changes = node.has_changes

    # Фильтруем детей
    for child in node.children:
        if child.should_display(only_changed):
            filtered_child = filter_tree_for_display(child, only_changed)
            filtered_node.add_child(filtered_child)

    return filtered_node


def main():
    parser = argparse.ArgumentParser(
        description="Считает количество строк в файлах и показывает изменения из git",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  %(prog)s /path/to/project py js jsx
  %(prog)s /path/to/project py js jsx --changes
  %(prog)s /path/to/project py js jsx --changes --only-changed
  %(prog)s . py js --changes --debug-git
"""
    )

    parser.add_argument("directory", nargs="?", default=".", help="Путь к папке")
    parser.add_argument("extensions", nargs="*", default=["py", "js", "txt"],
                        help="Расширения файлов для подсчета")

    parser.add_argument("--exclude-dir", "-ed", nargs="+", default=[], metavar="DIR",
                        help="Исключаемые папки")
    parser.add_argument("--exclude-file", "-ef", nargs="+", default=[], metavar="FILE",
                        help="Исключаемые файлы")
    parser.add_argument("--exclude-pattern", "-ep", nargs="+", default=[], metavar="PATTERN",
                        help="Паттерны для исключения")

    parser.add_argument("--changes", "-c", action="store_true",
                        help="Показать изменения с последнего коммита/пуша")
    parser.add_argument("--only-changed", "-oc", action="store_true",
                        help="Показать только измененные файлы и папки")
    parser.add_argument("--debug-git", action="store_true",
                        help="Показать отладочную информацию о git")

    parser.add_argument("--min-width", type=int, default=20,
                        help="Минимальная ширина столбца имен (по умолчанию: 20)")

    args = parser.parse_args()

    if not os.path.exists(args.directory):
        print(f"Ошибка: папка '{args.directory}' не существует", file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(args.directory):
        print(f"Ошибка: '{args.directory}' не является папкой", file=sys.stderr)
        sys.exit(1)

    git_root = get_git_repo_root(args.directory)
    if args.changes and not git_root:
        print(f"Внимание: '{args.directory}' не является git репозиторием", file=sys.stderr)
        args.changes = False

    processed_extensions = []
    for ext in args.extensions:
        if not ext.startswith('.'):
            processed_extensions.append(f".{ext}")
        else:
            processed_extensions.append(ext)

    exclude_dirs = set(args.exclude_dir)
    exclude_files = set(args.exclude_file)
    exclude_patterns = set(args.exclude_pattern)

    auto_exclude_dirs = {'.git', '.svn', '.hg', '.idea', '.vscode', '__pycache__', 'node_modules', 'dist', 'build'}
    auto_exclude_files = {'.env', '.env.local', '.env.production', '.env.development'}

    exclude_dirs.update(auto_exclude_dirs)
    exclude_files.update(auto_exclude_files)

    print(f"Анализируем папку: {args.directory}")
    print(f"Расширения для подсчёта: {', '.join(processed_extensions)}")

    if args.changes:
        print("Режим: показывать изменения с последнего коммита/пуша")
    if args.only_changed:
        print("Режим: показывать только измененные файлы")

    if exclude_dirs:
        print(f"Исключаемые папки: {', '.join(sorted(exclude_dirs))}")
    if exclude_files:
        print(f"Исключаемые файлы: {', '.join(sorted(exclude_files))}")
    if exclude_patterns:
        print(f"Паттерны исключения: {', '.join(sorted(exclude_patterns))}")

    print("=" * 80)

    changed_files = {}
    if args.changes and git_root:
        if args.debug_git:
            print("\nОтладочная информация git:")
            print(f"Корень репозитория: {git_root}")

            result = subprocess.run(
                ["git", "remote", "-v"],
                cwd=git_root,
                capture_output=True,
                text=True
            )
            if result.stdout:
                print(f"Удаленные репозитории:\n{result.stdout}")

            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=git_root,
                capture_output=True,
                text=True
            )
            if result.stdout:
                print(f"Текущая ветка: {result.stdout.strip()}")

            result = subprocess.run(
                ["git", "status", "--short"],
                cwd=git_root,
                capture_output=True,
                text=True
            )
            if result.stdout:
                print(f"Статус git:\n{result.stdout}")

            print("-" * 50)

        changed_files = get_git_changes(git_root, processed_extensions)

        if args.debug_git:
            print(f"\nНайдено изменений в {len(changed_files)} файлах:")
            for file_path, changes in sorted(changed_files.items()):
                print(f"  {file_path}: {changes} строк")
            print("-" * 50)

    # Строим дерево, передавая корень репозитория как repo_root
    tree_root = build_tree(args.directory, processed_extensions, exclude_dirs,
                           exclude_files, exclude_patterns, changed_files,
                           args.debug_git, git_root)

    total_lines, total_changed, has_changes = tree_root.calculate_totals()

    # Фильтруем дерево если нужно показывать только измененные
    if args.only_changed:
        display_tree = filter_tree_for_display(tree_root, args.only_changed)
    else:
        display_tree = tree_root

    # Получаем максимальные длины для корневого уровня
    if display_tree.is_dir:
        children_to_display = [child for child in display_tree.children
                               if child.should_display(args.only_changed)]
        max_line_len, max_changed_len = get_max_lengths_for_level(children_to_display)
    else:
        max_line_len, max_changed_len = 4, 4

    # Выводим дерево
    if display_tree.is_dir:
        # Выводим корневую папку
        if args.changes:
            line_str = str(display_tree.line_count).rjust(max_line_len)
            changed_str = str(display_tree.changed_lines).rjust(max_changed_len)
            print(f"{display_tree.name} [{line_str}]   [{changed_str}]")
        else:
            print(f"{display_tree.name} [{display_tree.line_count}]")

        # Выводим детей
        for i, child in enumerate(children_to_display):
            is_last_child = (i == len(children_to_display) - 1)
            print_tree_aligned(child, max_line_len, max_changed_len, "",
                               is_last_child, args.changes, args.only_changed,
                               args.min_width)
    else:
        # Если это файл (маловероятно)
        if display_tree.skip:
            print(f"{display_tree.name} [пропускаем]")
        else:
            if args.changes:
                line_str = str(display_tree.line_count).rjust(max_line_len)
                changed_str = str(display_tree.changed_lines).rjust(max_changed_len)
                print(f"{display_tree.name} [{line_str}]   [{changed_str}]")
            else:
                print(f"{display_tree.name} [{display_tree.line_count}]")

    print("=" * 80)

    if args.changes:
        print(f"Итого строк во всех файлах с указанными расширениями: {total_lines}")
        print(f"Изменено строк с последнего коммита/пуша: {total_changed}")

        if total_lines > 0:
            percentage = (total_changed / total_lines) * 100
            print(f"Изменения составляют: {percentage:.1f}% от общего количества строк")
    else:
        print(f"Итого строк во всех файлах с указанными расширениями: {total_lines}")


if __name__ == "__main__":
    main()