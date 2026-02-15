# VERSION MANAGEMENT (VirtualCom)

Этот документ описывает управление версией для текущего проекта `VirtualCom`.

---

## Источник правды

Единственный источник версии и даты релиза:
- `pyproject.toml`

```toml
[project]
version = "X.Y.Z"

[tool.virtualcom]
release_date = "DD.MM.YYYY"
```

Важно:
- версию не берем из локальных/пользовательских конфигов;
- перед релизом сначала обновляем `pyproject.toml`, потом синхронизируем derived-файлы.

---

## Какие файлы синхронизируем

Скрипт `scripts/update_version.py` синхронизирует:
- `version_info.py`  
  (`__version__`, `__release_date__`)
- `installer.iss`  
  (`#define MyAppVersion "X.Y.Z"`)
- `README.md`  
  (строка `Текущая версия`)

Дополнительно:
- `build_installer_mac.sh` читает версию из `pyproject.toml` и записывает ее в `CFBundleVersion` / `CFBundleShortVersionString`.

---

## Команды `scripts/update_version.py`

Общий формат:

```text
python3 scripts/update_version.py <command> [args]
```

Доступные команды:

```text
status                    Показать текущую версию и статус синхронизации
sync [VERSION]            Синхронизировать все derived-файлы (release_date = сегодня)
bump patch                1.1.0 -> 1.1.1
bump minor                1.1.0 -> 1.2.0
bump major                1.1.0 -> 2.0.0
release [VERSION]         Сейчас эквивалентно sync + сообщение (без auto commit/push)
```

---

## Быстрые команды

### macOS / Linux

```bash
python3 scripts/update_version.py status | cat
python3 scripts/update_version.py bump patch | cat
python3 scripts/update_version.py sync | cat
```

### Windows (PowerShell)

```powershell
python scripts\update_version.py status
python scripts\update_version.py bump patch
python scripts\update_version.py sync
```

---

## Рекомендуемый workflow релиза

1. Проверить текущее состояние:
   - `python3 scripts/update_version.py status | cat`
2. Поднять версию:
   - `python3 scripts/update_version.py bump patch | cat`
   - или `python3 scripts/update_version.py sync 1.2.0 | cat`
3. Пересобрать инсталляторы:
   - macOS: `bash build_installer_mac.sh | cat`
   - Windows: `build_installer.bat`
4. Проверить при запуске приложения строку версии:
   - `VirtualCom vX.Y.Z (релиз: DD.MM.YYYY)`
5. После проверки — commit/tag/release по обычному git-процессу.

---

## Troubleshooting

### Версия в приложении не совпадает

Проверьте:
- `pyproject.toml` (source of truth),
- `python3 scripts/update_version.py status | cat`,
- что установлен свежий инсталлятор (новый `.dmg` / `.exe`), а не старый.

### В macOS `.app` неправильная версия в свойствах

Проверьте, что сборка была после обновления версии:
- `bash build_installer_mac.sh | cat`

Скрипт должен вывести строку вида:
- `ℹ️ Версия сборки: X.Y.Z (релиз: DD.MM.YYYY)`
