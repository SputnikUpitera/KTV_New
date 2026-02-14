# Архитектура OperatorKTV

## Обзор системы

OperatorKTV - распределённая система для автоматизированного управления воспроизведением медиафайлов, состоящая из двух основных компонентов:

1. **Windows GUI Client** - графический интерфейс оператора
2. **Linux Daemon** - служба воспроизведения медиафайлов

```
┌─────────────────────┐
│  Windows Operator   │
│    (PyQt6 GUI)      │
└──────────┬──────────┘
           │ SSH/SFTP
           │ Port 22
           ▼
┌─────────────────────┐
│   Linux Server      │
│  ┌───────────────┐  │
│  │ KTV Daemon    │  │
│  │ (Port 9999)   │  │
│  └───────┬───────┘  │
│          │          │
│          ▼          │
│  ┌───────────────┐  │
│  │ MPV Player    │  │
│  └───────────────┘  │
└─────────────────────┘
```

## Компоненты Windows клиента

### 1. GUI Layer (`operator_ktv/gui/`)

#### MainWindow
- Основное окно приложения (480x480px)
- Темная тема Fusion
- Управление подключением и меню
- Интеграция всех компонентов

#### MoviesTab
- Дерево расписания (12 месяцев → дни)
- Drag-and-drop для добавления файлов
- Визуализация расписания
- Управление статусом (enable/disable)
- Цветовое кодирование

#### ClipsTab
- Список плейлистов
- Управление активным плейлистом
- Drag-and-drop для добавления в плейлист
- Создание/удаление плейлистов

#### SSHTerminalWidget
- Встроенная SSH консоль
- Эмуляция терминала
- История команд
- ANSI escape codes поддержка

#### Dialogs
- `ConnectionDialog` - настройка SSH подключения
- `ScheduleDialog` - выбор времени воспроизведения

### 2. Network Layer (`operator_ktv/network/`)

#### SSHClient
Класс для работы с SSH/SFTP:
- `connect()` - подключение к удалённой системе
- `execute_command()` - выполнение команд
- `upload_file()` - загрузка файлов с прогрессом
- `download_file()` - скачивание файлов
- `delete_file()` - удаление файлов
- `create_directory()` - создание папок

#### CommandClient
Протокол команд для daemon API:
- Отправка JSON команд через socket
- Методы для каждой операции:
  - `add_schedule()` - добавить в расписание
  - `remove_schedule()` - удалить из расписания
  - `toggle_schedule()` - включить/выключить
  - `list_schedules()` - список расписаний
  - `create_playlist()` - создать плейлист
  - `set_active_playlist()` - активировать плейлист
  - `get_status()` - статус daemon

### 3. Installer Layer (`operator_ktv/installer/`)

#### RemoteChecker
Проверка совместимости системы:
- Определение ОС и архитектуры
- Проверка наличия Python, MPV
- Проверка sudo прав
- Проверка свободного места
- Проверка статуса daemon

#### PackageDeployer
Развёртывание offline пакета:
- Передача tar.gz через SFTP
- Распаковка на удалённой системе
- Запуск install.sh с sudo
- Отслеживание прогресса
- Обработка ошибок

#### InstallationVerifier
Верификация установки:
- Проверка файлов daemon
- Проверка systemd сервиса
- Проверка портов
- Проверка базы данных
- Проверка медиа директорий

### 4. Models Layer (`operator_ktv/models/`)

#### ScheduleItem
```python
@dataclass
class ScheduleItem:
    id: int
    month: int
    day: int
    hour: int
    minute: int
    filepath: str
    filename: str
    enabled: bool
    category: str
```

#### Playlist
```python
@dataclass
class Playlist:
    id: int
    name: str
    folder_path: str
    active: bool
```

## Компоненты Linux daemon

### 1. Core Daemon (`remote_player/daemon.py`)

Основной процесс, координирующий все компоненты:

```python
class KTVDaemon:
    - Загрузка конфигурации
    - Инициализация компонентов
    - Регистрация API handlers
    - Обработка сигналов (SIGTERM, SIGINT)
    - Graceful shutdown
```

Жизненный цикл:
1. Загрузка конфигурации из `/etc/ktv/config.json`
2. Инициализация логирования
3. Создание Database, Player, APIServer
4. Создание Scheduler, PlaylistManager, TimeController
5. Запуск всех компонентов
6. Основной цикл
7. Graceful shutdown при получении сигнала

### 2. API Server (`remote_player/api_server.py`)

TCP socket сервер на порту 9999:

```python
class APIServer:
    - TCP socket сервер
    - JSON протокол (request/response)
    - Многопоточная обработка клиентов
    - Регистрация handlers для команд
```

Протокол:
```json
// Request
{
    "command": "add_schedule",
    "params": {
        "month": 12,
        "day": 31,
        "hour": 23,
        "minute": 59,
        "filepath": "/path/to/file.mp4",
        "filename": "file.mp4"
    }
}

// Response
{
    "success": true,
    "result": {
        "schedule_id": 123
    }
}
```

### 3. Player (`remote_player/player.py`)

Обёртка над MPV:

```python
class Player:
    - Запуск MPV через subprocess
    - Контроль воспроизведения
    - Мониторинг процесса
    - Callback при окончании
```

Функции:
- `play(filepath)` - начать воспроизведение
- `stop()` - остановить воспроизведение
- `get_status()` - получить статус
- `is_busy()` - проверка занятости

### 4. Scheduler (`remote_player/scheduler.py`)

Планировщик на основе APScheduler:

```python
class Scheduler:
    - BackgroundScheduler
    - CronTrigger для каждого расписания
    - Динамическое добавление/удаление джобов
    - Приоритет над плейлистами
```

Логика:
1. Загрузка расписаний из БД
2. Создание cron trigger для каждого
3. При срабатывании:
   - Остановка плейлиста
   - Воспроизведение файла
   - Callback для возобновления плейлиста

### 5. Playlist Manager (`remote_player/playlist_manager.py`)

Управление непрерывным воспроизведением:

```python
class PlaylistManager:
    - Сканирование папок с видео
    - Непрерывное воспроизведение (loop)
    - Пауза при scheduled playback
    - Возобновление после scheduled
```

Логика:
1. Загрузка активного плейлиста из БД
2. Сканирование файлов в папке
3. Основной цикл:
   - Проверка статуса (paused?)
   - Проверка player (busy?)
   - Воспроизведение следующего файла
   - Ожидание окончания
   - Переход к следующему (loop)

### 6. Time Controller (`remote_player/time_controller.py`)

Контроль часов работы:

```python
class TimeController:
    - Cron jobs для 6:00 и 22:00
    - Контроль broadcasting статуса
    - Управление playlist manager
```

Логика:
- 6:00 → `start_broadcasting()` → resume playlist
- 22:00 → `stop_broadcasting()` → pause playlist

### 7. Database (`remote_player/storage/database.py`)

SQLite база данных:

```sql
-- Расписание
CREATE TABLE schedule (
    id INTEGER PRIMARY KEY,
    month INTEGER,
    day INTEGER,
    hour INTEGER,
    minute INTEGER,
    filepath TEXT,
    filename TEXT,
    enabled INTEGER,
    category TEXT
);

-- Плейлисты
CREATE TABLE playlists (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE,
    folder_path TEXT,
    active INTEGER
);

-- Настройки
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

## Offline Package

### Структура пакета

```
ktv_offline_package.tar.gz
├── install.sh              # Мастер-установщик
├── packages/               # .deb пакеты
│   ├── mpv_*.deb
│   ├── libmpv1_*.deb
│   └── dependencies/
├── python_wheels/          # Python .whl файлы
│   ├── APScheduler-*.whl
│   └── ...
├── daemon/                 # Исходники daemon
├── systemd/               # Systemd unit
└── config/                # Конфигурация
```

### Процесс сборки

`build_offline_package.py`:
1. Скачивание .deb пакетов с Ubuntu репозитория
2. Скачивание .whl файлов с PyPI
3. Копирование исходников daemon
4. Создание install.sh
5. Создание systemd unit файла
6. Упаковка в tar.gz

### Процесс установки

`install.sh`:
1. Проверка прав (root)
2. Проверка архитектуры
3. Установка .deb пакетов
4. Создание пользователя `ktv`
5. Создание структуры папок
6. Создание Python venv
7. Установка .whl пакетов
8. Копирование daemon файлов
9. Установка systemd service
10. Запуск daemon

## Потоки данных

### Добавление файла в расписание

```
1. User: Drag file to day
   ↓
2. MoviesTab: Show time dialog
   ↓
3. User: Select time (19:00)
   ↓
4. MoviesTab: upload_and_schedule()
   ↓
5. SSHClient: upload_file() via SFTP
   ↓
6. Linux: File saved to /opt/ktv/media/movies/
   ↓
7. CommandClient: add_schedule()
   ↓
8. APIServer: Receive JSON command
   ↓
9. Daemon: Handler add_schedule
   ↓
10. Database: INSERT INTO schedule
    ↓
11. Scheduler: reload_schedules()
    ↓
12. APScheduler: Add cron job
```

### Воспроизведение по расписанию

```
1. APScheduler: Trigger at 19:00
   ↓
2. Scheduler: _execute_scheduled_playback()
   ↓
3. PlaylistManager: pause()
   ↓
4. Player: stop() current
   ↓
5. Player: play(scheduled_file)
   ↓
6. MPV: Start playback
   ↓
7. Player: Monitor process
   ↓
8. MPV: Playback ends
   ↓
9. Player: Callback
   ↓
10. PlaylistManager: resume()
    ↓
11. Player: play(playlist_file)
```

## Безопасность

### Уровень передачи
- SSH шифрование (RSA/AES)
- Аутентификация по паролю или ключу
- SFTP для передачи файлов

### Уровень приложения
- Валидация всех входных данных
- SQL параметризованные запросы
- Проверка путей к файлам
- Ограничение прав daemon (пользователь ktv)

### Уровень системы
- Systemd изоляция процесса
- Ограниченные права файловой системы
- Логирование всех операций

## Масштабируемость

### Текущие ограничения
- Один Windows клиент → один Linux сервер
- Последовательная обработка команд
- Локальное хранилище файлов

### Возможные улучшения
- Множественные клиенты через аутентификацию
- Очередь команд для параллельной обработки
- Распределённое хранилище (NFS, SMB)
- Кластеризация серверов
- Web интерфейс

## Производительность

### Оптимизации
- Асинхронная передача файлов
- Кеширование расписания на клиенте
- Индексы в базе данных
- Предзагрузка следующего файла плейлиста

### Метрики
- Задержка команды: ~100-500ms
- Скорость передачи: зависит от сети (обычно 10-100 MB/s)
- Потребление ресурсов Linux:
  - RAM: ~50-100 MB (daemon)
  - CPU: ~1-5% (idle), ~20-40% (playback)

## Мониторинг и отладка

### Логи

Windows:
- `%USERPROFILE%\.operatorktv\operator_ktv.log`

Linux:
- `/var/log/ktv/daemon.log` - daemon логи
- `journalctl -u ktv-daemon` - systemd логи

### Метрики

Доступны через `get_status()` API:
- Статус daemon
- Статус player (playing/stopped)
- Текущий файл
- Активный плейлист
- Broadcast статус

### Отладка

Windows:
```python
logging.basicConfig(level=logging.DEBUG)
```

Linux:
```bash
/opt/ktv/venv/bin/python /opt/ktv/daemon.py --debug
```

## Тестирование

### Компоненты для тестирования

1. **Unit тесты** (рекомендуется добавить):
   - Database операции
   - Scheduler логика
   - Player управление
   - API протокол

2. **Integration тесты**:
   - SSH подключение
   - Передача файлов
   - Команды daemon
   - Полный цикл добавления файла

3. **Manual тесты**:
   - GUI юзабилити
   - Drag-and-drop
   - Offline установка
   - Различные сценарии использования

## Зависимости

### Windows
- Python 3.10+
- PyQt6 6.6.1
- paramiko 3.4.0
- cryptography 41.0.7

### Linux
- Python 3.8+ (входит в Ubuntu 20.04)
- MPV 0.32+
- APScheduler 3.10.4
- SQLite3 (встроен в Python)

## Развёртывание

### Development
```bash
# Windows
python operator_ktv/main.py

# Linux (manual)
cd /opt/ktv
source venv/bin/activate
python daemon.py
```

### Production
```bash
# Windows: PyInstaller
pyinstaller operator_ktv/main.py --onefile --windowed

# Linux: Systemd service (автоматически)
sudo systemctl start ktv-daemon
```

## Лицензирование

Proprietary - все права защищены.

## Версионирование

Текущая версия: **1.0.0**

Семантическое версионирование:
- MAJOR: несовместимые изменения API
- MINOR: новый функционал (совместимо)
- PATCH: исправления ошибок
