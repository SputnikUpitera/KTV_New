# Пересборка пакета после исправления

## Что было исправлено

Файлы для Linux теперь создаются с правильными Unix окончаниями строк (LF `\n`) вместо Windows (CRLF `\r\n`):
- ✅ `install.sh` - установочный скрипт
- ✅ `ktv-daemon.service` - systemd сервис
- ✅ `config.json` - конфигурация

## Как пересобрать пакет

### 1. Пересоберите offline пакет:

```cmd
python build_offline_package.py
```

Это создаст новый `offline_package/ktv_offline_package.tar.gz` с правильными окончаниями строк.

### 2. Установите на неттоп:

1. Запустите OperatorKTV:
   ```cmd
   python operator_ktv/main.py
   ```

2. Подключитесь к неттопу (Menu → Connect)

3. Нажмите **Install Software**

4. Установка должна пройти успешно!

## Что было исправлено ранее

### Проблема 1: sudo требует пароль
✅ **Исправлено**: Пароль передаётся через stdin с помощью `sudo -S`

### Проблема 2: sudo не может выполнить cd
✅ **Исправлено**: Команда обёрнута в `bash -c "cd ... && command"`

### Проблема 3: Windows окончания строк в скриптах
✅ **Исправлено**: Все Linux файлы создаются с Unix окончаниями строк (LF)

## Проверка после установки

После успешной установки проверьте на неттопе:

```bash
# Статус daemon
systemctl status ktv-daemon

# Логи daemon
journalctl -u ktv-daemon -n 50

# API сервер доступен
curl http://localhost:9999
```

## Если всё ещё есть проблемы

Запустите в DEBUG режиме:

```cmd
python operator_ktv/main.py --debug
```

Проверьте логи:

```cmd
python view_logs.py -n 200
```

Смотрите `DEBUGGING.md` для дополнительной информации.
