import serial
import serial.tools.list_ports
import sys
import threading
import time
import os # Для очистки экрана

# Импорт msvcrt только для Windows
if os.name == 'nt':
    import msvcrt
else:
    # Для других ОС пока не реализовано
    msvcrt = None

# Значения по умолчанию
DEFAULT_SETTINGS = {
    "baudrate": 38400,
    "bytesize": serial.EIGHTBITS,
    "parity": serial.PARITY_NONE,
    "stopbits": serial.STOPBITS_ONE
}

POLYNOMIAL = 0xA001  # Стандартный полином для CRC16-MODBUS

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
            print(f"\n{port_name} 📥 Получен запрос HEX: {' '.join(f'{b:02X}' for b in request)}")
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
                print(f"📤 Отправлен ответ: {' '.join(f'{b:02X}' for b in response)}")
            # Выводим приглашение снова после получения данных (без \n)
            print("Меню (Esc) или Выход (Ctrl+C): ", end='', flush=True)

        except serial.SerialException as serial_err:
            # Обработка ошибок, связанных с портом (например, отключение устройства)
            print(f"\n⚠️ Ошибка порта в потоке приема: {serial_err}")
            break # Выход из цикла потока
        except Exception as e:
            print(f"\n⚠️ Ошибка при приеме данных: {e}")
            # Можно продолжить или выйти в зависимости от типа ошибки
            time.sleep(0.1)

def send_hex_data(ser, hex_string: str):
    """Отправка HEX данных в порт"""
    try:
        hex_string = hex_string.replace(" ", "")
        if not all(c in '0123456789ABCDEFabcdef' for c in hex_string):
            print("❌ Ошибка: неверный формат HEX данных")
            return
        
        data = bytes.fromhex(hex_string)
        ser.write(data)
        print(f"📤 Отправлено (HEX): {' '.join(f'{b:02X}' for b in data)}")
    except ValueError:
        print("❌ Ошибка: неверный формат HEX данных")

def send_hex_data_with_crc(ser, hex_string: str):
    """Отправка HEX данных в порт с добавлением CRC16"""
    try:
        hex_string = hex_string.replace(" ", "")
        if not all(c in '0123456789ABCDEFabcdef' for c in hex_string):
            print("❌ Ошибка: неверный формат HEX данных")
            return
        
        data = bytes.fromhex(hex_string)
        crc = calculate_crc16(data)
        
        # Добавляем CRC к данным (младший байт первый)
        final_data = data + bytes([crc & 0xFF, (crc >> 8) & 0xFF])
        
        ser.write(final_data)
        print(f"📤 Отправлено (HEX+CRC): {' '.join(f'{b:02X}' for b in data)} | CRC: {crc & 0xFF:02X} {(crc >> 8) & 0xFF:02X}")
        
    except ValueError:
        print("❌ Ошибка: неверный формат HEX данных")

def send_text_message(ser, message: str):
    """Отправка текстового сообщения в порт"""
    data = message.encode('utf-8')
    ser.write(data)
    print(f"📤 Отправлено (текст): {message}")

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
    if status_message:
        print(f"\n{status_message}") 
    print("Выберите действие (1-7), Меню (Esc) или Выход (Ctrl+C): ", end='', flush=True)

def list_available_ports():
    """Возвращает список доступных COM-портов и выводит их на экран, отсортированных по номеру."""
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("❌ Нет доступных последовательных портов!")
        return []

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
            selected_index = int(input("\nВведите номер порта: ")) - 1
            if 0 <= selected_index < len(ports):
                return ports[selected_index].device
            print("⚠️ Ошибка: введите корректный номер порта!")
        except ValueError:
            print("⚠️ Ошибка: введите число!")

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
        if msvcrt and msvcrt.kbhit(): # Используем msvcrt, если доступен
            key = msvcrt.getch()
            if key == b'1':
                print("1") # Отображаем выбор
                return None # Ручная настройка
            elif key == b'2':
                print("2") # Отображаем выбор
                return DEFAULT_SETTINGS # Настройки по умолчанию
            elif key == b'\x03': # Ctrl+C
                raise KeyboardInterrupt
            # Игнорируем другие клавиши
        elif not msvcrt: # Если msvcrt недоступен, используем input
             # Перемещаем сюда запрос input из старой версии
            choice = input().strip()
            if choice == '1':
                return None
            elif choice == '2':
                return DEFAULT_SETTINGS
            else:
                print("⚠️ Некорректный выбор. Пожалуйста, введите 1 или 2.")
                print("Выберите режим настройки (1 или 2): ", end='', flush=True)
                
        # Небольшая пауза, чтобы не загружать ЦП в ожидании нажатия
        time.sleep(0.05) 

def choose_option(prompt, options):
    """Позволяет выбрать один из предложенных вариантов (мгновенный выбор по цифре в Windows)."""
    print(f"\n{prompt}")
    num_options = len(options)
    for i, option in enumerate(options, start=1):
        print(f"  {i}. {option}")

    print("Выберите номер: ", end='', flush=True)

    while True:
        if msvcrt and msvcrt.kbhit():
            key = msvcrt.getch()
            try:
                digit = key.decode('ascii')
                if '1' <= digit <= str(min(num_options, 9)): # Проверяем цифру от 1 до 9 (и не больше кол-ва опций)
                    print(digit) # Отображаем выбор
                    selected_index = int(digit) - 1
                    return options[selected_index]
                elif key == b'\x03': # Ctrl+C
                    raise KeyboardInterrupt
                # Игнорируем другие клавиши (включая цифры > num_options или 0)
            except UnicodeDecodeError:
                if key == b'\x03': # Ctrl+C
                    raise KeyboardInterrupt
                # Игнорируем не-ASCII клавиши
                pass
            except KeyboardInterrupt:
                raise # Передаем исключение выше
                
        elif not msvcrt:
            # Fallback на стандартный input для не-Windows систем
            try:
                choice_str = input() # Читаем ввод пользователя
                selected_index = int(choice_str) - 1
                if 0 <= selected_index < num_options:
                    return options[selected_index]
                else:
                    print("⚠️ Ошибка: выберите корректный номер!")
                    print("Выберите номер: ", end='', flush=True)
            except ValueError:
                print("⚠️ Ошибка: введите число!")
                print("Выберите номер: ", end='', flush=True)
            except KeyboardInterrupt:
                raise

        # Небольшая пауза
        time.sleep(0.05)

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

def read_line_msvcrt(prompt=""):
    """Читает строку ввода посимвольно с использованием msvcrt (только Windows).
    
    Поддерживает Backspace, завершает ввод по Enter.
    Возвращает None при нажатии Esc, пустую строку при Ctrl+C.
    """
    if not msvcrt:
        try:
            # Возврат к стандартному input, если msvcrt недоступен
            return input(prompt)
        except KeyboardInterrupt:
            print("\nОперация прервана.")
            return "" # Возвращаем пустую строку при прерывании в input
        
    print(prompt, end='', flush=True)
    chars = []
    while True:
        try:
            key = msvcrt.getch()
            
            if key == b'\r': # Enter
                print() # Перевод строки после ввода
                break
            elif key == b'\x1b': # Esc
                print(" [Esc]") # Показываем, что нажали Esc
                return None # Возвращаем None для выхода из цикла
            elif key == b'\x08': # Backspace
                if chars:
                    chars.pop()
                    # Стереть символ с консоли: \b (назад) + ' ' (пробел) + \b (назад)
                    print('\b \b', end='', flush=True)
            elif key == b'\x03': # Ctrl+C
                 # Не прерываем здесь, чтобы позволить основному циклу обработать
                 print(" [Ctrl+C]")
                 raise KeyboardInterrupt 
            else:
                try:
                    char = key.decode('cp866') # Попробуем OEM кодировку Windows
                    # char = key.decode('utf-8') # Или utf-8, если cp866 не подходит
                    if char.isprintable(): # Печатаем только видимые символы
                         chars.append(char)
                         print(char, end='', flush=True)
                except UnicodeDecodeError:
                    # Игнорируем байты, которые не можем декодировать
                    pass 
                    
        except KeyboardInterrupt:
            # Эта обработка нужна, если Ctrl+C нажат во время работы getch()?
            # Лучше передать выше
            raise KeyboardInterrupt
            
    return "".join(chars)

def handle_send_text_loop(ser):
    """Цикл для непрерывной отправки текстовых сообщений."""
    print() # Добавляем пустую строку
    print("\n--- Режим отправки текста (Esc для возврата в меню) ---")
    while True:
        message = read_line_msvcrt(prompt="Введите текст: ")
        if message is None: # Нажат Esc в read_line_msvcrt
            break
        if message and ser.is_open: # Отправляем только если не пустая строка
            send_text_message(ser, message)

def handle_send_hex_loop(ser):
    """Цикл для непрерывной отправки HEX данных."""
    print() # Добавляем пустую строку
    print("\n--- Режим отправки HEX (Esc для возврата в меню) ---")
    while True:
        hex_data = read_line_msvcrt(prompt="Введите HEX: ")
        if hex_data is None: # Нажат Esc
            break
        if hex_data and ser.is_open:
            send_hex_data(ser, hex_data)

def handle_send_hex_crc_loop(ser):
    """Цикл для непрерывной отправки HEX данных с CRC."""
    print() # Добавляем пустую строку
    print("\n--- Режим отправки HEX+CRC (Esc для возврата в меню) ---")
    while True:
        hex_data = read_line_msvcrt(prompt="Введите HEX для CRC: ")
        if hex_data is None: # Нажат Esc
            break
        if hex_data and ser.is_open:
            send_hex_data_with_crc(ser, hex_data)

def process_request(request):
    """Логика обработки запросов."""
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
    # Проверка, доступен ли msvcrt (только Windows)
    if not msvcrt:
        print("❌ Ошибка: Мгновенное чтение клавиш поддерживается только в Windows.")
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
            print("\n🔄 Эмулятор готов к работе.")

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
                    if msvcrt.kbhit():
                        key = msvcrt.getch()
                        
                        current_status_message = None # Сбрасываем статус перед обработкой

                        if key == b'\x03': # Ctrl+C
                            raise KeyboardInterrupt
                        elif key == b'\x1b': # Esc
                            processing_event.clear() # Останавливаем прием
                            os.system('cls' if os.name == 'nt' else 'clear')
                            current_status_message = "⏸ Прием команд остановлен."
                            # show_menu(status_message="⏸ Прием команд остановлен.") # Вызов show_menu будет ниже
                            # continue # Убираем continue, чтобы show_menu вызвался один раз
                        
                        try:
                            choice = key.decode('ascii')
                        except UnicodeDecodeError:
                            choice = None

                        # Флаг, нужно ли перерисовать меню после действия
                        redisplay_menu = False

                        if choice == '1':
                            handle_send_text_loop(ser)
                            redisplay_menu = True
                        elif choice == '2':
                            handle_send_hex_loop(ser)
                            redisplay_menu = True
                        elif choice == '3':
                            handle_send_hex_crc_loop(ser)
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
                        else:
                            # Если нажата не цифра и не спец. клавиша, но это был Esc
                            if key == b'\x1b': 
                                redisplay_menu = True # Нужно перерисовать меню со статусом
                            # Иначе игнорируем
                            pass 

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
                if ser and ser.is_open:
                    ser.close()
                    print(f"\n🔌 Порт {port} закрыт.")
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
            if ser and ser.is_open: ser.close()
            sys.exit(0)
        except Exception as e:
            print(f"\n❌ Неожиданная ошибка: {e}")
            # Убеждаемся, что событие установлено перед выходом/повтором
            if 'processing_event' in locals(): processing_event.set()
            if ser and ser.is_open: ser.close()
            retry = input("\nПопробовать снова? (y/n): ").lower().strip()
            if retry != 'y':
                sys.exit(1)
            continue

if __name__ == "__main__":
    main()
