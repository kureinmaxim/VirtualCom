import serial
import serial.tools.list_ports
import sys
import threading
import time
import os # Для очистки экрана
import json
import subprocess
from pathlib import Path
from version_info import __release_date__, __version__

# Кроссплатформенный импорт модулей для работы с клавиатурой
if os.name == 'nt':
    import msvcrt
    getch = msvcrt.getch
    kbhit = msvcrt.kbhit
else:
    import sys
    import tty
    import termios
    import select
    
    class UnixGetch:
        """Класс для реализации getch() на Unix-подобных системах."""
        def __call__(self):
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(sys.stdin.fileno())
                ch = sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            
            # Обработка Ctrl+C (ETX)
            if ch == '\x03':
                raise KeyboardInterrupt
            
            return ch.encode('utf-8')

    def unix_kbhit():
        """Реализация kbhit() для Unix."""
        dr, dw, de = select.select([sys.stdin], [], [], 0)
        return dr != []

    getch = UnixGetch()
    kbhit = unix_kbhit

# Значения по умолчанию

DEFAULT_SETTINGS = {
    "baudrate": 38400,
    "bytesize": serial.EIGHTBITS,
    "parity": serial.PARITY_NONE,
    "stopbits": serial.STOPBITS_ONE
}

POLYNOMIAL = 0xA001  # Стандартный полином для CRC16-MODBUS
HISTORY_KEYS = ("text", "hex", "hex_crc")
RUNTIME_COMMANDS = ("help", "init", "doctor", "history", "/help", "/init", "/doctor", "/history")
RUNTIME_COMMAND_HELP = {
    "help": "Справка по служебным командам",
    "init": "Текущие параметры порта/сессии",
    "doctor": "Диагностика соединения",
    "history": "История команд текущего режима",
}

if os.name != 'nt':
    try:
        import readline  # type: ignore
        READLINE_AVAILABLE = True
    except Exception:
        READLINE_AVAILABLE = False
else:
    READLINE_AVAILABLE = False


def get_user_data_dir() -> Path:
    """Возвращает каталог данных приложения, переживающий переустановку."""
    if os.name == 'nt':
        appdata = os.getenv("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "VirtualCom"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "VirtualCom"
    return Path.home() / ".local" / "share" / "VirtualCom"


APP_DATA_DIR = get_user_data_dir()
HISTORY_FILE = APP_DATA_DIR / "command_history.json"


def _empty_history() -> dict[str, list[str]]:
    return {key: [] for key in HISTORY_KEYS}


def deduplicate_list_keep_last(items: list[str]) -> list[str]:
    """Удаляет дубликаты, оставляя последнее вхождение."""
    seen: set[str] = set()
    result_rev: list[str] = []
    for item in reversed(items):
        if item not in seen:
            seen.add(item)
            result_rev.append(item)
    return list(reversed(result_rev))


def load_command_history() -> dict[str, list[str]]:
    """Загружает историю команд из JSON-файла."""
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not HISTORY_FILE.exists():
        return _empty_history()
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        normalized = _empty_history()
        if isinstance(data, dict):
            for key in HISTORY_KEYS:
                value = data.get(key, [])
                if isinstance(value, list):
                    cleaned = [str(v) for v in value if str(v).strip()]
                    normalized[key] = deduplicate_list_keep_last(cleaned)
        return normalized
    except Exception:
        # Поврежденный файл не должен ломать запуск.
        return _empty_history()


def save_command_history():
    """Сохраняет историю команд в JSON-файл."""
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(
        json.dumps(COMMAND_HISTORY, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def add_command_to_history(history_key: str, command: str):
    """Добавляет команду в историю и сохраняет ее на диск."""
    value = command.strip()
    if not value or history_key not in COMMAND_HISTORY:
        return
    # Сразу поддерживаем историю без дублей:
    # одинаковая команда переносится в конец как "последняя использованная".
    COMMAND_HISTORY[history_key] = [cmd for cmd in COMMAND_HISTORY[history_key] if cmd != value]
    COMMAND_HISTORY[history_key].append(value)
    save_command_history()


def apply_readline_history(history_key: str):
    """Подгружает историю выбранного раздела в readline (macOS/Linux)."""
    if not READLINE_AVAILABLE:
        return
    readline.clear_history()
    for item in COMMAND_HISTORY.get(history_key, []):
        readline.add_history(item)


def make_readline_completer(history_key: str | None):
    """Tab-completion для служебных команд и истории текущего режима."""
    mode_items = COMMAND_HISTORY.get(history_key, []) if history_key in HISTORY_KEYS else []
    candidates = sorted(set((*RUNTIME_COMMANDS, *mode_items)), key=str.lower)

    def _completer(text, state):
        lowered = text.lower()
        matches = [item for item in candidates if item.lower().startswith(lowered)]
        return matches[state] if state < len(matches) else None

    return _completer


def make_readline_display_hook(prompt: str):
    """Красиво выводит варианты автодополнения как в терминале."""
    def _display(substitution, matches, longest_match_length):
        print()
        for item in matches:
            key = item.lstrip("/")
            hint = RUNTIME_COMMAND_HELP.get(key)
            if hint:
                print(f"  {item:<12} - {hint}")
            else:
                print(f"  {item}")
        try:
            current = readline.get_line_buffer()
        except Exception:
            current = substitution
        print(f"{prompt}{current}", end="", flush=True)

    return _display


def history_label(history_key: str) -> str:
    labels = {"text": "Текст", "hex": "HEX", "hex_crc": "HEX+CRC"}
    return labels.get(history_key, history_key)


def flatten_history(mode_key: str | None) -> list[tuple[str, str]]:
    if mode_key in HISTORY_KEYS:
        return [(mode_key, cmd) for cmd in COMMAND_HISTORY[mode_key]]
    result: list[tuple[str, str]] = []
    for key in HISTORY_KEYS:
        result.extend((key, cmd) for cmd in COMMAND_HISTORY[key])
    return result


def deduplicate_history(mode_key: str | None):
    """Удаляет дубликаты, оставляя последнее вхождение команды."""
    keys = [mode_key] if mode_key in HISTORY_KEYS else list(HISTORY_KEYS)
    for key in keys:
        seen: set[str] = set()
        dedup_reversed: list[str] = []
        for cmd in reversed(COMMAND_HISTORY[key]):
            if cmd not in seen:
                seen.add(cmd)
                dedup_reversed.append(cmd)
        COMMAND_HISTORY[key] = list(reversed(dedup_reversed))
    save_command_history()


def clear_history(mode_key: str | None):
    keys = [mode_key] if mode_key in HISTORY_KEYS else list(HISTORY_KEYS)
    for key in keys:
        COMMAND_HISTORY[key] = []
    save_command_history()


def show_history_entries(mode_key: str | None):
    entries = flatten_history(mode_key)
    if not entries:
        print("\n📭 История пуста.")
        return
    print("\n=== 🕘 История команд ===")
    for i, (key, cmd) in enumerate(entries, start=1):
        print(f"  {i}. [{history_label(key)}] {cmd}")


def manage_command_history():
    """Упрощенное меню управления историей (без вложенных шагов)."""
    while True:
        entries = flatten_history(None)
        print(f"\n📂 Файл истории: {HISTORY_FILE}")
        print(f"Всего записей: {len(entries)}")
        action = choose_option(
            "Управление историей:",
            [
                "Показать историю",
                "Удалить запись",
                "Удалить дубликаты (вся история)",
                "Очистить всю историю",
                "Назад",
            ],
        )

        if action == "Назад":
            return

        if action == "Показать историю":
            show_history_entries(None)
            continue

        if action == "Удалить запись":
            if not entries:
                print("\n📭 История пуста.")
                continue
            show_history_entries(None)
            try:
                idx = int(input("\nВведите номер записи для удаления: ").strip())
            except ValueError:
                print("⚠️ Ошибка: введите число.")
                continue
            if idx < 1 or idx > len(entries):
                print("⚠️ Ошибка: номер вне диапазона.")
                continue
            key, value = entries[idx - 1]
            try:
                COMMAND_HISTORY[key].remove(value)
            except ValueError:
                print("⚠️ Не удалось удалить запись (история изменилась).")
                continue
            save_command_history()
            print("✅ Запись удалена.")
            continue

        if action == "Удалить дубликаты (вся история)":
            deduplicate_history(None)
            print("✅ Дубликаты удалены.")
            continue

        if action == "Очистить всю историю":
            confirm = input("Подтвердите очистку (y/n): ").strip().lower()
            if confirm == "y":
                clear_history(None)
                print("✅ История очищена.")
            else:
                print("ℹ️ Очистка отменена.")


COMMAND_HISTORY = load_command_history()


def safe_close_serial(ser, port_name: str | None = None):
    """Безопасно закрывает serial-порт без падения на повторном close()."""
    if not ser:
        return
    try:
        if ser.is_open:
            ser.close()
            if port_name:
                print(f"\n🔌 Порт {port_name} закрыт.")
    except (serial.SerialException, OSError):
        # Уже закрыт/дескриптор недоступен — для graceful shutdown это нормально.
        pass

def calculate_crc16(data: bytes) -> int:
    """
    Вычисляет CRC16 для переданных данных.
    Аналог алгоритма из C-кода.
    """
    crc = 0xFFFF

    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ POLYNOMIAL
            else:
                crc >>= 1

    return crc

def receive_data(ser, port_name, processing_event):
    """Функция для приема и обработки данных в отдельном потоке"""
    while ser.is_open:
        try:
            # Ждем события или таймаута 0.1 сек
            # Если событие НЕ установлено (остановлено), wait вернет False
            # Если событие установлено, wait вернет True сразу
            is_processing_allowed = processing_event.wait(timeout=0.1)

            # Если прием не разрешен или нет данных, пропускаем итерацию
            if not is_processing_allowed or not ser.in_waiting:
                time.sleep(0.05) # Небольшая пауза, чтобы не грузить ЦП в ожидании
                continue

            # Прием и обработка данных (только если is_processing_allowed == True и есть данные)
            request = ser.read(ser.in_waiting)
            print(f"\n{port_name} 📥 Получены данные HEX: {' '.join(f'{b:02X}' for b in request)}")
            try:
                # Попытка декодировать как ASCII, заменяя непечатаемые символы
                ascii_representation = request.decode('ascii', errors='replace')
            except UnicodeDecodeError:
                # Если декодирование не удалось, показать как есть (редкий случай для ASCII)
                ascii_representation = repr(request)
            print(f"{port_name} 📥 ASCII: {ascii_representation}")
            response = process_request(request)
            if response:
                ser.write(response)
                print(f"📤 Отправлен автоответ: {' '.join(f'{b:02X}' for b in response)}")
            # Не печатаем меню-приглашение из фонового потока:
            # это ломает UX в режимах отправки (HEX/TEXT), создавая ложное
            # впечатление, что приложение вышло в главное меню.

        except serial.SerialException as serial_err:
            # Обработка ошибок, связанных с портом (например, отключение устройства)
            print(f"\n⚠️ Ошибка порта в потоке приема: {serial_err}")
            break # Выход из цикла потока
        except OSError as e:
            # При закрытии порта в другом потоке на Unix/macOS возможен EBADF.
            if getattr(e, "errno", None) == 9:
                break
            print(f"\n⚠️ Ошибка ОС при приеме данных: {e}")
            time.sleep(0.1)
        except Exception as e:
            if isinstance(e, OSError) and getattr(e, "errno", None) == 9:
                break
            print(f"\n⚠️ Ошибка при приеме данных: {e}")
            # Можно продолжить или выйти в зависимости от типа ошибки
            time.sleep(0.1)

def send_hex_data(ser, hex_string: str):
    """Отправка HEX данных в порт"""
    try:
        hex_string = hex_string.replace(" ", "")
        if not all(c in '0123456789ABCDEFabcdef' for c in hex_string):
            print("❌ Ошибка: неверный формат HEX данных")
            return False
        
        data = bytes.fromhex(hex_string)
        ser.write(data)
        print(f"📤 Отправлено (HEX): {' '.join(f'{b:02X}' for b in data)}")
        return True
    except ValueError:
        print("❌ Ошибка: неверный формат HEX данных")
        return False

def send_hex_data_with_crc(ser, hex_string: str):
    """Отправка HEX данных в порт с добавлением CRC16"""
    try:
        hex_string = hex_string.replace(" ", "")
        if not all(c in '0123456789ABCDEFabcdef' for c in hex_string):
            print("❌ Ошибка: неверный формат HEX данных")
            return False
        
        data = bytes.fromhex(hex_string)
        crc = calculate_crc16(data)
        
        # Добавляем CRC к данным (младший байт первый)
        final_data = data + bytes([crc & 0xFF, (crc >> 8) & 0xFF])
        
        ser.write(final_data)
        print(f"📤 Отправлено (HEX+CRC): {' '.join(f'{b:02X}' for b in data)} | CRC: {crc & 0xFF:02X} {(crc >> 8) & 0xFF:02X}")
        return True
        
    except ValueError:
        print("❌ Ошибка: неверный формат HEX данных")
        return False

def send_text_message(ser, message: str):
    """Отправка текстового сообщения в порт"""
    data = message.encode('utf-8')
    ser.write(data)
    print(f"📤 Отправлено (текст): {message}")
    return True

def show_menu(status_message: str | None = None):
    """Отображение меню команд и опционального статусного сообщения."""
    print("\n=== 📋 Меню команд ===")
    print("1. Отправить текстовое сообщение")
    print("2. Отправить HEX данные")
    print("3. Отправить HEX данные с CRC16")
    print("4. 🛑 Остановить прием команд")
    print("5. ▶️  Продолжить прием команд")
    print("6. Очистить экран")
    print("7. Выход")
    print("8. 🕘 История команд")
    if status_message:
        print(f"\n{status_message}") 
    print("Выберите действие (1-8), Меню (Esc) или Выход (Ctrl+C): ", end='', flush=True)

def list_available_ports():
    """Возвращает список доступных COM-портов и выводит их на экран, отсортированных по номеру."""
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("❌ Нет доступных последовательных портов!")
        return []

    # На macOS скрываем системные pseudo-порты, которые часто путают
    # и не используются как обычные внешние последовательные устройства.
    if os.name != 'nt':
        excluded_keywords = ("Bluetooth-Incoming-Port", "debug-console")
        filtered_ports = [
            p for p in ports
            if not any(keyword in p.device for keyword in excluded_keywords)
        ]
        if filtered_ports:
            ports = filtered_ports

    # Функция для извлечения номера из имени порта (например, COM10 -> 10)
    def extract_com_number(port_info):
        try:
            # Ищем только цифры в имени устройства
            num_str = ''.join(filter(str.isdigit, port_info.device))
            return int(num_str) if num_str else float('inf') # Если цифр нет, ставим в конец
        except (ValueError, TypeError):
            return float('inf') # В случае ошибки ставим в конец

    # Сортируем порты по извлеченному номеру
    ports.sort(key=extract_com_number)

    print("\n🔌 Доступные порты (отсортировано):")
    print("  0. ➕ Открыть еще одно приложение (дубликат)")
    for i, port in enumerate(ports, start=1):
        print(f"  {i}. {port.device}")

    return ports

def select_port():
    """Позволяет выбрать COM-порт по номеру."""
    ports = list_available_ports()
    if not ports:
        return None

    while True:
        try:
            selected_raw = input("\nВведите номер порта (или 0 для дубликата): ").strip()
            if selected_raw == "0":
                launch_duplicate_instance()
                continue
            selected_index = int(selected_raw) - 1
            if 0 <= selected_index < len(ports):
                return ports[selected_index].device
            print("⚠️ Ошибка: введите корректный номер порта!")
        except ValueError:
            print("⚠️ Ошибка: введите число!")


def launch_duplicate_instance():
    """Запускает еще один экземпляр приложения."""
    try:
        is_frozen = getattr(sys, "frozen", False)

        # Запуск собранного приложения (PyInstaller)
        if is_frozen:
            if sys.platform == "darwin":
                exe_path = Path(sys.executable).resolve()
                # .../VirtualCom.app/Contents/Resources/VirtualCom_bin -> .../VirtualCom.app
                app_bundle = exe_path.parents[2]
                if app_bundle.suffix == ".app" and app_bundle.exists():
                    subprocess.Popen(["open", "-n", str(app_bundle)])
                else:
                    subprocess.Popen([str(exe_path)])
            elif os.name == "nt":
                creation_flags = (
                    getattr(subprocess, "DETACHED_PROCESS", 0)
                    | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                )
                subprocess.Popen([sys.executable], creationflags=creation_flags)
            else:
                subprocess.Popen([sys.executable])
        else:
            # Запуск из исходников
            subprocess.Popen([sys.executable, str(Path(__file__).resolve())])

        print("✅ Запущен новый экземпляр приложения.")
    except Exception as e:
        print(f"❌ Не удалось запустить дубликат: {e}")

def is_port_currently_available(port_name: str) -> bool:
    """Проверяет, что порт все еще присутствует в актуальном списке устройств."""
    current_ports = {p.device.upper() for p in serial.tools.list_ports.comports()}
    return port_name.upper() in current_ports

def ask_retry_port_selection() -> bool:
    """Спрашивает, нужно ли повторить выбор порта."""
    while True:
        retry = input("\nПопробовать выбрать другой порт? (y/n): ").lower().strip()
        if retry in ['y', 'n']:
            return retry == 'y'
        print("Пожалуйста, введите 'y' или 'n'")

def is_phantom_port_error(error_text: str) -> bool:
    """Определяет типовую ошибку Windows для отключенного/фантомного COM-порта."""
    return (
        "A device which does not exist was specified" in error_text
        or "WinError 433" in error_text
        or "OSError(22" in error_text
    )

def choose_configuration_mode():
    """Выбор режима настройки порта"""
    print("\n=== ⚙  Настройка последовательного порта ===")
    print("1. Ручная настройка параметров")
    print("2. Использовать настройки по умолчанию")
    print("   (38400 бод, 8 бит, без паритета, 1 стоп-бит)")

    print("\nВыберите режим настройки (1 или 2): ", end='', flush=True)
    while True:
        key = getch()
        if key == b'1':
            print("1")
            return None
        if key == b'2':
            print("2")
            return DEFAULT_SETTINGS
        if key == b'\x03':
            raise KeyboardInterrupt
        print("⚠️ Некорректный выбор. Пожалуйста, введите 1 или 2.")
        print("Выберите режим настройки (1 или 2): ", end='', flush=True)

def choose_option(prompt, options):
    """Позволяет выбрать один из предложенных вариантов."""
    print(f"\n{prompt}")
    num_options = len(options)
    for i, option in enumerate(options, start=1):
        print(f"  {i}. {option}")

    print("Выберите номер: ", end='', flush=True)
    while True:
        try:
            key = getch()
            digit = key.decode('ascii')
            selected_index = int(digit) - 1
            if 0 <= selected_index < num_options:
                print(digit)
                return options[selected_index]
            print("⚠️ Ошибка: выберите корректный номер!")
            print("Выберите номер: ", end='', flush=True)
        except ValueError:
            print("⚠️ Ошибка: введите число!")
            print("Выберите номер: ", end='', flush=True)
        except UnicodeDecodeError:
            if key == b'\x03':
                raise KeyboardInterrupt
            # Игнорируем не-ASCII клавиши
            continue

def full_port_configuration():
    """Полная ручная настройка порта"""
    # Изменяем порядок baudrate и добавляем метку
    baudrate_display_list = [
        "115200 (стандарт)", 
        "1200", "2400", "4800", "9600", "19200", "38400", "57600"
    ]
    # Словарь для сопоставления отображаемой строки с числовым значением
    baudrate_values = {str(b): b for b in [1200, 2400, 4800, 9600, 19200, 38400, 57600]}
    baudrate_values["115200 (стандарт)"] = 115200
    
    baudrate_choice = choose_option("Выберите скорость передачи (бод):", baudrate_display_list)
    baudrate = baudrate_values[baudrate_choice] # Получаем числовое значение

    # Изменяем порядок bytesize
    bytesize_options_ordered = {
        "8 бит (стандарт)": serial.EIGHTBITS,
        "5 бит": serial.FIVEBITS,
        "6 бит": serial.SIXBITS,
        "7 бит": serial.SEVENBITS
    }
    bytesize_keys_ordered = list(bytesize_options_ordered.keys())
    bytesize_choice = choose_option("Выберите размер байта:", bytesize_keys_ordered)
    bytesize = bytesize_options_ordered[bytesize_choice]

    # Оставляем порядок parity как есть
    parity_options = {
        "Нет": serial.PARITY_NONE,
        "Четный (Even)": serial.PARITY_EVEN,
        "Нечетный (Odd)": serial.PARITY_ODD,
        "Маркер (Mark)": serial.PARITY_MARK,
        "Пробел (Space)": serial.PARITY_SPACE
    }
    parity_choice = choose_option("Выберите паритет:", list(parity_options.keys()))
    parity = parity_options[parity_choice]

    # Оставляем порядок stopbits как есть
    stopbits_list = [serial.STOPBITS_ONE, serial.STOPBITS_ONE_POINT_FIVE, serial.STOPBITS_TWO]
    stopbits = choose_option("Выберите количество стоп-битов:", stopbits_list)

    return {
        "baudrate": baudrate,
        "bytesize": bytesize,
        "parity": parity,
        "stopbits": stopbits
    }

def read_line_msvcrt(prompt="", history_key: str | None = None):
    """Читает строку ввода посимвольно (кроссплатформенно).
    
    Поддерживает Backspace, завершает ввод по Enter.
    Возвращает None при нажатии Esc, пустую строку при Ctrl+C.
    """
    # На Unix/macOS в некоторых терминалах (особенно при запуске из .app)
    # посимвольный raw-ввод может вести себя нестабильно.
    # Для надежности используем обычный построчный input().
    if os.name != 'nt':
        old_completer = None
        old_delims = None
        display_hook_supported = hasattr(readline, "set_completion_display_matches_hook")
        if READLINE_AVAILABLE:
            if history_key in HISTORY_KEYS:
                apply_readline_history(history_key)
            old_completer = readline.get_completer()
            old_delims = readline.get_completer_delims()
            readline.set_completer_delims(" \t\n")
            # На macOS часто используется libedit (не GNU readline).
            # Для него нужен другой синтаксис бинда Tab.
            if "libedit" in (getattr(readline, "__doc__", "") or "").lower():
                readline.parse_and_bind("bind ^I rl_complete")
            else:
                readline.parse_and_bind("tab: complete")
            readline.set_completer(make_readline_completer(history_key))
            if display_hook_supported:
                readline.set_completion_display_matches_hook(make_readline_display_hook(prompt))
        try:
            user_input = input(prompt)
        finally:
            if READLINE_AVAILABLE:
                readline.set_completer(old_completer)
                if old_delims is not None:
                    readline.set_completer_delims(old_delims)
                if display_hook_supported:
                    readline.set_completion_display_matches_hook(None)
        # Аналог "Esc" для line-input режима.
        if user_input.strip().lower() in {"esc", "/esc", "/menu", "/back"}:
            return None
        return user_input
        
    print(prompt, end='', flush=True)
    chars = []
    history_index = -1  # -1 = новая команда, 0+ = индекс в истории
    current_history = COMMAND_HISTORY.get(history_key, []) if history_key in HISTORY_KEYS else []

    while True:
        try:
            key = getch()

            if key == b'\r' or key == b'\n': # Enter (Windows \r, Unix \n)
                print() # Перевод строки после ввода
                break
            elif key == b'\x1b': # Esc
                print(" [Esc]") # Показываем, что нажали Esc
                return None # Возвращаем None для выхода из цикла
            elif key == b'\x08' or key == b'\x7f': # Backspace (Windows \x08, Unix \x7f)
                if chars:
                    chars.pop()
                    # Стереть символ с консоли: \b (назад) + ' ' (пробел) + \b (назад)
                    print('\b \b', end='', flush=True)
                    history_index = -1  # Сброс при ручном редактировании
            elif key == b'\t':  # Tab - автодополнение
                current_text = "".join(chars).lower()
                # Кандидаты: служебные команды + история текущего режима
                candidates = list(RUNTIME_COMMANDS)
                if history_key in HISTORY_KEYS:
                    candidates.extend(COMMAND_HISTORY.get(history_key, []))
                # Удаляем дубликаты и сортируем
                candidates = sorted(set(candidates), key=str.lower)
                # Ищем совпадения
                matches = [c for c in candidates if c.lower().startswith(current_text)]

                if len(matches) == 1:
                    # Одно совпадение - автодополняем
                    print('\r' + ' ' * (len(prompt) + len(chars)), end='', flush=True)
                    chars = list(matches[0])
                    print(f'\r{prompt}{"".join(chars)}', end='', flush=True)
                    history_index = -1
                elif len(matches) > 1:
                    # Несколько совпадений - показываем список
                    print()
                    for match in matches:
                        key_name = match.lstrip("/")
                        hint = RUNTIME_COMMAND_HELP.get(key_name)
                        if hint:
                            print(f"  {match:<12} - {hint}")
                        else:
                            print(f"  {match}")
                    print(f'{prompt}{"".join(chars)}', end='', flush=True)
            elif key == b'\x03': # Ctrl+C
                 # Не прерываем здесь, чтобы позволить основному циклу обработать
                 print(" [Ctrl+C]")
                 raise KeyboardInterrupt
            elif key == b'\x00' or key == b'\xe0':  # Специальные клавиши на Windows (стрелки, F-клавиши и т.д.)
                if kbhit():  # Проверяем наличие второго байта
                    arrow_key = getch()
                    if arrow_key == b'H' and current_history:  # Стрелка вверх
                        # Перемещаемся назад по истории
                        if history_index == -1:
                            history_index = len(current_history) - 1
                        elif history_index > 0:
                            history_index -= 1

                        # Очищаем текущую строку и выводим команду из истории
                        print('\r' + ' ' * (len(prompt) + len(chars)), end='', flush=True)
                        chars = list(current_history[history_index])
                        print(f'\r{prompt}{"".join(chars)}', end='', flush=True)

                    elif arrow_key == b'P' and current_history:  # Стрелка вниз
                        # Перемещаемся вперед по истории
                        if history_index >= 0 and history_index < len(current_history) - 1:
                            history_index += 1
                            # Очищаем строку и выводим следующую команду
                            print('\r' + ' ' * (len(prompt) + len(chars)), end='', flush=True)
                            chars = list(current_history[history_index])
                            print(f'\r{prompt}{"".join(chars)}', end='', flush=True)
                        elif history_index >= 0:
                            # Возвращаемся к пустому вводу
                            history_index = -1
                            print('\r' + ' ' * (len(prompt) + len(chars)), end='', flush=True)
                            chars = []
                            print(f'\r{prompt}', end='', flush=True)
            else:
                try:
                    char = key.decode('cp866') # Попробуем OEM кодировку Windows
                    # char = key.decode('utf-8') # Или utf-8, если cp866 не подходит
                    if char.isprintable(): # Печатаем только видимые символы
                         chars.append(char)
                         print(char, end='', flush=True)
                         history_index = -1  # Сброс индекса при ручном вводе
                except UnicodeDecodeError:
                    # Игнорируем байты, которые не можем декодировать
                    pass

        except KeyboardInterrupt:
            # Эта обработка нужна, если Ctrl+C нажат во время работы getch()?
            # Лучше передать выше
            raise KeyboardInterrupt

    return "".join(chars)


def ensure_receive_active(processing_event):
    """Гарантирует, что прием включен перед режимами отправки."""
    if not processing_event.is_set():
        processing_event.set()
        print("ℹ️ Прием данных был остановлен и автоматически возобновлен.")

def handle_send_text_loop(ser, settings, receiver_thread, processing_event):
    """Цикл для непрерывной отправки текстовых сообщений."""
    print() # Добавляем пустую строку
    ensure_receive_active(processing_event)
    print("\n--- Режим отправки текста (Esc для возврата в меню; help/init/doctor/history) ---")
    while True:
        message = read_line_msvcrt(prompt="Введите текст: ", history_key="text")
        if message is None: # Нажат Esc в read_line_msvcrt
            break
        if message and ser.is_open: # Отправляем только если не пустая строка
            if handle_runtime_command(message, ser, settings, receiver_thread, processing_event, "text"):
                continue
            if send_text_message(ser, message):
                add_command_to_history("text", message)

def print_runtime_commands_help():
    """Показывает служебные команды, доступные в режимах отправки."""
    print("\n=== 🆘 Служебные команды ===")
    print("  help   - Показать эту справку")
    print("  init   - Показать текущие параметры порта/сессии")
    print("  doctor - Диагностика состояния соединения и потока приема")
    print("  history- Показать историю команд текущего режима")
    print("  esc    - Возврат в меню (также /esc, /menu, /back)")
    print("  Tab    - Автодополнение команд")


def print_init_info(ser, settings):
    """Показывает краткую сводку текущей инициализации порта."""
    print("\n=== ⚙️ Init / Текущая сессия ===")
    print(f"Порт: {ser.port}")
    print(f"Скорость: {settings['baudrate']} бод")
    print(f"Биты данных: {settings['bytesize']}")
    print(f"Паритет: {settings['parity']}")
    print(f"Стоп-биты: {settings['stopbits']}")
    print(f"timeout: {ser.timeout}")
    print(f"inter_byte_timeout: {ser.inter_byte_timeout}")
    print(f"Файл истории: {HISTORY_FILE}")


def run_doctor(ser, receiver_thread, processing_event):
    """Диагностика текущего состояния соединения."""
    print("\n=== 🩺 Doctor ===")
    print(f"Порт открыт: {'да' if ser.is_open else 'нет'}")
    print(f"Порт доступен в системе: {'да' if is_port_currently_available(ser.port) else 'нет'}")
    print(f"Поток приема жив: {'да' if receiver_thread and receiver_thread.is_alive() else 'нет'}")
    print(f"Прием разрешен: {'да' if processing_event.is_set() else 'нет'}")
    try:
        print(f"in_waiting: {ser.in_waiting}")
    except Exception as e:
        print(f"in_waiting: ошибка ({e})")
    try:
        print(f"out_waiting: {ser.out_waiting}")
    except Exception as e:
        print(f"out_waiting: ошибка ({e})")
    print("Doctor: OK")


def handle_runtime_command(
    raw_value: str,
    ser,
    settings,
    receiver_thread,
    processing_event,
    history_key: str | None = None,
) -> bool:
    """Обрабатывает служебные команды в режимах отправки.
    Возвращает True, если команда обработана и отправка не нужна.
    """
    command = raw_value.strip().lower()
    aliases = {
        "/help": "help",
        "/init": "init",
        "/doctor": "doctor",
        "/history": "history",
    }
    command = aliases.get(command, command)

    # Надежный fallback: автодополнение по уникальному префиксу на Enter.
    # Пример: "do" -> "doctor", "his" -> "history".
    known_commands = ("help", "init", "doctor", "history")
    if command not in known_commands:
        prefix_matches = [cmd for cmd in known_commands if cmd.startswith(command)]
        if len(prefix_matches) == 1:
            command = prefix_matches[0]

    if command == "help":
        print_runtime_commands_help()
        return True
    if command == "init":
        print_init_info(ser, settings)
        return True
    if command == "doctor":
        run_doctor(ser, receiver_thread, processing_event)
        return True
    if command == "history":
        show_history_entries(history_key)
        return True
    return False


def handle_send_hex_loop(ser, settings, receiver_thread, processing_event):
    """Цикл для непрерывной отправки HEX данных."""
    print() # Добавляем пустую строку
    ensure_receive_active(processing_event)
    print("\n--- Режим отправки HEX (Esc для возврата в меню; help/init/doctor/history) ---")
    while True:
        hex_data = read_line_msvcrt(prompt="Введите HEX: ", history_key="hex")
        if hex_data is None: # Нажат Esc
            break
        if hex_data and ser.is_open:
            if handle_runtime_command(hex_data, ser, settings, receiver_thread, processing_event, "hex"):
                continue
            if send_hex_data(ser, hex_data):
                add_command_to_history("hex", hex_data)

def handle_send_hex_crc_loop(ser, settings, receiver_thread, processing_event):
    """Цикл для непрерывной отправки HEX данных с CRC."""
    print() # Добавляем пустую строку
    ensure_receive_active(processing_event)
    print("\n--- Режим отправки HEX+CRC (Esc для возврата в меню; help/init/doctor/history) ---")
    while True:
        hex_data = read_line_msvcrt(prompt="Введите HEX для CRC: ", history_key="hex_crc")
        if hex_data is None: # Нажат Esc
            break
        if hex_data and ser.is_open:
            if handle_runtime_command(hex_data, ser, settings, receiver_thread, processing_event, "hex_crc"):
                continue
            if send_hex_data_with_crc(ser, hex_data):
                add_command_to_history("hex_crc", hex_data)

def process_request(request):
    """Логика обработки входящих данных и автогенерации ответа."""
    if request == bytes([0x01, 0x02, 0x03]):
        return bytes([0x01, 0x0C])
    elif request == bytes([0x41]):
        return bytes([0x20, 0x00])
    elif request == bytes([0xAA, 0xBB, 0xCC]):
        return bytes([0xDD, 0xEE])
    elif len(request) == 3 and request[0] == 0x01:
        return bytes([request[0], request[1] + 10])

    return None

def main():
    print(f"VirtualCom v{__version__} (релиз: {__release_date__})")

    # Проверка на наличие функций ввода (должны быть определены для всех ОС)
    if not getch or not kbhit:
        print("❌ Ошибка: Функции ввода не инициализированы.")
        sys.exit(1)

    while True:  # Цикл для повторного выбора порта
        ser = None # Инициализируем ser здесь
        receiver_thread = None # Инициализируем поток здесь
        processing_event = threading.Event() # Событие для управления потоком
        
        try:
            port = select_port()
            if not port:
                print("❌ Выход: последовательный порт не выбран!")
                sys.exit(0)

            # На Windows список портов может устареть (устройство отключили после отображения меню).
            if not is_port_currently_available(port):
                print(f"\n⚠️ Порт {port} больше не доступен. Обновляем список портов...")
                continue

            settings = choose_configuration_mode()
            if settings is None:
                settings = full_port_configuration()

            # Расчет inter_byte_timeout для 20 байт
            bits_per_char = 1 + settings["bytesize"] + settings["stopbits"]
            # Добавляем 1 бит, если есть паритет (кроме PARITY_NONE)
            if settings["parity"] != serial.PARITY_NONE:
                bits_per_char += 1
            
            inter_byte_timeout_calc = 0
            if settings["baudrate"] > 0:
                 # Время передачи 20 символов
                inter_byte_timeout_calc = (bits_per_char * 20) / settings["baudrate"] # Возвращаем 20
                # Добавляем небольшой запас, например, 10% или несколько мс
                inter_byte_timeout_calc += max(0.005, inter_byte_timeout_calc * 0.1) 
            else:
                # Если скорость 0, таймаут не имеет смысла
                 inter_byte_timeout_calc = None

            # Небольшое ограничение сверху, чтобы не ждать слишком долго
            # если скорость очень низкая (например, не более 0.5 сек)
            if inter_byte_timeout_calc is not None and inter_byte_timeout_calc > 0.5:
                 inter_byte_timeout_calc = 0.5
            
            print(f"ℹ️ Рассчитанный inter_byte_timeout: {inter_byte_timeout_calc:.4f} сек" if inter_byte_timeout_calc is not None else "ℹ️ inter_byte_timeout не используется (baudrate=0)")

            try:
                ser = serial.Serial(
                    port=port,
                    baudrate=settings["baudrate"],
                    bytesize=settings["bytesize"],
                    parity=settings["parity"],
                    stopbits=settings["stopbits"],
                    timeout=1, # Таймаут чтения (общий)
                    inter_byte_timeout=inter_byte_timeout_calc # Таймаут между байтами
                )
            except serial.SerialException as e:
                error_text = str(e)
                print(f"\n❌ Ошибка открытия порта {port}: {error_text}")
                print("💡 Возможные причины:")
                print("   - Порт используется другой программой")
                print("   - Недостаточно прав доступа")
                print("   - Устройство было отключено")

                if is_phantom_port_error(error_text):
                    print("💡 Похоже, это фантомный/отключенный COM-порт. Выберите порт снова из обновленного списка.")
                    continue

                if not ask_retry_port_selection():
                    print("\n👋 До свидания!")
                    sys.exit(0)
                continue

            if not ser or not ser.is_open:
                continue

            print(f"\n✅ Соединение установлено: Порт 📌: {ser.port} @ {ser.baudrate} бод @ {ser.bytesize} @ {ser.parity} @ {ser.stopbits}")
            print("\n🔄 VirtualCom готов к работе.")

            # Устанавливаем событие - прием разрешен по умолчанию
            processing_event.set()
            
            # Запускаем поток приема данных, передаем событие
            # receiver_thread = None # Убрано отсюда
            receiver_thread = threading.Thread(target=receive_data, args=(ser, ser.port, processing_event), daemon=True)
            receiver_thread.start()

            try:
                # Показываем меню первый раз
                os.system('cls' if os.name == 'nt' else 'clear')
                # Определяем начальный статус
                initial_status = "▶️ Прием команд активен." if processing_event.is_set() else "⏸ Прием команд остановлен."
                show_menu(status_message=initial_status)
                
                while True:
                    key = None
                    choice = None

                    if os.name == 'nt':
                        if not kbhit():
                            # Проверяем, жив ли еще поток (на случай ошибки в нем)
                            if receiver_thread and not receiver_thread.is_alive():
                                print("\n⚠️ Поток приема данных неожиданно завершился.")
                                break
                            time.sleep(0.05)
                            continue

                        key = getch()
                        if key == b'\x03': # Ctrl+C
                            raise KeyboardInterrupt
                        try:
                            choice = key.decode('ascii')
                        except UnicodeDecodeError:
                            choice = None
                    else:
                        # На macOS/Linux читаем меню мгновенно по одной клавише.
                        key = getch()
                        if key == b'\x03':
                            raise KeyboardInterrupt
                        # ANSI-стрелки начинаются с ESC-последовательности.
                        # Не воспринимаем их как "Esc в меню".
                        if key == b'\x1b':
                            time.sleep(0.01)
                            consumed_escape_sequence = False
                            while kbhit():
                                _ = getch()
                                consumed_escape_sequence = True
                            if consumed_escape_sequence:
                                # Игнорируем стрелки/ANSI-последовательности в главном меню.
                                continue
                        try:
                            choice = key.decode('ascii')
                        except UnicodeDecodeError:
                            choice = None

                    current_status_message = None # Сбрасываем статус перед обработкой

                    if key == b'\x1b': # Esc
                        processing_event.clear() # Останавливаем прием
                        os.system('cls' if os.name == 'nt' else 'clear')
                        current_status_message = "⏸ Прием команд остановлен."

                    # Флаг, нужно ли перерисовать меню после действия
                    redisplay_menu = False

                    if choice == '1':
                        handle_send_text_loop(ser, settings, receiver_thread, processing_event)
                        redisplay_menu = True
                    elif choice == '2':
                        handle_send_hex_loop(ser, settings, receiver_thread, processing_event)
                        redisplay_menu = True
                    elif choice == '3':
                        handle_send_hex_crc_loop(ser, settings, receiver_thread, processing_event)
                        redisplay_menu = True
                    elif choice == '4': # Остановить прием
                        processing_event.clear()
                        current_status_message = "⏸ Прием команд остановлен."
                        redisplay_menu = True
                    elif choice == '5': # Продолжить прием
                        processing_event.set() 
                        if ser.is_open:
                            try:
                                ser.reset_input_buffer() # Очищаем буфер приема
                                current_status_message = "▶️ Прием команд возобновлен (буфер очищен)."
                            except Exception as e:
                                print(f"\n⚠️ Ошибка при очистке буфера: {e}")
                                current_status_message = "▶️ Прием команд возобновлен (ошибка очистки буфера)."
                        else:
                            current_status_message = "▶️ Прием команд возобновлен (порт закрыт?)."
                        redisplay_menu = True
                    elif choice == '6': # Очистить экран
                        os.system('cls' if os.name == 'nt' else 'clear')
                        # Статус нужно определить заново, так как экран очищен
                        current_status_message = "▶️ Прием команд активен." if processing_event.is_set() else "⏸ Прием команд остановлен."
                        redisplay_menu = True
                    elif choice == '7': # Выход
                        print("\n👋 До свидания!")
                        break # Выход из внутреннего цикла
                    elif choice == '8': # История команд
                        manage_command_history()
                        current_status_message = "🕘 История команд обновлена."
                        redisplay_menu = True
                    else:
                        # Если введен Esc как команда в line-mode
                        if key == b'\x1b': 
                            redisplay_menu = True # Нужно перерисовать меню со статусом

                    # Перерисовываем меню, если нужно (после действия или Esc)
                    if redisplay_menu:
                        # Определяем статус, если он еще не определен (например, после ввода данных)
                        if not current_status_message:
                            current_status_message = "▶️ Прием команд активен." if processing_event.is_set() else "⏸ Прием команд остановлен."
                        show_menu(status_message=current_status_message)

                    # Проверяем, жив ли еще поток (на случай ошибки в нем)
                    if receiver_thread and not receiver_thread.is_alive():
                        print("\n⚠️ Поток приема данных неожиданно завершился.")
                        break # Выходим из внутреннего цикла, чтобы перейти к finally
                        
                    time.sleep(0.05)

            except KeyboardInterrupt:
                print("\n⏹ Остановка эмуляции (Ctrl+C)")
            finally:
                # Сначала останавливаем прием, чтобы поток мог завершиться
                processing_event.set() # Устанавливаем на случай, если был clear
                safe_close_serial(ser, port)
                # Даем потоку шанс завершиться после закрытия порта
                if receiver_thread and receiver_thread.is_alive():
                    receiver_thread.join(timeout=1.0)
                
                # Повторная проверка и сообщение, если поток все еще жив
                if receiver_thread and receiver_thread.is_alive():
                    print("⚠️ Поток приема данных не завершился корректно после закрытия порта.")

            break  # Выходим из внешнего цикла (повторный выбор порта)

        except KeyboardInterrupt:
            print("\n🚪 Завершение работы по Ctrl + C")
            # Убеждаемся, что событие установлено перед выходом, чтобы поток не завис на wait
            if 'processing_event' in locals(): processing_event.set() 
            safe_close_serial(ser)
            sys.exit(0)
        except Exception as e:
            print(f"\n❌ Неожиданная ошибка: {e}")
            # Убеждаемся, что событие установлено перед выходом/повтором
            if 'processing_event' in locals(): processing_event.set()
            safe_close_serial(ser)
            retry = input("\nПопробовать снова? (y/n): ").lower().strip()
            if retry != 'y':
                sys.exit(1)
            continue

if __name__ == "__main__":
    main()
