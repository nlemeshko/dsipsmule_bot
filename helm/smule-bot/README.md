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

Для бесплатных AI-функций добавьте в этот же Secret `GROQ_API_KEY`
(текст и расшифровка), `CLOUDFLARE_API_TOKEN` и `CLOUDFLARE_ACCOUNT_ID`
(картинки). Оставьте аккаунты Groq и Workers AI на бесплатных тарифах.
Список групп задаётся `ALLOWED_GROUP_ID` через запятую. Модели по умолчанию:
`openai/gpt-oss-20b`, `whisper-large-v3-turbo`, `@cf/black-forest-labs/flux-1-schnell`.
Отдельные Deployments, GPU, Ollama и изменения Ingress не нужны.
После изменения Secret нужно заменить Pod: переменные окружения читаются при запуске.
Обновляйте образ вместе с кодом: перезапуск старого образа не добавит AI-функции.

Зал славы хранится в S3: endpoint `https://nbg1.your-objectstorage.com`,
бакет `dsipsmule`, файл `dsipsmule-bot/hall/hall.csv`. Эти значения уже заданы
в `env` в values. Добавьте `S3_ACCESS_KEY_ID` и `S3_SECRET_ACCESS_KEY` в
существующий Secret `env` в namespace `smule-bot` и обновите релиз. Ключи
подхватываются через `envFrom`; хранить их в values не нужно.

При первом запуске, если объекта ещё нет, бот перенесёт локальный CSV из
`DATA_DIR=/data` (или начальный `data/hall.csv` из образа). Существующий объект
не перезаписывается при запуске. Перед первым обновлением сохраните CSV из
старого Pod, если там есть новые записи: отключённый PVC не переживает замену Pod.
При сбое S3 бот сообщает об ошибке сохранения, а не подтверждает потерянные голоса.

PVC для S3 не требуется: `emptyDir` используется как локальный кэш.
Для режима только с локальным файлом задайте `env.S3_BUCKET: ""`, уберите S3-ключи
из окружения и включите `persistence.enabled`. Используйте одну реплику;
стратегия `Recreate` исключает одновременную запись старого и нового Pod.

## Предварительные требования

- Kubernetes 1.19+
- Helm 3.0+
- Доступ к S3 и ключ с правами чтения/записи в выбранном бакете

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
- `GROQ_API_KEY` - вопросы и расшифровка аудио (опционально)
- `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` - создание картинок (опционально)
- `ALLOWED_GROUP_ID` - разрешённые для AI группы через запятую (без списка AI работает только в личке)
- `CHARACTER_AI_TOKEN`, `CHARACTER_ID`, `CHARACTER_VOICE_ID` - прежний /ask, если Groq не подключён (опционально)

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
