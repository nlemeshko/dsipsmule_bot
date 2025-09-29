# smule-bot (Telegram) - Helm Chart

Этот Helm чарт разворачивает Telegram smule-bot в Kubernetes кластере.

## Предварительные требования

- Kubernetes 1.19+
- Helm 3.0+
- PersistentVolume для хранения данных

## Установка

### 1. Подготовка переменных окружения

Скопируйте файл с примером конфигурации:

```bash
cp values-example.yaml values.yaml
```

Отредактируйте `values.yaml` и заполните обязательные переменные:

```yaml
env:
  TELEGRAM_TOKEN: "YOUR_TELEGRAM_BOT_TOKEN_HERE"
  CHAT_ID: "YOUR_TELEGRAM_CHAT_ID_HERE"
  SMULE_ACCOUNT_IDS: "96242367,3150102762"
```

### 2. Установка чарта

```bash
# Добавьте репозиторий (если необходимо)
helm repo add smule-bot ./helm/smule-followers

# Установите чарт
helm install smule-bot ./helm/smule-followers -f ./helm/smule-followers/values.yaml
```

### 3. Проверка установки

```bash
# Проверьте статус подов
kubectl get pods -l app.kubernetes.io/name=smule-bot

# Проверьте логи
kubectl logs -l app.kubernetes.io/name=smule-bot

# Проверьте PersistentVolumeClaim
kubeclt get pvc -l app.kubernetes.io/name=smule-bot
```

## Конфигурация

### Обязательные переменные окружения

- `BOT_TOKEN` - токен Telegram бота
- `ADMINS` - список ID администраторов через запятую (опционально)
- `CHARACTER_AI_TOKEN`, `CHARACTER_ID`, `CHARACTER_VOICE_ID` - для команды /ask (опционально)

### Опциональные переменные

- `TZ` - часовой пояс (по умолчанию Europe/Kyiv)

### PersistentVolume

По умолчанию PVC отключен. Если необходимо, включите `persistence.enabled` и укажите параметры.

## Обновление

```bash
helm upgrade smule-bot ./helm/smule-followers -f ./helm/smule-followers/values.yaml
```

## Удаление

```bash
helm uninstall smule-bot
```

**Внимание:** При удалении PersistentVolumeClaim также будет удален, что приведет к потере данных. Если нужно сохранить данные, сделайте бэкап перед удалением.

## Безопасность

Чарт настроен с учетом лучших практик безопасности:

- Запуск от непривилегированного пользователя (UID 10001)
- Read-only root filesystem
- Отключение privilege escalation
- Ограничение ресурсов

## Мониторинг

Бот отправляет уведомления в Telegram при:
- Событиях бота и ошибках (см. логи)

## Troubleshooting

### Проверка логов

```bash
kubectl logs -l app.kubernetes.io/name=smule-followers -f
```

### Проверка переменных окружения

```bash
kubectl describe pod -l app.kubernetes.io/name=smule-followers
```

### Проверка PersistentVolume

```bash
kubectl get pvc -l app.kubernetes.io/name=smule-followers
kubectl describe pvc -l app.kubernetes.io/name=smule-followers
```
