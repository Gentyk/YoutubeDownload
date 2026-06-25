# Деплой yt2mp3 на удалённый сервер

Что получится: сайт по адресу `https://yt2mp3.твой-домен.com` с авто-HTTPS (Caddy +
Let's Encrypt, всё в `docker compose`). По умолчанию сайт **открыт всем без логина**;
в админ-панели `/admin` можно включить обязательный логин на всём сайте. Удаление файлов
и аналитика по IP всегда только для админа.

---

## 1. Купи VPS

Минимум: **1 vCPU / 1 ГБ RAM / 20 ГБ диск / 1 ТБ трафика**.

- **Hetzner Cloud CX22** (Германия, ~€4/мес, 2 vCPU / 4 ГБ / 40 ГБ NVMe / 20 ТБ) — рекомендую
- DigitalOcean / Vultr / Linode — аналогичные планы по $6/мес

Образ — **Ubuntu 24.04 LTS** или Debian 12.

---

## 2. Базовая настройка сервера

Заходи по SSH (`ssh root@<твой-ip>`) и выполняй:

```bash
apt update && apt upgrade -y
apt install -y docker.io docker-compose-v2 git ufw

# Отдельный пользователь, не работаем из-под root
adduser --disabled-password --gecos "" yt2mp3
usermod -aG docker yt2mp3

# Firewall: SSH + HTTP/HTTPS (Caddy). Порт 8000 наружу НЕ открываем —
# приложение слушает только внутреннюю docker-сеть, наружу смотрит Caddy.
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable

# Дальше работаем под yt2mp3
su - yt2mp3
```

---

## 3. Залей код

### Вариант 1: git
```bash
git clone <твой-репо-url> yt2mp3
cd yt2mp3
```

### Вариант 2: rsync с Mac
На Маке:
```bash
cd /Users/gentyuk.valentin/Documents/projects/tripAnal
rsync -avz --exclude .venv --exclude downloads --exclude '*.db' --exclude '*.log' \
  --exclude data --exclude .git \
  ./ yt2mp3@<твой-ip>:/home/yt2mp3/yt2mp3/
```
На сервере:
```bash
cd ~/yt2mp3
```

---

## 4. Домен и настройки (.env)

### 4.1. Купи домен и направь A-запись на IP сервера

Например `yt2mp3.example.com → 5.6.7.8`. Любой регистратор (Namecheap, Reg.ru, Cloudflare).
Caddy получит Let's Encrypt сертификат автоматически по этому домену.

### 4.2. Заполни `.env`

```bash
cp .env.example .env
nano .env
```

```
DOMAIN=yt2mp3.example.com

# Учётка АДМИНА (нужна для админ-панели и переключателя логина).
# Сам сайт открыт всем по умолчанию — это только для /admin.
YT2MP3_AUTH_USER=admin
YT2MP3_AUTH_PASS=<длинный_рандомный_пароль>
YT2MP3_SECRET_KEY=<ещё_один_длинный_рандомный_токен>
```

Сгенерировать рандом:
```bash
openssl rand -base64 24      # пароль
openssl rand -base64 48      # secret_key
```

- **`DOMAIN`** — для авто-HTTPS. Должен резолвиться на этот сервер, порты 80/443 открыты.
- **`AUTH_USER/PASS`** — учётка админа. Без неё сайт полностью открыт и админки нет.
- **`SECRET_KEY`** — подписывает cookie-сессию. Если не задать — генерится случайно при
  каждом старте, и админа «выкидывает» при каждом рестарте. С заданным ключом логин
  держится ~14 дней.

> Файл `.env` в `.gitignore` — секреты в репозиторий не попадают. Не коммить пароли.

---

## 5. Запусти (приложение + Caddy + HTTPS — одной командой)

```bash
mkdir -p data
docker compose up -d --build
docker compose logs -f         # "Admin ENABLED (user=admin); site login: OPEN" — Ctrl+C
```

`docker-compose.yml` поднимает два контейнера: `yt2mp3` (слушает только внутреннюю
docker-сеть) и `caddy` (порты 80/443, авто-Let's Encrypt, reverse-proxy на приложение).

Открывай **`https://yt2mp3.твой-домен.com`** — настоящий HTTPS. Сайт открыт всем.

---

## 6. Управление доступом (открыто / под логином)

- По умолчанию сайт **открыт всем** — логин не нужен.
- Зайди на **`/admin`** (потребует логин админа из `.env`) → переключатель
  «Требовать логин для всего сайта». Включил — весь сайт под логином; выключил — снова
  открыт. Состояние хранится в БД (`data/yt2mp3.db`) и переживает рестарт.
- Удаление треков с сервера и аналитика «по IP» в любом режиме доступны только админу.

Запуск **без** Caddy (например, за своим nginx или для локального теста): добавь
приложению `ports: ["127.0.0.1:8000:8000"]`, убери сервис `caddy`, и поставь
`YT2MP3_SECURE_COOKIES=0`, если ходишь по HTTP.

---

## Операционка

### Логи
```bash
docker compose logs -f                    # хвост в реальном времени
docker compose logs --tail=200            # последние 200 строк
tail -f data/yt2mp3.log                   # из самого приложения
```

### Обновить приложение
```bash
cd ~/yt2mp3
git pull   # или rsync с мака
docker compose up -d --build
```

### Обновить yt-dlp (когда YouTube меняет API)

Полный rebuild (медленнее, но чисто):
```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

Быстрый hot-fix (на запущенном контейнере, до следующего rebuild):
```bash
docker exec -w /app yt2mp3 uv pip install --python /app/.venv/bin/python \
  --prerelease=allow --upgrade "yt-dlp>=$(date +%Y.%m.01)"
docker compose restart
```

> **Важно**: стабильный канал yt-dlp на PyPI иногда отстаёт от YouTube-фиксов на 1-2 месяца. Мы используем pre-release (nightly) channel — он публикуется на PyPI ежедневно и содержит свежие фиксы экстрактора. Это уже зашито в Dockerfile.

### Бекап SQLite + mp3 на свой Mac
```bash
# На маке:
rsync -avz yt2mp3@<ip>:/home/yt2mp3/yt2mp3/data/ ./yt2mp3-backup/
```

### Сменить пароль
```bash
nano .env       # поменяй YT2MP3_AUTH_PASS
docker compose up -d   # рестарт, новый пароль активен
```

### Размер базы / диска
```bash
du -sh data/
df -h
```

### Остановить
```bash
docker compose down       # стоп + удалить контейнер (данные в ./data сохранятся)
```

---

## Что мониторить

1. **Диск**. mp3 копятся — `du -sh data/downloads` раз в неделю
2. **YouTube IP-бан**. Если скачивания внезапно начинают падать с `HTTP Error 429` — обнови yt-dlp
3. **Логи на failed login attempts**: `docker compose logs | grep "failed login"` — если кто-то долбит брутом, стоит поставить fail2ban или ограничить IP в Caddyfile

---

## Если что-то не работает

| Симптом | Что проверить |
|---|---|
| Не открывается сайт | `docker compose ps` — контейнер running? `ufw status` — порт открыт? |
| 502 от Caddy | `docker compose logs` — приложение крутится? |
| `ffmpeg not found` в логах | `docker exec yt2mp3 ffmpeg -version` — должно отвечать |
| Скачивания всегда failed | `docker compose logs | grep ERROR` — yt-dlp скорее всего устарел |
| Постоянно «выкидывает» с залогина | `YT2MP3_SECRET_KEY` не задан — добавь в `.env`, рестарт |
| Забыл пароль | Поменяй `YT2MP3_AUTH_PASS` в `.env`, `docker compose up -d` |
