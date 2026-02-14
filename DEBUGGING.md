# Руководство по отладке OperatorKTV

## Логирование

### Где находятся логи

**Windows клиент:**
```
%USERPROFILE%\.operatorktv\operator_ktv.log
```

Обычно это:
```
C:\Users\ИмяПользователя\.operatorktv\operator_ktv.log
```

**Linux daemon:**
```
/var/log/ktv/daemon.log
```

### Просмотр логов Windows

#### Способ 1: Встроенный скрипт
```cmd
# Показать последние 100 строк
python view_logs.py

# Показать последние 50 строк
python view_logs.py -n 50

# Следить за логом в реальном времени (как tail -f)
python view_logs.py -f

# Очистить логи
python view_logs.py --clear
```

#### Способ 2: Notepad
```cmd
notepad %USERPROFILE%\.operatorktv\operator_ktv.log
```

#### Способ 3: PowerShell
```powershell
# Последние 100 строк
Get-Content ~\.operatorktv\operator_ktv.log -Tail 100

# В реальном времени
Get-Content ~\.operatorktv\operator_ktv.log -Wait -Tail 50
```

### Запуск в режиме отладки

Для более детального логирования запустите с флагом `--debug`:

```cmd
python operator_ktv/main.py --debug
```

В DEBUG режиме логируется:
- Все SSH команды и их результаты
- Детали paramiko (SSH библиотека)
- Сетевые операции
- Состояния всех компонентов

### Просмотр логов Linux

```bash
# Последние строки daemon логов
tail -f /var/log/ktv/daemon.log

# Systemd логи
journalctl -u ktv-daemon -f

# Последние 100 строк
journalctl -u ktv-daemon -n 100

# Логи за последний час
journalctl -u ktv-daemon --since "1 hour ago"
```

## Типичные ошибки и решения

### 1. SSH Banner Error

**Ошибка:**
```
SSH error: Error reading SSH protocol banner
```

**Причины:**
- SSH сервер не запущен на Linux
- Неправильный IP адрес или порт
- Файрвол блокирует соединение
- На указанном порту работает не SSH сервер

**Решение:**

1. Проверьте SSH сервер на Linux:
```bash
sudo systemctl status ssh
# или
sudo systemctl status sshd
```

2. Если не запущен:
```bash
sudo systemctl start ssh
sudo systemctl enable ssh
```

3. Проверьте порт:
```bash
sudo netstat -tlnp | grep :22
# или
sudo ss -tlnp | grep :22
```

4. Проверьте файрвол:
```bash
sudo ufw status
sudo ufw allow 22/tcp
```

5. Проверьте IP адрес Linux системы:
```bash
ip addr show
# или
hostname -I
```

6. С Windows проверьте доступность:
```cmd
ping IP_АДРЕС
telnet IP_АДРЕС 22
```

### 2. Authentication Failed

**Ошибка:**
```
Authentication failed
```

**Причины:**
- Неправильный пароль
- Неправильное имя пользователя
- SSH не разрешает password authentication

**Решение:**

1. Проверьте логин и пароль через обычный SSH:
```cmd
ssh username@IP_АДРЕС
```

2. Проверьте настройки SSH на Linux:
```bash
sudo nano /etc/ssh/sshd_config
```

Убедитесь, что:
```
PasswordAuthentication yes
PermitRootLogin yes  # если используете root
```

3. Перезапустите SSH:
```bash
sudo systemctl restart ssh
```

### 3. Connection Timeout

**Ошибка:**
```
Connection timeout
```

**Причины:**
- IP адрес недоступен
- Неправильный IP
- Сетевые проблемы
- Файрвол блокирует

**Решение:**

1. Проверьте сетевое подключение:
```cmd
ping IP_АДРЕС
```

2. Проверьте, что VM в той же сети
3. Проверьте настройки сети VM (NAT vs Bridge)

### 4. Daemon не отвечает

**Ошибка:**
```
SSH подключение установлено, но daemon не отвечает
```

**Причины:**
- Daemon не установлен
- Daemon не запущен
- Порт 9999 заблокирован

**Решение:**

1. Используйте автоматическую установку из GUI:
   - **Инструменты → Установить ПО**

2. Или проверьте вручную:
```bash
systemctl status ktv-daemon
```

3. Проверьте порт:
```bash
netstat -tlnp | grep 9999
```

### 5. Upload Failed

**Ошибка:**
```
Upload failed: Permission denied
```

**Причины:**
- Нет прав на запись в целевую директорию
- Директория не существует

**Решение:**

1. Проверьте права:
```bash
ls -la /opt/ktv/media/
```

2. Установите права:
```bash
sudo chown -R ktv:ktv /opt/ktv/media/
sudo chmod -R 755 /opt/ktv/media/
```

## Диагностические команды

### Проверка системы через GUI

1. **Инструменты → Проверить систему**
   - Покажет полную информацию о Linux системе
   - OS, архитектура, Python, MPV
   - Статус daemon

2. **Инструменты → Проверить установку**
   - Детальная проверка всех компонентов
   - Файлы, сервисы, порты, база данных

3. **Инструменты → Статус daemon**
   - Текущее состояние daemon
   - Что воспроизводится
   - Активный плейлист

### SSH Консоль

**Инструменты → SSH Консоль** - открывает встроенный терминал

Полезные команды:
```bash
# Статус сервиса
systemctl status ktv-daemon

# Логи
tail -50 /var/log/ktv/daemon.log

# Проверка процессов
ps aux | grep python
ps aux | grep mpv

# Проверка портов
netstat -tlnp | grep 9999

# Проверка файлов
ls -la /opt/ktv/
ls -la /opt/ktv/media/movies/
ls -la /opt/ktv/media/clips/

# Проверка базы данных
sqlite3 /var/lib/ktv/schedule.db "SELECT * FROM schedule;"
```

## Пошаговая диагностика

### Проблема с подключением

1. **Запустите в DEBUG режиме:**
```cmd
python operator_ktv/main.py --debug
```

2. **Попробуйте подключиться**

3. **Проверьте логи:**
```cmd
python view_logs.py -n 200
```

4. **Ищите строки с:**
   - `ERROR` - ошибки
   - `Connecting to` - попытка подключения
   - `SSH exception` - детали SSH ошибок
   - `paramiko.transport` - низкоуровневые SSH детали

5. **Скопируйте последние 50 строк логов** для анализа

### Проблема с установкой

1. **Откройте SSH консоль** (Инструменты → SSH Консоль)

2. **Проверьте систему:**
```bash
# Версия OS
cat /etc/os-release

# Архитектура
uname -m

# Доступное место
df -h /opt

# Sudo
sudo -v
```

3. **Попробуйте установить вручную:**
   - Используйте GUI: **Инструменты → Установить ПО**
   - Следите за прогрессом
   - При ошибке смотрите детальный лог

4. **Проверьте результаты:**
```bash
systemctl status ktv-daemon
ls -la /opt/ktv/
```

### Проблема с воспроизведением

1. **Проверьте статус:**
   - **Инструменты → Статус daemon**

2. **Через SSH консоль:**
```bash
# Проверьте MPV
mpv --version

# Попробуйте воспроизвести тестовый файл
mpv --fs /opt/ktv/media/movies/test.mp4

# Проверьте расписание
sqlite3 /var/lib/ktv/schedule.db "SELECT * FROM schedule WHERE enabled=1;"
```

3. **Проверьте время на системе:**
```bash
date
timedatectl
```

## Сбор информации для поддержки

Если проблема не решается, соберите следующую информацию:

### Windows

```cmd
# Версия Python
python --version

# Установленные пакеты
pip list

# Последние 200 строк логов
python view_logs.py -n 200 > logs_windows.txt
```

### Linux (через SSH консоль)

```bash
# Системная информация
uname -a > /tmp/system_info.txt
cat /etc/os-release >> /tmp/system_info.txt

# Статус daemon
systemctl status ktv-daemon >> /tmp/system_info.txt

# Daemon логи
tail -200 /var/log/ktv/daemon.log > /tmp/daemon_logs.txt

# Systemd логи
journalctl -u ktv-daemon -n 100 > /tmp/systemd_logs.txt

# Скачайте файлы через SFTP или cat в консоли
```

## Частые вопросы по логам

**Q: Где найти логи?**
A: 
- Windows: `%USERPROFILE%\.operatorktv\operator_ktv.log`
- Linux: `/var/log/ktv/daemon.log`

**Q: Как включить DEBUG режим?**
A: Запустите с флагом: `python operator_ktv/main.py --debug`

**Q: Логи занимают много места?**
A: Можно очистить: `python view_logs.py --clear`

**Q: Как читать логи в реальном времени?**
A: `python view_logs.py -f` (Ctrl+C для выхода)

**Q: Что означает "SSH banner error"?**
A: SSH сервер не отвечает правильно. Проверьте:
- SSH сервер запущен
- Правильный IP и порт
- Нет файрвола

**Q: Можно ли увеличить timeout?**
A: Да, в коде `ssh_client.py` параметр `timeout` в методе `connect()`

## Проблемы с установкой

### "sudo: a terminal is required to read the password"

**Симптомы:**
```
Installation failed with exit code 1:
sudo: a terminal is required to read the password; either use the -S option to read from standard input or configure an askpass helper
sudo: a password is required
```

**Причина:**
Скрипт установки требует sudo привилегии, но SSH соединение не может предоставить пароль интерактивно.

**Решение:**
Эта проблема решается автоматически! Приложение использует ваш SSH пароль для sudo операций через `sudo -S`.

Если ошибка всё ещё возникает:

1. Убедитесь, что ваш SSH пользователь имеет sudo права:
   ```bash
   groups
   # Должно показать: sudo
   ```

2. Если пользователь не в группе sudo, добавьте его (требуется админ):
   ```bash
   sudo usermod -aG sudo your_username
   # Затем выйдите и войдите снова
   ```

3. Проверьте, что пароль SSH правильный - это тот же пароль, который используется для sudo.

### Установка зависает на долгое время

**Причина:**
Установка .deb пакетов и Python зависимостей может занять 5-10 минут на слабых системах (Intel Atom, 2GB RAM).

**Решение:**
- Подождите до 10 минут
- Следите за логами в DEBUG режиме:
  ```cmd
  python operator_ktv/main.py --debug
  python view_logs.py -f
  ```

### Недостаточно места на диске

**Диагностика:**
```bash
df -h /
```

**Решение:**
Освободите минимум 500MB на Linux системе:
```bash
# Очистить apt кеш
sudo apt clean

# Удалить старые логи
sudo journalctl --vacuum-time=7d

# Удалить неиспользуемые пакеты
sudo apt autoremove
```

## Контакты

При обращении в поддержку приложите:
- Логи Windows (последние 200 строк)
- Логи Linux (если доступны)
- Описание проблемы
- Версии ОС (Windows и Linux)
