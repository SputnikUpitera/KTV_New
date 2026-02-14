# Руководство по установке OperatorKTV

Подробная инструкция по установке и настройке системы OperatorKTV.

## Оглавление

1. [Подготовка Windows клиента](#подготовка-windows-клиента)
2. [Подготовка Linux сервера](#подготовка-linux-сервера)
3. [Сборка offline пакета](#сборка-offline-пакета)
4. [Установка на Linux](#установка-на-linux)
5. [Первый запуск](#первый-запуск)
6. [Проверка установки](#проверка-установки)

## Подготовка Windows клиента

### Шаг 1: Установка Python

1. Скачайте Python 3.10 или новее с https://www.python.org/
2. При установке отметьте "Add Python to PATH"
3. Проверьте установку:
```cmd
python --version
```

### Шаг 2: Клонирование проекта

```cmd
cd C:\Projects
git clone <repository_url> KTV_New
cd KTV_New
```

### Шаг 3: Создание виртуального окружения (рекомендуется)

```cmd
python -m venv venv
venv\Scripts\activate
```

### Шаг 4: Установка зависимостей

```cmd
pip install -r requirements_windows.txt
```

Это установит:
- PyQt6 (GUI фреймворк)
- paramiko (SSH/SFTP)
- cryptography (шифрование)

## Подготовка Linux сервера

### Минимальные требования

- Ubuntu 20.04 LTS (Focal Fossa) или совместимая
- 2 GB RAM
- 10 GB свободного места
- Процессор: Intel Atom или лучше
- Сетевое подключение к Windows клиенту

### Шаг 1: Установка SSH сервера (если не установлен)

```bash
sudo apt update
sudo apt install openssh-server
sudo systemctl enable ssh
sudo systemctl start ssh
```

### Шаг 2: Проверка доступа

С Windows клиента проверьте SSH доступ:
```cmd
ssh user@192.168.1.100
```

Замените `user` и IP на свои значения.

### Шаг 3: Настройка sudo (если требуется)

Пользователь должен иметь sudo права без пароля для автоматической установки:

```bash
sudo visudo
```

Добавьте строку (замените `user` на имя пользователя):
```
user ALL=(ALL) NOPASSWD: ALL
```

## Сборка offline пакета

### Важно

Этот шаг выполняется на Windows клиенте или на любом компьютере с доступом к интернету.

### Шаг 1: Запуск сборщика

```cmd
python build_offline_package.py --arch x86_64
```

Параметры:
- `--arch x86_64` - для Intel/AMD процессоров (по умолчанию)
- `--arch armv7l` - для ARM процессоров
- `--output folder` - папка для сохранения пакета

### Шаг 2: Что происходит при сборке

1. Скачиваются .deb пакеты для Ubuntu:
   - mpv (медиаплеер)
   - libmpv1 (библиотека)
   - зависимости ffmpeg

2. Скачиваются Python пакеты (.whl):
   - APScheduler
   - pytz, tzlocal
   - зависимости

3. Копируются файлы daemon
4. Создаётся установочный скрипт
5. Всё упаковывается в `ktv_offline_package.tar.gz`

### Шаг 3: Проверка результата

```cmd
dir offline_package\ktv_offline_package.tar.gz
```

Размер пакета должен быть около 50-100 MB.

## Установка на Linux

Есть два способа установки:

### Способ 1: Автоматическая установка через GUI (рекомендуется)

1. Запустите Windows клиент:
```cmd
python operator_ktv/main.py
```

2. Подключитесь к Linux системе:
   - **Файл → Подключиться**
   - Введите IP, логин, пароль
   - Нажмите **Подключиться**

3. Если daemon не установлен, программа предложит установить:
   - Нажмите **Да**
   - Дождитесь завершения установки (2-5 минут)

4. После установки программа автоматически подключится к daemon

### Способ 2: Ручная установка

Если автоматическая установка не работает:

#### Шаг 1: Передача пакета на Linux

На Windows:
```cmd
scp offline_package\ktv_offline_package.tar.gz user@192.168.1.100:/tmp/
```

#### Шаг 2: Распаковка и установка

На Linux:
```bash
cd /tmp
tar -xzf ktv_offline_package.tar.gz
cd ktv_offline_package
sudo bash install.sh
```

#### Шаг 3: Проверка установки

```bash
systemctl status ktv-daemon
```

Должно показать "active (running)".

## Первый запуск

### Шаг 1: Запуск Windows клиента

```cmd
cd KTV_New
python operator_ktv/main.py
```

### Шаг 2: Подключение

1. Откроется диалог подключения
2. Введите данные:
   - **IP адрес**: 192.168.1.100 (пример)
   - **Порт**: 22
   - **Пользователь**: ваш логин
   - **Пароль**: ваш пароль

3. Нажмите **Подключиться**

### Шаг 3: Проверка подключения

После успешного подключения:
- Статус-бар внизу покажет "Подключено к 192.168.1.100"
- Вкладки "Фильмы" и "Клипы" станут активными
- В меню "Инструменты" появятся доступные команды

### Шаг 4: Первый тест

1. Создайте тестовый плейлист:
   - Вкладка **Клипы**
   - **Создать плейлист**
   - Имя: "Test"

2. Добавьте видеофайл:
   - Перетащите MP4 файл в правую область
   - Дождитесь загрузки

3. Проверьте статус:
   - **Инструменты → Статус daemon**
   - Должно показать "Daemon запущен: Да"

## Проверка установки

### На Linux сервере

#### 1. Проверка сервиса

```bash
sudo systemctl status ktv-daemon
```

Вывод должен содержать:
- `Active: active (running)`
- Процесс запущен несколько секунд/минут назад

#### 2. Проверка файлов

```bash
ls -la /opt/ktv/
ls -la /opt/ktv/media/movies/
ls -la /opt/ktv/media/clips/
ls -la /etc/ktv/
```

Все папки должны существовать.

#### 3. Проверка логов

```bash
tail -f /var/log/ktv/daemon.log
```

Не должно быть ошибок, только информационные сообщения.

#### 4. Проверка API порта

```bash
netstat -tlnp | grep 9999
```

Или:
```bash
sudo ss -tlnp | grep 9999
```

Должна быть строка с портом 9999 в состоянии LISTEN.

#### 5. Проверка MPV

```bash
mpv --version
```

Должна показать версию MPV.

### Из Windows клиента

#### 1. Проверка системы

**Инструменты → Проверить систему**

Должно показать:
- ✓ OS: Ubuntu 20.04...
- ✓ Python3: 3.x.x
- ✓ MPV: найден
- ✓ Daemon установлен: Да
- ✓ Daemon запущен: Да

#### 2. Проверка установки

**Инструменты → Проверить установку**

Все проверки должны быть успешными (✓).

#### 3. SSH консоль

**Инструменты → SSH Консоль**

Попробуйте команды:
```bash
ls /opt/ktv/
systemctl status ktv-daemon
tail /var/log/ktv/daemon.log
```

## Устранение проблем при установке

### Проблема: Не удаётся подключиться по SSH

**Решение:**
1. Проверьте, что SSH сервер запущен:
   ```bash
   sudo systemctl status ssh
   ```
2. Проверьте файрвол:
   ```bash
   sudo ufw status
   sudo ufw allow 22/tcp
   ```
3. Проверьте IP адрес:
   ```bash
   ip addr show
   ```

### Проблема: Daemon не запускается

**Решение:**
1. Проверьте логи:
   ```bash
   sudo journalctl -u ktv-daemon -n 50
   ```
2. Проверьте, что все файлы на месте:
   ```bash
   ls -la /opt/ktv/daemon.py
   ```
3. Попробуйте запустить вручную:
   ```bash
   cd /opt/ktv
   source venv/bin/activate
   python daemon.py --debug
   ```

### Проблема: MPV не установлен

**Решение:**
1. Установите вручную:
   ```bash
   sudo apt update
   sudo apt install mpv
   ```
2. Или установите из offline пакета:
   ```bash
   cd /tmp/ktv_offline_package/packages
   sudo dpkg -i *.deb
   sudo apt-get install -f
   ```

### Проблема: Нет прав sudo

**Решение:**
1. Попросите администратора добавить вас в группу sudo:
   ```bash
   sudo usermod -aG sudo your_username
   ```
2. Выйдите и войдите снова
3. Проверьте:
   ```bash
   sudo -v
   ```

### Проблема: Недостаточно места на диске

**Решение:**
1. Проверьте свободное место:
   ```bash
   df -h /opt
   ```
2. Очистите ненужные файлы:
   ```bash
   sudo apt clean
   sudo apt autoremove
   ```

## Обновление

### Обновление Windows клиента

```cmd
cd KTV_New
git pull
pip install -r requirements_windows.txt --upgrade
```

### Обновление Linux daemon

1. Соберите новый offline пакет
2. Остановите daemon:
   ```bash
   sudo systemctl stop ktv-daemon
   ```
3. Установите новую версию (автоматически или вручную)
4. Запустите daemon:
   ```bash
   sudo systemctl start ktv-daemon
   ```

## Резервное копирование

### Важные файлы для бэкапа

На Linux сервере:
- `/var/lib/ktv/schedule.db` - база данных расписания
- `/etc/ktv/config.json` - конфигурация
- `/opt/ktv/media/` - медиафайлы

Пример резервного копирования:
```bash
sudo tar -czf ktv_backup_$(date +%Y%m%d).tar.gz \
  /var/lib/ktv/schedule.db \
  /etc/ktv/config.json \
  /opt/ktv/media/
```

## Удаление

### Удаление с Linux

```bash
# Остановить и отключить сервис
sudo systemctl stop ktv-daemon
sudo systemctl disable ktv-daemon

# Удалить файлы
sudo rm /etc/systemd/system/ktv-daemon.service
sudo rm -rf /opt/ktv
sudo rm -rf /var/lib/ktv
sudo rm -rf /var/log/ktv
sudo rm -rf /etc/ktv

# Перезагрузить systemd
sudo systemctl daemon-reload
```

### Удаление с Windows

Просто удалите папку проекта:
```cmd
rmdir /s KTV_New
```

## Поддержка

Если возникли проблемы, соберите следующую информацию:

1. Версия ОС (Windows и Linux)
2. Вывод команды (на Linux):
   ```bash
   systemctl status ktv-daemon
   tail -50 /var/log/ktv/daemon.log
   ```
3. Логи Windows клиента:
   ```
   %USERPROFILE%\.operatorktv\operator_ktv.log
   ```

И обратитесь к разработчику.
