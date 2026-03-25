# OperatorKTV

Система удалённого управления воспроизведением медиафайлов.

Проект состоит из двух частей:
- `operator_ktv` - Windows GUI-клиент на `PyQt6`
- `remote_player` - Linux daemon для воспроизведения и планирования

Клиент подключается к Linux-машине по `SSH/SFTP`, загружает файлы, управляет расписанием и плейлистами, а также может установить daemon на удалённую систему.

## Актуальное состояние

- Плеер на Linux: `VLC`
- API daemon: `localhost:8888`
- Фильмы по расписанию хранятся в `~/oktv/MM/DD/HH-MM/`
- Клиповые плейлисты хранятся в `~/oktv/clips/`
- Конфигурация daemon: `/etc/ktv/config.json`
- Сервис Linux: `ktv-daemon`

## Возможности

- Добавление видеофайлов в расписание через drag-and-drop
- Воспроизведение по месяцу, дню и времени
- Изменение времени фильма и отдельное включение/отключение элементов расписания
- Создание и активация плейлистов для фонового воспроизведения
- Автоматическое переключение между плейлистом и запланированным контентом
- Встроенная SSH-консоль
- Проверка удалённой системы и верификация установки
- Автоматическая установка daemon на Linux через offline package

## Как работает воспроизведение

- Время вещания задаётся параметрами `broadcast_start` и `broadcast_end`
- Вне окна вещания фоновый плейлист не воспроизводится
- Запланированные файлы тоже не запускаются вне окна вещания
- Если на одну и ту же минуту назначено несколько файлов, они ставятся в очередь и воспроизводятся последовательно
- После завершения запланированного контента фоновый плейлист возобновляется

## Требования

### Windows-клиент

- Windows 10/11
- Python 3.10+

### Linux-система

- Ubuntu 20.04+ или совместимая Debian/Ubuntu-система
- Архитектура `x86_64` / `amd64`
- Доступ по `SSH`
- Права `sudo`
- Установленный `VLC`

Важно: offline package не включает системные пакеты `VLC`. Перед установкой daemon `VLC` должен уже быть установлен на Linux-машине.

## Установка

### 1. Установка зависимостей Windows

```bash
pip install -r requirements_windows.txt
```

### 2. Сборка offline package

```bash
python build_offline_package.py --arch x86_64
```

Результат:
- `offline_package/ktv_offline_package.tar.gz`

### 3. Запуск Windows-клиента

```bash
python operator_ktv/main.py
```

### 4. Подготовка Linux

Убедитесь, что на Linux-машине:

```bash
sudo apt update
sudo apt install vlc openssh-server
sudo systemctl enable ssh
sudo systemctl start ssh
```

### 5. Установка daemon через GUI

1. Запустите клиент.
2. Выберите `Файл -> Подключиться`.
3. Введите IP, логин и пароль.
4. Если daemon ещё не установлен, подтвердите установку.

Во время установки клиент:
- загрузит offline package на Linux
- распакует файлы
- установит Python-зависимости
- создаст `/opt/ktv`, `/etc/ktv`, `/var/lib/ktv`, `/var/log/ktv`
- установит и запустит `ktv-daemon`

## Ручная установка на Linux

Если нужно поставить пакет вручную:

```bash
scp offline_package/ktv_offline_package.tar.gz user@HOST:/tmp/
ssh user@HOST
cd /tmp
tar -xzf ktv_offline_package.tar.gz
cd ktv_offline_package
sudo bash install.sh
```

После установки проверьте сервис:

```bash
systemctl status ktv-daemon
```

## Использование

### Добавить фильм в расписание

1. В главном окне используйте левую часть `Фильмы`.
2. Найдите нужный месяц и день.
3. Перетащите видеофайл на нужный день.
4. Выберите время.
5. Подтвердите добавление.

Файл будет загружен в каталог вида `~/oktv/MM/DD/HH-MM/filename.ext` и добавлен в расписание daemon.

### Управление плейлистами

1. В главном окне используйте правую часть `Клипы`.
2. Нажмите `Создать плейлист`.
3. Укажите имя.
4. Перетащите файлы в область загрузки.
5. Активируйте плейлист кнопкой `Активировать` или двойным кликом.

Файлы плейлиста загружаются в `~/oktv/clips/<playlist_name>/`.

### Проверка состояния

- `Инструменты -> Проверить систему`
- `Инструменты -> Проверить установку`
- `Инструменты -> Статус daemon`
- `Инструменты -> SSH Консоль`

## Структура проекта

```text
KTV_New/
├── operator_ktv/
│   ├── main.py
│   ├── gui/
│   ├── network/
│   ├── installer/
│   └── models/
├── remote_player/
│   ├── daemon.py
│   ├── api_server.py
│   ├── scheduler.py
│   ├── playlist_manager.py
│   ├── player.py
│   ├── time_controller.py
│   └── storage/
├── build_offline_package.py
├── requirements_windows.txt
└── requirements_linux.txt
```

## Конфигурация Linux

Файл:
- `/etc/ktv/config.json`

Пример:

```json
{
    "api_port": 8888,
    "media_base_path": "~/oktv",
    "clips_folder": "~/oktv/clips",
    "database_path": "/var/lib/ktv/schedule.db",
    "log_path": "/var/log/ktv/daemon.log",
    "broadcast_start": "06:00",
    "broadcast_end": "22:00",
    "vlc_path": "/usr/bin/vlc",
    "display": ":0"
}
```

После изменения конфигурации:

```bash
sudo systemctl restart ktv-daemon
```

## Пути и данные на Linux

- `/opt/ktv/` - код daemon
- `/etc/ktv/config.json` - конфигурация
- `/var/lib/ktv/schedule.db` - база данных
- `/var/log/ktv/daemon.log` - лог daemon
- `~/oktv/MM/DD/HH-MM/` - файлы расписания
- `~/oktv/clips/` - файлы плейлистов

## Диагностика

### Windows

- лог клиента: `%USERPROFILE%\.operatorktv\operator_ktv.log`

Запуск клиента с подробным логированием:

```bash
python operator_ktv/main.py --debug
```

Просмотр лога:

```bash
python view_logs.py -n 100
python view_logs.py -f
```

### Linux

Основные команды:

```bash
sudo systemctl status ktv-daemon
sudo systemctl restart ktv-daemon
sudo journalctl -u ktv-daemon -f
tail -f /var/log/ktv/daemon.log
```

Проверка API-порта:

```bash
ss -tlnp | grep 8888
```

Проверка VLC:

```bash
vlc --version
```

## Устранение неполадок

### Не удаётся подключиться по SSH

- проверьте `ssh user@host`
- убедитесь, что запущен `openssh-server`
- проверьте сетевую доступность и файрвол

### Daemon не отвечает

- проверьте `systemctl status ktv-daemon`
- проверьте `journalctl -u ktv-daemon -n 100`
- убедитесь, что `ss -tlnp | grep 8888` показывает listening на `8888`

### Не запускается воспроизведение

- проверьте `vlc --version`
- проверьте наличие файла по пути из расписания
- проверьте текущее время и окно вещания
- убедитесь, что на X-сервере доступен `DISPLAY`, указанный в конфиге

### Не загружаются файлы

- убедитесь, что пользователь перелогинился после установки
- проверьте права на домашний каталог и группу `ktv`

## Ограничения

- Автоматический установщик рассчитан на `x86_64` / `amd64`
- API daemon слушает локальный порт на Linux и вызывается клиентом через SSH-команды
- Для работы воспроизведения нужен установленный `VLC`

## Лицензия

`Proprietary`
# OperatorKTV

Система удалённого управления воспроизведением медиафайлов.

Проект состоит из двух частей:
- `operator_ktv` - Windows GUI-клиент на `PyQt6`
- `remote_player` - Linux daemon для воспроизведения и планирования

Клиент подключается к Linux-машине по `SSH/SFTP`, загружает файлы, управляет расписанием и плейлистами, а также может установить daemon на удалённую систему.

## Актуальное состояние

- Плеер на Linux: `VLC`
- API daemon: `localhost:8888`
- Фильмы по расписанию хранятся в `~/oktv/MM/DD/HH-MM/`
- Клиповые плейлисты хранятся в `~/oktv/clips/`
- Конфигурация daemon: `/etc/ktv/config.json`
- Сервис Linux: `ktv-daemon`

## Возможности

- Добавление видеофайлов в расписание через drag-and-drop
- Воспроизведение по месяцу, дню и времени
- Изменение времени фильма и отдельное включение/отключение элементов расписания
- Создание и активация плейлистов для фонового воспроизведения
- Автоматическое переключение между плейлистом и запланированным контентом
- Встроенная SSH-консоль
- Проверка удалённой системы и верификация установки
- Автоматическая установка daemon на Linux через offline package

## Как работает воспроизведение

- Время вещания задаётся параметрами `broadcast_start` и `broadcast_end`
- Вне окна вещания фоновый плейлист не воспроизводится
- Запланированные файлы тоже не запускаются вне окна вещания
- Если на одну и ту же минуту назначено несколько файлов, они ставятся в очередь и воспроизводятся последовательно
- После завершения запланированного контента фоновый плейлист возобновляется

## Требования

### Windows-клиент

- Windows 10/11
- Python 3.10+

### Linux-система

- Ubuntu 20.04+ или совместимая Debian/Ubuntu-система
- Архитектура `x86_64` / `amd64`
- Доступ по `SSH`
- Права `sudo`
- Установленный `VLC`

Важно: offline package не включает системные пакеты `VLC`. Перед установкой daemon `VLC` должен уже быть установлен на Linux-машине.

## Установка

### 1. Установка зависимостей Windows

```bash
pip install -r requirements_windows.txt
```

### 2. Сборка offline package

```bash
python build_offline_package.py --arch x86_64
```

Результат:
- `offline_package/ktv_offline_package.tar.gz`

### 3. Запуск Windows-клиента

```bash
python operator_ktv/main.py
```

### 4. Подготовка Linux

Убедитесь, что на Linux-машине:

```bash
sudo apt update
sudo apt install vlc openssh-server
sudo systemctl enable ssh
sudo systemctl start ssh
```

### 5. Установка daemon через GUI

1. Запустите клиент.
2. Выберите `Файл -> Подключиться`.
3. Введите IP, логин и пароль.
4. Если daemon ещё не установлен, подтвердите установку.

Во время установки клиент:
- загрузит offline package на Linux
- распакует файлы
- установит Python-зависимости
- создаст `/opt/ktv`, `/etc/ktv`, `/var/lib/ktv`, `/var/log/ktv`
- установит и запустит `ktv-daemon`

## Ручная установка на Linux

Если нужно поставить пакет вручную:

```bash
scp offline_package/ktv_offline_package.tar.gz user@HOST:/tmp/
ssh user@HOST
cd /tmp
tar -xzf ktv_offline_package.tar.gz
cd ktv_offline_package
sudo bash install.sh
```

После установки проверьте сервис:

```bash
systemctl status ktv-daemon
```

## Использование

### Добавить фильм в расписание

1. В главном окне используйте левую часть `Фильмы`.
2. Найдите нужный месяц и день.
3. Перетащите видеофайл на нужный день.
4. Выберите время.
5. Подтвердите добавление.

Файл будет загружен в каталог вида `~/oktv/MM/DD/HH-MM/filename.ext` и добавлен в расписание daemon.

### Управление плейлистами

1. В главном окне используйте правую часть `Клипы`.
2. Нажмите `Создать плейлист`.
3. Укажите имя.
4. Перетащите файлы в область загрузки.
5. Активируйте плейлист кнопкой `Активировать` или двойным кликом.

Файлы плейлиста загружаются в `~/oktv/clips/<playlist_name>/`.

### Проверка состояния

- `Инструменты -> Проверить систему`
- `Инструменты -> Проверить установку`
- `Инструменты -> Статус daemon`
- `Инструменты -> SSH Консоль`

## Структура проекта

```text
KTV_New/
├── operator_ktv/
│   ├── main.py
│   ├── gui/
│   ├── network/
│   ├── installer/
│   └── models/
├── remote_player/
│   ├── daemon.py
│   ├── api_server.py
│   ├── scheduler.py
│   ├── playlist_manager.py
│   ├── player.py
│   ├── time_controller.py
│   └── storage/
├── build_offline_package.py
├── requirements_windows.txt
└── requirements_linux.txt
```

## Конфигурация Linux

Файл:
- `/etc/ktv/config.json`

Пример:

```json
{
    "api_port": 8888,
    "media_base_path": "~/oktv",
    "clips_folder": "~/oktv/clips",
    "database_path": "/var/lib/ktv/schedule.db",
    "log_path": "/var/log/ktv/daemon.log",
    "broadcast_start": "06:00",
    "broadcast_end": "22:00",
    "vlc_path": "/usr/bin/vlc",
    "display": ":0"
}
```

После изменения конфигурации:

```bash
sudo systemctl restart ktv-daemon
```

## Пути и данные на Linux

- `/opt/ktv/` - код daemon
- `/etc/ktv/config.json` - конфигурация
- `/var/lib/ktv/schedule.db` - база данных
- `/var/log/ktv/daemon.log` - лог daemon
- `~/oktv/MM/DD/HH-MM/` - файлы расписания
- `~/oktv/clips/` - файлы плейлистов

## Диагностика

### Windows

- лог клиента: `%USERPROFILE%\\.operatorktv\\operator_ktv.log`

Запуск клиента с подробным логированием:

```bash
python operator_ktv/main.py --debug
```

Просмотр лога:

```bash
python view_logs.py -n 100
python view_logs.py -f
```

### Linux

Основные команды:

```bash
sudo systemctl status ktv-daemon
sudo systemctl restart ktv-daemon
sudo journalctl -u ktv-daemon -f
tail -f /var/log/ktv/daemon.log
```

Проверка API-порта:

```bash
ss -tlnp | grep 8888
```

Проверка VLC:

```bash
vlc --version
```

## Устранение неполадок

### Не удаётся подключиться по SSH

- проверьте `ssh user@host`
- убедитесь, что запущен `openssh-server`
- проверьте сетевую доступность и файрвол

### Daemon не отвечает

- проверьте `systemctl status ktv-daemon`
- проверьте `journalctl -u ktv-daemon -n 100`
- убедитесь, что `ss -tlnp | grep 8888` показывает listening на `8888`

### Не запускается воспроизведение

- проверьте `vlc --version`
- проверьте наличие файла по пути из расписания
- проверьте текущее время и окно вещания
- убедитесь, что на X-сервере доступен `DISPLAY`, указанный в конфиге

### Не загружаются файлы

- убедитесь, что пользователь перелогинился после установки
- проверьте права на домашний каталог и группу `ktv`

## Ограничения

- Автоматический установщик рассчитан на `x86_64` / `amd64`
- API daemon слушает локальный порт на Linux и вызывается клиентом через SSH-команды
- Для работы воспроизведения нужен установленный `VLC`

## Лицензия

`Proprietary`
