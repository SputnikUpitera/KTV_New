# Подготовка Linux системы для OperatorKTV

## Минимальные требования

Перед использованием OperatorKTV на Linux системе **обязательно** должно быть установлено:

1. ✅ **Ubuntu 20.04 LTS** (или совместимая система)
2. ✅ **SSH сервер** (openssh-server)
3. ✅ **Пользователь с sudo правами**
4. ✅ **Минимум 500 MB свободного места**

## Пошаговая настройка Linux VM

### Шаг 1: Установка SSH сервера

#### Если есть интернет:

```bash
# Обновить список пакетов
sudo apt update

# Установить OpenSSH Server
sudo apt install -y openssh-server

# Запустить и включить автозапуск
sudo systemctl start ssh
sudo systemctl enable ssh

# Проверить статус
sudo systemctl status ssh
```

Вы должны увидеть:
```
● ssh.service - OpenSSH server daemon
   Loaded: loaded (/lib/systemd/system/ssh.service; enabled)
   Active: active (running)
```

#### Если НЕТ интернета:

**Вариант А: Включить SSH при установке Ubuntu**

При установке Ubuntu выберите опцию "Install OpenSSH server"

**Вариант Б: Установить с другого носителя**

1. На компьютере с интернетом (Ubuntu):
```bash
# Скачать пакеты
mkdir ssh_packages
cd ssh_packages
apt download openssh-server openssh-client openssh-sftp-server
apt download libwrap0 tcpd
```

2. Скопировать все .deb файлы на USB флешку

3. На Linux VM:
```bash
# Вставить USB, смонтировать и установить
cd /media/usb  # путь может отличаться
sudo dpkg -i *.deb
sudo apt-get install -f  # установить зависимости, если есть
sudo systemctl start ssh
sudo systemctl enable ssh
```

### Шаг 2: Настройка SSH

```bash
# Разрешить password authentication
sudo nano /etc/ssh/sshd_config
```

Убедитесь, что эти строки присутствуют и не закомментированы:
```
Port 22
PasswordAuthentication yes
PermitRootLogin no
PubkeyAuthentication yes
```

Сохраните (Ctrl+O, Enter, Ctrl+X) и перезапустите SSH:
```bash
sudo systemctl restart ssh
```

### Шаг 3: Настройка файрвола (если установлен)

```bash
# Проверить статус файрвола
sudo ufw status

# Если файрвол активен, разрешить SSH
sudo ufw allow 22/tcp
sudo ufw reload
```

### Шаг 4: Создание пользователя (если нужно)

```bash
# Создать пользователя для OperatorKTV
sudo adduser ktvuser

# Добавить в группу sudo
sudo usermod -aG sudo ktvuser

# Для автоматической установки без запроса пароля (опционально):
sudo visudo
```

Добавьте строку:
```
ktvuser ALL=(ALL) NOPASSWD: ALL
```

### Шаг 5: Узнать IP адрес

```bash
# Показать все IP адреса
ip addr show

# Или короткая версия
hostname -I
```

Запишите IP адрес, например: `192.168.1.100`

### Шаг 6: Проверка с Windows

На Windows компьютере проверьте подключение:

```cmd
# Проверить доступность
ping 192.168.1.100

# Попробовать SSH
ssh ktvuser@192.168.1.100
```

Если SSH подключается, вы готовы использовать OperatorKTV!

## Настройка сети VM

### VirtualBox

**Для доступа с Windows используйте Bridge Adapter:**

1. Выключите VM
2. Settings → Network → Adapter 1
3. Attached to: **Bridged Adapter**
4. Name: выберите ваш сетевой адаптер
5. Запустите VM

После запуска VM будет в той же сети что и Windows.

**Альтернатива: NAT + Port Forwarding**

1. Attached to: NAT
2. Advanced → Port Forwarding
3. Добавить правило:
   - Name: SSH
   - Protocol: TCP
   - Host Port: 2222
   - Guest Port: 22
4. В OperatorKTV подключайтесь к `127.0.0.1:2222`

### VMware / Hyper-V

Используйте Bridge mode или NAT с аналогичными настройками.

## Проверочный список

Перед использованием OperatorKTV убедитесь:

- [ ] SSH сервер установлен и запущен
- [ ] Порт 22 открыт в файрволе
- [ ] У вас есть пользователь с sudo правами
- [ ] Вы знаете IP адрес Linux VM
- [ ] SSH подключение работает с Windows
- [ ] Минимум 500 MB свободного места

Проверьте все пункты командами:

```bash
# 1. SSH сервер
sudo systemctl status ssh

# 2. Порт открыт
sudo ss -tlnp | grep :22

# 3. Ваш пользователь
groups
# Должно быть: sudo

# 4. IP адрес
hostname -I

# 5. (С Windows) Тест SSH
ssh username@IP

# 6. Свободное место
df -h /
```

## Быстрая установка (с интернетом)

Одна команда для полной настройки:

```bash
sudo apt update && \
sudo apt install -y openssh-server && \
sudo systemctl start ssh && \
sudo systemctl enable ssh && \
sudo ufw allow 22/tcp && \
echo "SSH готов! IP адрес:" && hostname -I
```

## Troubleshooting

### SSH не запускается

```bash
# Проверьте логи
sudo journalctl -u ssh -n 50

# Проверьте конфиг
sudo sshd -t

# Проверьте порт
sudo netstat -tlnp | grep :22
```

### "Permission denied" при sudo

```bash
# Проверьте группы пользователя
groups

# Добавьте в sudo (от другого админ пользователя)
sudo usermod -aG sudo your_username

# Выйдите и войдите снова
exit
```

### Забыли IP адрес

```bash
ip a | grep "inet " | grep -v 127.0.0.1
```

### "kex_exchange_identification: Connection closed by remote host"

Эта ошибка означает, что SSH сервер закрывает соединение во время handshake.

**Причина 1: TCP Wrappers блокируют подключение**

```bash
# Проверьте правила доступа
cat /etc/hosts.allow
cat /etc/hosts.deny

# Разрешите SSH для всех
echo "sshd: ALL" | sudo tee -a /etc/hosts.allow

# Или только для вашей сети
echo "sshd: 192.168.109." | sudo tee -a /etc/hosts.allow
```

**Причина 2: Проблемы с конфигурацией SSH**

```bash
# Проверьте конфиг на ошибки
sudo sshd -t

# Отредактируйте при необходимости
sudo nano /etc/ssh/sshd_config

# Убедитесь что установлено:
# Port 22
# ListenAddress 0.0.0.0
# PasswordAuthentication yes
# MaxStartups 10:30:100

# Перезапустите
sudo systemctl restart ssh
```

**Причина 3: Нехватка ресурсов**

На системах с 2GB RAM добавьте swap:

```bash
# Создать 1GB swap
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Сделать постоянным
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

**Смотрите логи в реальном времени:**

```bash
# В одном терминале
sudo journalctl -u ssh -f

# В другом терминале
sudo tail -f /var/log/auth.log

# Затем пытайтесь подключиться с Windows
```

**Если ничего не помогает - переустановите:**

```bash
sudo apt remove --purge openssh-server
sudo apt autoremove
sudo apt install -y openssh-server
sudo systemctl enable ssh
sudo systemctl start ssh
```

## Готово!

После выполнения всех шагов:

1. Запустите OperatorKTV на Windows
2. Подключитесь, используя IP адрес Linux VM
3. Программа автоматически установит daemon

Если проблемы остались, запустите в DEBUG режиме и проверьте логи:

```cmd
python operator_ktv/main.py --debug
python view_logs.py -n 200
```
