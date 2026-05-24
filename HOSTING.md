# Деплой yt2mp3 на удалённый сервер

Что получится: обычный сайт по адресу `http://<твой-ip>:8000` (или `https://yt2mp3.твой-домен.com` если повесишь Caddy) с формой логина — ввёл логин/пароль, и пользуешься как локально.

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

# Firewall: открываем SSH и порт приложения
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 8000/tcp
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

## 4. Настрой логин и пароль

```bash
cp .env.example .env
nano .env
```

Заполни:
```
YT2MP3_AUTH_USER=admin
YT2MP3_AUTH_PASS=<длинный_рандомный_пароль>
YT2MP3_SECRET_KEY=<ещё_один_длинный_рандомный_токен>
```

Сгенерировать рандом одной командой:
```bash
openssl rand -base64 24      # пароль
openssl rand -base64 48      # secret_key
```

**Зачем `SECRET_KEY`**: подписывает cookie-сессию. Если не задать — генерится случайно при каждом старте, и тебя будет «выкидывать» при каждом перезапуске контейнера. С заданным `SECRET_KEY` логин сохраняется надолго (по умолчанию 14 дней).

---

## 5. Открой порт наружу

В `docker-compose.yml` поменяй:
```yaml
- "127.0.0.1:8000:8000"
```
на:
```yaml
- "8000:8000"
```

---

## 6. Запусти

```bash
mkdir -p data
docker compose up -d --build
docker compose logs -f         # увидишь "Login ENABLED (user=admin)" — жми Ctrl+C
```

Открывай в браузере: **`http://<ip-сервера>:8000`** — увидишь форму логина. Войдёшь — попадёшь на главную, всё работает как локально.

---

## 7. (Опционально, но желательно) HTTPS через Caddy

Если оставить как есть — пароль ходит в открытом виде по HTTP. Это **плохо**, если ты собираешься пользоваться из публичных Wi-Fi сетей. Поставь Caddy с авто-HTTPS:

### 7.1. Купи домен и направь A-запись на IP сервера

Например, `yt2mp3.example.com → 5.6.7.8`. Любой регистратор работает (Namecheap, Reg.ru, Cloudflare).

### 7.2. Установи Caddy

```bash
# На сервере, под root (exit из yt2mp3-сессии или sudo)
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

### 7.3. Caddyfile

```bash
sudo nano /etc/caddy/Caddyfile
```
Содержимое:
```
yt2mp3.твой-домен.com {
    reverse_proxy 127.0.0.1:8000
}
```

### 7.4. Закрой 8000, открой 443

```bash
sudo systemctl reload caddy
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw delete allow 8000/tcp
```

В `docker-compose.yml` верни биндинг на localhost (Caddy сам ходит туда):
```yaml
- "127.0.0.1:8000:8000"
```
Перезапусти приложение:
```bash
docker compose up -d
```

Caddy сам получит Let's Encrypt сертификат за 30 секунд. Открывай **`https://yt2mp3.твой-домен.com`** — настоящий HTTPS, пароль больше не утекает.

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
```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

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
