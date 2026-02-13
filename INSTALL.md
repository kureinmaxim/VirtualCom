# INSTALL.md — установка и сборка VirtualCom (Windows)

Этот документ описывает полный цикл:

1. локальный запуск `vicom.py`,
2. устранение ошибки `pip is not recognized`,
3. сборка `exe` через PyInstaller,
4. сборка установщика через Inno Setup.

---

## 1) Требования

- Windows 10/11
- Python 3.13+ (желательно установить с опцией **Add Python to PATH**)
- Inno Setup 6 (для создания инсталлятора)

Проект:
- основной файл: `vicom.py`
- зависимости: `requirements.txt`
- скрипт сборки: `build_installer.bat`
- скрипт Inno Setup: `installer.iss`

---

## 2) Быстрый запуск проекта из исходников

Откройте PowerShell и выполните:

```powershell
cd C:\Project\ProjectPython\VirtualCom
python -m venv venv
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe vicom.py
```

---

## 3) Если `pip` не распознается

Симптом:

```text
pip: The term 'pip' is not recognized ...
```

Причина: `pip` не добавлен в PATH (или активировано другое окружение).

Решение: всегда ставьте пакеты через интерпретатор Python:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Если в проекте используется виртуальное окружение, предпочтительно:

```powershell
venv\Scripts\python.exe -m pip install -r requirements.txt
```

---

## 4) Полная сборка EXE + установщика (рекомендуемый способ)

Самый простой путь — запустить готовый скрипт:

```powershell
cd C:\Project\ProjectPython\VirtualCom
.\build_installer.bat
```

Скрипт выполняет автоматически:

1. проверку Python,
2. создание `venv` (если отсутствует),
3. установку `requirements.txt` и `pyinstaller`,
4. сборку `dist\VirtualCom.exe`,
5. запуск `ISCC.exe` и сборку инсталлятора.

Результат:

- `dist\VirtualCom.exe` — собранное приложение
- `output\VirtualCom_Setup_1.0.0.exe` — готовый инсталлятор

---

## 5) Ручная сборка (если нужно контролировать каждый шаг)

### 5.1 Собрать EXE через PyInstaller

```powershell
cd C:\Project\ProjectPython\VirtualCom
python -m venv venv
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
venv\Scripts\python.exe -m PyInstaller --clean --noconfirm --onefile --console --name VirtualCom vicom.py
```

Проверьте, что появился файл:

- `dist\VirtualCom.exe`

### 5.2 Собрать инсталлятор через Inno Setup

Вариант A: через GUI Inno Setup
- открыть `installer.iss`
- нажать **Compile**

Вариант B: через командную строку:

```powershell
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "C:\Project\ProjectPython\VirtualCom\installer.iss"
```

Если Inno Setup установлен в другой каталог, укажите фактический путь к `ISCC.exe`.

---

## 6) Проверка результата

После успешной сборки должно быть:

- `dist\VirtualCom.exe`
- `output\VirtualCom_Setup_1.0.0.exe`

Проверьте установщик:

1. запустить `output\VirtualCom_Setup_1.0.0.exe`,
2. установить программу,
3. запустить ярлык `VirtualCom`,
4. убедиться, что приложение открывается и видит COM-порты.

---

## 7) Типовые ошибки и решения

### Ошибка: `Source file "...dist\VirtualCom.exe" does not exist`

Причина: EXE ещё не собран.

Решение:

1. сначала собрать через PyInstaller (`build_installer.bat` или шаг 5.1),
2. затем компилировать `installer.iss`.

---

### Ошибка: `pip is not recognized`

Решение: использовать `python -m pip ...` или `venv\Scripts\python.exe -m pip ...`.

---

### Ошибка: `ISCC.exe not found`

Причина: Inno Setup не установлен или установлен не по стандартному пути.

Решение:

1. установить Inno Setup 6,
2. проверить наличие `ISCC.exe`,
3. при ручном запуске указывать корректный путь.

---

### Ошибка PowerShell при активации venv (`Activate.ps1` blocked)

Если нужно именно активировать окружение, временно разрешите выполнение:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

Но активация не обязательна: можно всегда запускать через `venv\Scripts\python.exe`.

---

## 8) Рекомендуемый рабочий сценарий

Для ежедневной работы:

```powershell
cd C:\Project\ProjectPython\VirtualCom
venv\Scripts\python.exe vicom.py
```

Для релиза:

```powershell
cd C:\Project\ProjectPython\VirtualCom
.\build_installer.bat
```

---

## 9) Что лежит в проекте для установки

- `requirements.txt` — зависимости Python
- `build_installer.bat` — автоматическая сборка релиза
- `installer.iss` — конфигурация Inno Setup
- `INSTALL.md` — этот документ

