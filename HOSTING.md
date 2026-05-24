# Деплой yt2mp3 на удалённый сервер

Два варианта. Выбери один.

| | A. Tailscale (рекомендую) | B. Basic Auth + публичный порт |
|---|---|---|
| Кто видит сервер | Только твои устройства в Tailscale | Любой в интернете (с паролем) |
| Безопасность | Высокая (приватная mesh-сеть) | Средняя (пароль + опц. HTTPS) |
| Сложность | +1 шаг (`tailscale up`) | На 1 шаг проще |
| Юридическая поверхность | Нулевая (не торчит наружу) | Есть (видно сканерам) |
| HTTPS | Не нужен | Желателен (Caddy/Cloudflare) |

> **Я рекомендую вариант A.** YouTube-downloader публично торчащий в интернет — заявка на проблемы с хостером и YouTube IP-баны.

---

## Универсальная часть (для обоих вариантов)

### 1. Купи VPS

Минимум: **1 vCPU / 1 ГБ RAM / 20 ГБ диск / 1 ТБ трафика**. Подойдут:

- **Hetzner Cloud CX22** (Германия, ~€4/мес, 2 vCPU / 4 ГБ / 40 ГБ NVMe / 20 ТБ) — рекомендую
- DigitalOcean Basic ($6/мес)
- Vultr/Linode/любой VPS-провайдер

Образ — **Ubuntu 24.04 LTS** или Debian 12.

### 2. Заходи по SSH

```bash
ssh root@<твой-ip>
```

### 3. Базовая настройка сервера

```bash
# Обновись + ставь Docker
apt update && apt upgrade -y
apt install -y docker.io docker-compose-v2 git ufw

# Создай отдельного пользователя (не работай из-под root)
adduser --disabled-password --gecos "" yt2mp3
usermod -aG docker yt2mp3

# Простой firewall — открыт только SSH
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw enable

# Логинься как yt2mp3
su - yt2mp3
```

### 4. Забери код

Вариант 1 — клонируй из своего git-репо:
```bash
git clone <твой-репо-url> yt2mp3
cd yt2mp3
```

Вариант 2 — закинь файлы через scp с Mac (если репозитория ещё нет):
```bash
# На локальном маке:
cd /Users/gentyuk.valentin/Documents/projects/tripAnal
rsync -avz --exclude .venv --exclude downloads --exclude '*.db' --exclude '*.log' \
  ./ yt2mp3@<твой-ip>:/home/yt2mp3/yt2mp3/
```

---

## Вариант A: Tailscale (рекомендую)

### A1. Установи Tailscale

На сервере:
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```
Откроет ссылку — авторизуйся через свой Google/GitHub аккаунт (бесплатный план до 100 устройств).

На Mac:
```bash
brew install --cask tailscale-app
# или через App Store
```
Запусти Tailscale на Маке, залогинься тем же аккаунтом.

Проверь — на маке `tailscale status` покажет твой сервер.

### A2. Запусти yt2mp3 без Auth

`.env` оставь пустым (или вообще не создавай). docker-compose уже биндит порт только на `127.0.0.1` хоста — снаружи VPS не видно.

```bash
cd ~/yt2mp3
mkdir -p data
docker compose up -d --build
docker compose logs -f   # Ctrl+C когда увидишь "queue started"
```

### A3. Открой с Mac

В Tailscale у твоего сервера есть имя (типа `my-vps.tailnet-name.ts.net`).
```
http://<имя-сервера-в-tailscale>:8000
```

Но порт 8000 биндится только на 127.0.0.1 сервера — Tailscale его не видит. Два варианта починки:

**Простой — поменяй биндинг.** В `docker-compose.yml` замени:
```yaml
- "127.0.0.1:8000:8000"
```
на (Tailscale IP сервера — узнай через `tailscale ip -4` на VPS):
```yaml
- "100.x.y.z:8000:8000"
```

**Лучше — Tailscale Serve** (встроенный reverse-proxy с auto-HTTPS):
```bash
sudo tailscale serve --bg --https=443 http://127.0.0.1:8000
```
И открывай `https://<имя-сервера>.ts.net` — с настоящим Let's Encrypt сертификатом, только из Tailscale-сети.

---

## Вариант B: Basic Auth + публичный порт

### B1. Поставь пароль

На сервере:
```bash
cd ~/yt2mp3
cp .env.example .env
nano .env
```
Заполни:
```
YT2MP3_AUTH_USER=admin
YT2MP3_AUTH_PASS=<тут_длинный_рандомный_пароль>
```
Сгенерировать пароль: `openssl rand -base64 32`

### B2. Открой порт наружу

В `docker-compose.yml` замени `"127.0.0.1:8000:8000"` на `"8000:8000"`.

В firewall:
```bash
sudo ufw allow 8000/tcp
```

### B3. Запусти

```bash
mkdir -p data
docker compose up -d --build
docker compose logs -f
```

Открывай: `http://<ip-сервера>:8000` — браузер спросит логин/пароль.

### B4. (Опционально, но очень желательно) HTTPS через Caddy

Базовая Auth по голому HTTP — пароль ходит в открытом виде. Поставь Caddy:

```bash
# На сервере:
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy

# Caddyfile (заведи домен, направь A-запись на IP сервера)
sudo nano /etc/caddy/Caddyfile
```
```
yt2mp3.твой-домен.com {
    reverse_proxy 127.0.0.1:8000
}
```
```bash
sudo systemctl reload caddy
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw delete allow 8000/tcp
```
В `docker-compose.yml` верни `"127.0.0.1:8000:8000"` (наружу торчит только Caddy).

Caddy сам получит Let's Encrypt сертификат за 30 секунд.

---

## Операционка

### Логи
```bash
docker compose logs -f                    # хвост в реальном времени
docker compose logs --tail=200            # последние 200 строк
tail -f data/yt2mp3.log                    # из самого приложения (rotating)
```

### Обновить приложение
```bash
cd ~/yt2mp3
git pull   # или rsync с мака
docker compose up -d --build
```

### Бекап SQLite + mp3 на свой Mac
```bash
# На маке:
rsync -avz yt2mp3@<ip>:/home/yt2mp3/yt2mp3/data/ ./yt2mp3-backup/
```

### Обновить yt-dlp (при поломке YouTube API)
```bash
cd ~/yt2mp3
docker compose down
docker compose build --no-cache
docker compose up -d
```
Это перетянет последнюю версию yt-dlp с PyPI.

### Размер базы / диска
```bash
du -sh data/
df -h
```

### Остановить
```bash
docker compose down                       # стоп + удалить контейнер (данные в ./data сохранятся)
docker compose down -v                    # + удалить volumes (НЕ нужно — данные в bind-mount)
```

---

## Что мониторить

1. **Диск**. mp3 копятся — `du -sh data/downloads` раз в неделю.
2. **YouTube IP-бан**. Если скачивания внезапно начинают падать с `HTTP Error 429` — обнови yt-dlp.
3. **Логи Caddy/Nginx на 404/scan-попытки** — если боты долбят, добавь fail2ban.

---

## Если что-то не работает

| Симптом | Что проверить |
|---|---|
| 502 / нет ответа | `docker compose ps` — контейнер running? `docker compose logs` |
| `ffmpeg not found` | `docker exec yt2mp3 ffmpeg -version` — должно отвечать |
| Скачивания всегда failed | `docker compose logs | grep ERROR` — yt-dlp скорее всего устарел |
| 401 не вижу логин-окно | Используешь curl — добавь `-u admin:password`, или открой в браузере |
| `/healthz` ok, но `/` 401 | Auth работает корректно — введи логин/пароль |
