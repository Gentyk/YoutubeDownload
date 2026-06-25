"""Minimal i18n — no deps. Translations dict + per-request current language.

Language is chosen from the ``lang`` cookie, then ``Accept-Language``, then the
default. Templates call ``t('key')`` (a Jinja global bound to the current lang).
"""

from __future__ import annotations

from contextvars import ContextVar

from yt2mp3 import config

_current: ContextVar[str] = ContextVar("lang", default=config.DEFAULT_LANG)

LANG_NAMES = {"ru": "Русский", "en": "English", "fr": "Français", "de": "Deutsch"}
LANG_FLAGS = {"ru": "🇷🇺", "en": "🇬🇧", "fr": "🇫🇷", "de": "🇩🇪"}

# key -> {lang: text}
TRANSLATIONS: dict[str, dict[str, str]] = {
    # nav
    "nav_download": {"ru": "Скачать", "en": "Download", "fr": "Télécharger", "de": "Herunterladen"},
    "nav_library": {"ru": "Загружено", "en": "Library", "fr": "Bibliothèque", "de": "Bibliothek"},
    "nav_stats": {"ru": "Статистика", "en": "Stats", "fr": "Stats", "de": "Statistik"},
    "nav_admin": {"ru": "Админ", "en": "Admin", "fr": "Admin", "de": "Admin"},
    "nav_login": {"ru": "Войти", "en": "Sign in", "fr": "Connexion", "de": "Anmelden"},
    "nav_logout": {"ru": "Выйти", "en": "Sign out", "fr": "Déconnexion", "de": "Abmelden"},
    # hero / index
    "hero_title": {"ru": "Вставь ссылку — получи MP3", "en": "Paste a link — get an MP3",
                   "fr": "Collez un lien — obtenez un MP3", "de": "Link einfügen — MP3 erhalten"},
    "hero_sub": {
        "ru": "YouTube-ссылки в любом виде — через запятую, пробел или с новой строки. Имя файла = название видео.",
        "en": "YouTube links in any form — comma, space or newline separated. Filename = video title.",
        "fr": "Liens YouTube sous toute forme — séparés par virgule, espace ou retour. Nom = titre de la vidéo.",
        "de": "YouTube-Links in jeder Form — durch Komma, Leerzeichen oder Zeilen getrennt. Dateiname = Videotitel.",
    },
    "form_placeholder": {"ru": "https://www.youtube.com/watch?v=…", "en": "https://www.youtube.com/watch?v=…",
                         "fr": "https://www.youtube.com/watch?v=…", "de": "https://www.youtube.com/watch?v=…"},
    "form_hint": {"ru": "⌘/Ctrl+Enter — отправить.", "en": "⌘/Ctrl+Enter — submit.",
                  "fr": "⌘/Ctrl+Entrée — envoyer.", "de": "⌘/Strg+Enter — senden."},
    "force_label": {"ru": "Скачать заново, даже если уже есть", "en": "Re-download even if it exists",
                    "fr": "Retélécharger même si présent", "de": "Erneut laden, auch wenn vorhanden"},
    "playlist_label": {"ru": "Разворачивать плейлист целиком", "en": "Expand the whole playlist",
                       "fr": "Développer toute la playlist", "de": "Ganze Playlist aufklappen"},
    "submit": {"ru": "Скачать", "en": "Download", "fr": "Télécharger", "de": "Herunterladen"},
    "view_stats": {"ru": "Смотреть статистику →", "en": "View stats →", "fr": "Voir les stats →", "de": "Statistik ansehen →"},
    "queue_title": {"ru": "Очередь", "en": "Queue", "fr": "File", "de": "Warteschlange"},
    "queue_updates": {"ru": "обновляется каждые 2с", "en": "updates every 2s", "fr": "maj toutes les 2s", "de": "alle 2s aktualisiert"},
    "queue_empty": {"ru": "Пока пусто.", "en": "Nothing yet.", "fr": "Rien pour l’instant.", "de": "Noch nichts."},
    # recent panel
    "just_ready": {"ru": "Только что готово", "en": "Just ready", "fr": "Prêt à l’instant", "de": "Gerade fertig"},
    "all_arrow": {"ru": "Все →", "en": "All →", "fr": "Tout →", "de": "Alle →"},
    # library
    "library_title": {"ru": "Загружено", "en": "Your library", "fr": "Votre bibliothèque", "de": "Deine Bibliothek"},
    "player": {"ru": "Мой плеер", "en": "My player", "fr": "Mon lecteur", "de": "Mein Player"},
    "library_empty_title": {"ru": "Пока ничего не скачано.", "en": "Nothing downloaded yet.",
                            "fr": "Rien téléchargé pour l’instant.", "de": "Noch nichts geladen."},
    "library_empty_sub": {"ru": "Скачай первый трек на главной — он появится здесь.",
                          "en": "Download your first track on the home page — it’ll show up here.",
                          "fr": "Téléchargez un premier titre sur l’accueil — il apparaîtra ici.",
                          "de": "Lade auf der Startseite den ersten Track — er erscheint hier."},
    "go_download": {"ru": "Перейти к загрузке", "en": "Go to download", "fr": "Aller au téléchargement", "de": "Zum Download"},
    "download_to_device": {"ru": "Скачать на устройство", "en": "Save to device", "fr": "Enregistrer", "de": "Aufs Gerät laden"},
    "delete_from_server": {"ru": "Удалить с сервера", "en": "Delete from server", "fr": "Supprimer du serveur", "de": "Vom Server löschen"},
    "tracks_word": {"ru": "треков", "en": "tracks", "fr": "pistes", "de": "Titel"},
    "only_your_tracks": {"ru": "Видны только твои треки.", "en": "Only your tracks are shown.",
                         "fr": "Seules vos pistes sont affichées.", "de": "Nur deine Titel werden gezeigt."},
    # form results
    "no_valid_urls": {"ru": "Не нашёл ни одной валидной YouTube-ссылки", "en": "No valid YouTube link found",
                      "fr": "Aucun lien YouTube valide trouvé", "de": "Kein gültiger YouTube-Link gefunden"},
    "queue_full": {"ru": "Очередь переполнена, подожди немного", "en": "Queue is full, try again shortly",
                   "fr": "File pleine, réessayez bientôt", "de": "Warteschlange voll, bitte später"},
    "added_to_queue": {"ru": "Добавлено в очередь", "en": "Added to queue", "fr": "Ajouté à la file", "de": "Zur Warteschlange"},
    "already_downloaded": {"ru": "Уже было скачано раньше — пропущено:", "en": "Already downloaded — skipped:",
                           "fr": "Déjà téléchargé — ignoré :", "de": "Bereits geladen — übersprungen:"},
    "download_existing": {"ru": "скачать существующий", "en": "download existing", "fr": "télécharger l’existant", "de": "vorhandenes laden"},
    "cancel": {"ru": "Отмена", "en": "Cancel", "fr": "Annuler", "de": "Abbrechen"},
    # admin
    "admin_panel": {"ru": "Админ-панель", "en": "Admin panel", "fr": "Panneau admin", "de": "Admin-Bereich"},
    "require_login_title": {"ru": "Требовать логин для всего сайта", "en": "Require login for the whole site",
                            "fr": "Exiger une connexion pour tout le site", "de": "Login für die ganze Seite verlangen"},
    "open_for_all": {"ru": "Открыть для всех", "en": "Open to everyone", "fr": "Ouvrir à tous", "de": "Für alle öffnen"},
    "close_with_login": {"ru": "Закрыть логином", "en": "Close with login", "fr": "Fermer par connexion", "de": "Mit Login schließen"},
    "system_load": {"ru": "Нагрузка сервера", "en": "Server load", "fr": "Charge serveur", "de": "Serverauslastung"},
    "cpu": {"ru": "Процессор", "en": "CPU", "fr": "Processeur", "de": "Prozessor"},
    "ram": {"ru": "Память", "en": "RAM", "fr": "Mémoire", "de": "Arbeitsspeicher"},
    # login
    "login_title": {"ru": "Вход", "en": "Sign in", "fr": "Connexion", "de": "Anmelden"},
    "username": {"ru": "Логин", "en": "Username", "fr": "Identifiant", "de": "Benutzername"},
    "password": {"ru": "Пароль", "en": "Password", "fr": "Mot de passe", "de": "Passwort"},
    "sign_in": {"ru": "Войти", "en": "Sign in", "fr": "Se connecter", "de": "Anmelden"},
    # queue states
    "q_queued": {"ru": "в очереди", "en": "queued", "fr": "en file", "de": "in Warteschlange"},
    "q_downloading": {"ru": "качаем", "en": "downloading", "fr": "téléchargement", "de": "lädt"},
    "q_converting": {"ru": "конвертируем", "en": "converting", "fr": "conversion", "de": "konvertiert"},
    "q_done": {"ru": "готово", "en": "done", "fr": "fini", "de": "fertig"},
    "q_failed": {"ru": "ошибка", "en": "error", "fr": "erreur", "de": "Fehler"},
    "q_cancelled": {"ru": "отменено", "en": "cancelled", "fr": "annulé", "de": "abgebrochen"},
    "playlist_need_expand": {
        "ru": "Это плейлист — включи «разворачивать плейлист».",
        "en": "That's a playlist — enable “expand playlist”.",
        "fr": "C'est une playlist — activez « développer la playlist ».",
        "de": "Das ist eine Playlist — „Playlist aufklappen“ aktivieren.",
    },
    "evict_warn": {
        "ru": "Лимит {cap} треков. Удалятся {n} самых старых.",
        "en": "Limit {cap} tracks. The {n} oldest will be removed.",
        "fr": "Limite {cap} pistes. Les {n} plus anciennes seront supprimées.",
        "de": "Limit {cap} Titel. Die {n} ältesten werden entfernt.",
    },
    "footer": {"ru": "yt2mp3 — личный архив. Видны только треки с твоего устройства.",
               "en": "yt2mp3 — personal archive. Only tracks from your device are shown.",
               "fr": "yt2mp3 — archive personnelle. Seules les pistes de votre appareil.",
               "de": "yt2mp3 — persönliches Archiv. Nur Titel von deinem Gerät."},
}


# Strings used by the interactive front-end engine (static/app.js).
JS_STRINGS: dict[str, dict[str, str]] = {
    "ru": {
        "placeholder": "Вставь ссылку на YouTube… можно несколько сразу",
        "go": "Скачать ↑", "emptyTitle": "Тут пока пусто и тихо",
        "emptySub": "Вставь или перетащи ссылку — и она вспорхнёт сюда шариком ↑",
        "dropHere": "Брось ссылку сюда", "queued": "в очереди", "downloading": "качается",
        "converting": "конвертируем", "ready": "готово", "failed": "ошибка", "retry": "↻ Повторить",
        "player": "Мой плеер", "listenSave": "Слушай или сохраняй готовое",
        "play": "Слушать", "pause": "Пауза", "save": "↓ Скачать", "remove": "Убрать",
        "dlAll": "↓ Скачать всё", "clear": "Очистить", "emptyTracks": "Здесь появятся готовые треки 🎧",
        "needLink": "Вставь ссылку на YouTube", "first8": "Добавил первые 8 ссылок",
        "dlToast": "Скачивание", "dropVideo": "Перетащи ссылку на видео",
        "themeMango": "Манго", "themeSunset": "Закат", "themeCaramel": "Карамель",
        "soundAria": "Звук", "themeAria": "Оформление", "tracks": "треков", "del": "Удалить",
    },
    "en": {
        "placeholder": "Paste a YouTube link… several at once is fine",
        "go": "Download ↑", "emptyTitle": "Empty and quiet for now",
        "emptySub": "Paste or drop a link — it'll flutter up here as a ball ↑",
        "dropHere": "Drop the link here", "queued": "queued", "downloading": "downloading",
        "converting": "converting", "ready": "done", "failed": "error", "retry": "↻ Retry",
        "player": "My player", "listenSave": "Listen or save your tracks",
        "play": "Play", "pause": "Pause", "save": "↓ Save", "remove": "Remove",
        "dlAll": "↓ Download all", "clear": "Clear", "emptyTracks": "Your finished tracks land here 🎧",
        "needLink": "Paste a YouTube link", "first8": "Added the first 8 links",
        "dlToast": "Downloading", "dropVideo": "Drop a video link",
        "themeMango": "Mango", "themeSunset": "Sunset", "themeCaramel": "Caramel",
        "soundAria": "Sound", "themeAria": "Theme", "tracks": "tracks", "del": "Delete",
    },
    "fr": {
        "placeholder": "Collez un lien YouTube… plusieurs à la fois, c'est bon",
        "go": "Télécharger ↑", "emptyTitle": "Vide et silencieux pour l'instant",
        "emptySub": "Collez ou déposez un lien — il s'envolera ici en bulle ↑",
        "dropHere": "Déposez le lien ici", "queued": "en file", "downloading": "téléchargement",
        "converting": "conversion", "ready": "fini", "failed": "erreur", "retry": "↻ Réessayer",
        "player": "Mon lecteur", "listenSave": "Écoutez ou enregistrez vos pistes",
        "play": "Écouter", "pause": "Pause", "save": "↓ Enregistrer", "remove": "Retirer",
        "dlAll": "↓ Tout télécharger", "clear": "Vider", "emptyTracks": "Vos pistes finies arrivent ici 🎧",
        "needLink": "Collez un lien YouTube", "first8": "8 premiers liens ajoutés",
        "dlToast": "Téléchargement", "dropVideo": "Déposez un lien vidéo",
        "themeMango": "Mangue", "themeSunset": "Coucher", "themeCaramel": "Caramel",
        "soundAria": "Son", "themeAria": "Thème", "tracks": "pistes", "del": "Supprimer",
    },
    "de": {
        "placeholder": "YouTube-Link einfügen… mehrere gleichzeitig sind ok",
        "go": "Laden ↑", "emptyTitle": "Noch leer und still",
        "emptySub": "Link einfügen oder ziehen — er fliegt als Kugel hierher ↑",
        "dropHere": "Link hier ablegen", "queued": "wartet", "downloading": "lädt",
        "converting": "konvertiert", "ready": "fertig", "failed": "Fehler", "retry": "↻ Erneut",
        "player": "Mein Player", "listenSave": "Höre oder speichere deine Titel",
        "play": "Abspielen", "pause": "Pause", "save": "↓ Speichern", "remove": "Entfernen",
        "dlAll": "↓ Alle laden", "clear": "Leeren", "emptyTracks": "Fertige Titel landen hier 🎧",
        "needLink": "YouTube-Link einfügen", "first8": "Erste 8 Links hinzugefügt",
        "dlToast": "Download", "dropVideo": "Videolink ablegen",
        "themeMango": "Mango", "themeSunset": "Sonnenuntergang", "themeCaramel": "Karamell",
        "soundAria": "Ton", "themeAria": "Thema", "tracks": "Titel", "del": "Löschen",
    },
}


def js_bundle() -> dict[str, str]:
    """Front-end strings for the current language (with English fallback)."""
    lang = _current.get()
    base = dict(JS_STRINGS.get("en", {}))
    base.update(JS_STRINGS.get(lang, {}))
    return base


def all_bundle() -> dict[str, dict[str, str]]:
    """Every key in every language — for instant client-side switching.

    Merges page TRANSLATIONS + front-end JS_STRINGS into one {lang: {key: text}}.
    """
    out: dict[str, dict[str, str]] = {}
    for lang in config.SUPPORTED_LANGS:
        d: dict[str, str] = {}
        for key, m in TRANSLATIONS.items():
            d[key] = m.get(lang) or m.get("en") or key
        d.update(JS_STRINGS.get("en", {}))
        d.update(JS_STRINGS.get(lang, {}))
        out[lang] = d
    return out


def set_lang(lang: str) -> None:
    _current.set(lang if lang in config.SUPPORTED_LANGS else config.DEFAULT_LANG)


def get_lang() -> str:
    return _current.get()


def t(key: str, **kwargs: object) -> str:
    entry = TRANSLATIONS.get(key)
    if not entry:
        return key
    lang = _current.get()
    text = entry.get(lang) or entry.get("en") or entry.get(config.DEFAULT_LANG) or key
    return text.format(**kwargs) if kwargs else text


def pick_lang(cookie_val: str | None, accept_language: str | None) -> str:
    """Choose a language: cookie > Accept-Language > default."""
    if cookie_val in config.SUPPORTED_LANGS:
        return cookie_val
    if accept_language:
        for part in accept_language.split(","):
            code = part.split(";")[0].strip().lower()[:2]
            if code in config.SUPPORTED_LANGS:
                return code
    return config.DEFAULT_LANG
