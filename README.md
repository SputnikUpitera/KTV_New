# OperatorKTV

## Описание

`OperatorKTV` — система удаленного управления медиавоспроизведением.

Состоит из двух частей:
- `operator_ktv` — Windows GUI-клиент (`PyQt6`);
- `remote_player` — Linux daemon (расписание + плейлисты + воспроизведение через `VLC`).

Клиент подключается к Linux по `SSH/SFTP`, загружает медиа, управляет расписанием и плейлистами, устанавливает и проверяет daemon.

---

## Требования

### Windows (клиент)
- Windows 10/11
- Python 3.10+

### Linux (сервер)
- Ubuntu 20.04+ (или совместимый Debian/Ubuntu)
- `x86_64` / `amd64`
- `ssh` доступ
- права `sudo`
- установленный `VLC`

---

## Установка

### 1) Установить зависимости клиента

```bash
pip install -r requirements_windows.txt
```

### 2) Собрать offline package

```bash
python build_offline_package.py --arch x86_64
```

Результат: `offline_package/ktv_offline_package.tar.gz`

### 3) Запустить клиент

```bash
python operator_ktv/main.py
```

### 4) Подготовить Linux

```bash
sudo apt update
sudo apt install -y vlc openssh-server
sudo systemctl enable ssh
sudo systemctl start ssh
```

### 5) Установить daemon из GUI

В клиенте: `Файл -> Подключиться` -> ввести хост/логин/пароль -> подтвердить установку.

---

## Использование

### Фильмы по расписанию
- открыть вкладку `Фильмы`;
- выбрать день/время;
- перетащить видеофайл;
- подтвердить добавление.

Файл попадет в `~/oktv/MM/DD/HH-MM/` на Linux.

### Плейлисты (клипы)
- открыть вкладку `Клипы`;
- создать плейлист;
- загрузить файлы;
- активировать плейлист.

Файлы плейлиста хранятся в `~/oktv/clips/<playlist>/`.

### Полезные инструменты GUI
- `Инструменты -> Проверить систему`
- `Инструменты -> Проверить установку`
- `Инструменты -> Статус daemon`
- `Инструменты -> SSH Консоль`

---

## Обслуживание

### Основные пути на Linux
- `/opt/ktv/` — код daemon
- `/etc/ktv/config.json` — конфиг
- `/var/lib/ktv/schedule.db` — база расписания
- `/var/log/ktv/daemon.log` — лог daemon
- `~/oktv/MM/DD/HH-MM/` — файлы расписания
- `~/oktv/clips/` — файлы плейлистов

### Команды эксплуатации

```bash
sudo systemctl status ktv-daemon
sudo systemctl restart ktv-daemon
sudo journalctl -u ktv-daemon -f
tail -f /var/log/ktv/daemon.log
ss -tlnp | grep 8888
```

### Логи клиента (Windows)
- `%USERPROFILE%\.operatorktv\operator_ktv.log`

Просмотр:

```bash
python view_logs.py -n 100
python view_logs.py -f
```
# OperatorKTV

## Описание

`OperatorKTV` — система удаленного управления медиавоспроизведением.

Состоит из двух частей:
- `operator_ktv` — Windows GUI-клиент (`PyQt6`);
- `remote_player` — Linux daemon (расписание + плейлисты + воспроизведение через `VLC`).

Клиент подключается к Linux по `SSH/SFTP`, загружает медиа, управляет расписанием и плейлистами, устанавливает и проверяет daemon.

---

## Требования

### Windows (клиент)
- Windows 10/11
- Python 3.10+

### Linux (сервер)
- Ubuntu 20.04+ (или совместимый Debian/Ubuntu)
- `x86_64` / `amd64`
- `ssh` доступ
- права `sudo`
- установленный `VLC`

---

## Установка

### 1) Установить зависимости клиента

```bash
pip install -r requirements_windows.txt
```

### 2) Собрать offline package

```bash
python build_offline_package.py --arch x86_64
```

Результат: `offline_package/ktv_offline_package.tar.gz`

### 3) Запустить клиент

```bash
python operator_ktv/main.py
```

### 4) Подготовить Linux

```bash
sudo apt update
sudo apt install -y vlc openssh-server
sudo systemctl enable ssh
sudo systemctl start ssh
```

### 5) Установить daemon из GUI

В клиенте: `Файл -> Подключиться` -> ввести хост/логин/пароль -> подтвердить установку.

---

## Использование

### Фильмы по расписанию
- открыть вкладку `Фильмы`;
- выбрать день/время;
- перетащить видеофайл;
- подтвердить добавление.

Файл попадет в `~/oktv/MM/DD/HH-MM/` на Linux.

### Плейлисты (клипы)
- открыть вкладку `Клипы`;
- создать плейлист;
- загрузить файлы;
- активировать плейлист.

Файлы плейлиста хранятся в `~/oktv/clips/<playlist>/`.

### Полезные инструменты GUI
- `Инструменты -> Проверить систему`
- `Инструменты -> Проверить установку`
- `Инструменты -> Статус daemon`
- `Инструменты -> SSH Консоль`

---

## Обслуживание

### Основные пути на Linux
- `/opt/ktv/` — код daemon
- `/etc/ktv/config.json` — конфиг
- `/var/lib/ktv/schedule.db` — база расписания
- `/var/log/ktv/daemon.log` — лог daemon
- `~/oktv/MM/DD/HH-MM/` — файлы расписания
- `~/oktv/clips/` — файлы плейлистов

### Команды эксплуатации

```bash
sudo systemctl status ktv-daemon
sudo systemctl restart ktv-daemon
sudo journalctl -u ktv-daemon -f
tail -f /var/log/ktv/daemon.log
ss -tlnp | grep 8888
```

### Логи клиента (Windows)
- `%USERPROFILE%\.operatorktv\operator_ktv.log`

Просмотр:

```bash
python view_logs.py -n 100
python view_logs.py -f
```
