# smule-bot (Telegram) - Helm Chart

Этот Helm чарт разворачивает Telegram smule-bot в Kubernetes кластере.

Мини-приложение доступно через Ingress `bot.dsipsmule.one` → Service → HTTP-порт 8080.
В том же контейнере работает polling Telegram. Используйте одну реплику.

Ingress настроен по конфигурации кластера: `ingressClassName: nginx`, issuer
`letsencrypt-prod-dns`, принудительные HTTPS-редиректы. Cert-manager создаёт
сертификат для `bot.dsipsmule.one` в Secret `bot-dsipsmule-one-tls` в namespace релиза.
DNS домена должен указывать на ваш Nginx ingress-контроллер. Service и backend
Ingress используют порт 8080; контейнер слушает этот же порт.

Для фото и аудио задан `proxy-body-size: 21m`, для ответов AI —
`proxy-read-timeout: 180` и `proxy-send-timeout: 180`.
Readiness проверяет `/healthz`. Переменные `MINI_APP_*` берутся из `env` в values,
а `existingSecret.keys` может переопределить их. Токен и ключи API берутся из Secret `env`.

Если зал славы должен переживать обновление Pod, включите `persistence.enabled`:
CSV будет храниться в PVC (`DATA_DIR=/data`). Без PVC используется доступный для
записи `emptyDir`: обновления CSV теряются при замене Pod. Первоначальные данные
берутся из `data/hall.csv` в образе.

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
  MINI_APP_URL: "https://bot.dsipsmule.one"
  MINI_APP_PORT: "8080"
existingSecret:
  name: env # Содержит BOT_TOKEN, ADMINS и ключи API
```

### 2. Установка чарта

```bash
# Добавьте репозиторий (если необходимо)

# Установите чарт
helm install smule-bot ./helm/smule-bot -f ./helm/smule-bot/values.yaml
```

### 3. Проверка установки

```bash
# Проверьте статус подов
kubectl get pods -l app.kubernetes.io/name=smule-bot

# Проверьте логи
kubectl logs -l app.kubernetes.io/name=smule-bot

# Проверьте PersistentVolumeClaim
kubectl get pvc -l app.kubernetes.io/name=smule-bot
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
helm upgrade smule-bot ./helm/smule-bot -f ./helm/smule-bot/values.yaml
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
kubectl logs -l app.kubernetes.io/name=smule-bot -f
```

### Проверка переменных окружения

```bash
kubectl describe pod -l app.kubernetes.io/name=smule-bot
```

### Проверка PersistentVolume

```bash
kubectl get pvc -l app.kubernetes.io/name=smule-bot
kubectl describe pvc -l app.kubernetes.io/name=smule-bot
```
