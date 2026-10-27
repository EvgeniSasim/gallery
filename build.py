#!/usr/bin/env python3
"""Собирает страницы аудиогида из content/ и media/."""

from __future__ import annotations

import json
import re
import struct
import sys
from pathlib import Path
from urllib.parse import urlparse

try:
    import segno
except ImportError:
    sys.stderr.write("Не найден пакет segno. Запустите ./build.sh\n")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"
MEDIA = ROOT / "media"
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".svg")
AUDIO_EXTS = (".mp3", ".m4a", ".ogg", ".wav")
SLOTS = [f"{i:02d}" for i in range(1, 19)]


def esc(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def load_site() -> dict:
    raw = json.loads((CONTENT / "site.json").read_text(encoding="utf-8"))
    base = str(raw.get("baseUrl", "")).rstrip("/")
    return {"kicker": str(raw.get("kicker") or "Аудиогид"), "baseUrl": base}


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1].strip()
    return value


def load_text(slot: str) -> tuple[dict, str]:
    path = CONTENT / f"{slot}.md"
    empty = {"title": "", "author": "", "year": ""}
    if not path.exists():
        return empty, ""
    raw = path.read_text(encoding="utf-8").lstrip("\ufeff")
    meta = dict(empty)
    body = raw
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            body = parts[2].strip()
            for line in parts[1].splitlines():
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                key = key.strip()
                if key in meta:
                    meta[key] = unquote(value)
    return meta, body.strip()


def find_media(slot: str, exts: tuple[str, ...]) -> Path | None:
    if not MEDIA.exists():
        return None
    found = []
    for path in MEDIA.iterdir():
        if not path.is_file():
            continue
        if path.stem.lower() == slot.lower() and path.suffix.lower() in exts:
            found.append(path)
    if not found:
        return None
    rank = {ext: index for index, ext in enumerate(exts)}
    found.sort(key=lambda path: rank.get(path.suffix.lower(), 99))
    return found[0]


def jpeg_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return None
    index = 2
    while index + 8 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            height, width = struct.unpack(">HH", data[index + 5 : index + 9])
            return width, height
        if marker in (0xD8, 0xD9):
            index += 2
            continue
        if index + 4 > len(data):
            break
        segment = struct.unpack(">H", data[index + 2 : index + 4])[0]
        index += 2 + segment
    return None


def webp_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    chunk = data[12:16]
    if chunk == b"VP8X":
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return width, height
    if chunk == b"VP8 ":
        start = data.find(b"\x9d\x01\x2a")
        if start != -1 and start + 7 <= len(data):
            width = int.from_bytes(data[start + 3 : start + 5], "little") & 0x3FFF
            height = int.from_bytes(data[start + 5 : start + 7], "little") & 0x3FFF
            return width, height
    if chunk == b"VP8L":
        bits = int.from_bytes(data[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    return None


def image_size(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes()
    suffix = path.suffix.lower()
    if suffix == ".png" and data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if suffix in {".jpg", ".jpeg"}:
        return jpeg_size(data)
    if suffix == ".webp":
        return webp_size(data)
    if suffix == ".svg":
        text = data.decode("utf-8", errors="ignore")
        width = re.search(r'\bwidth="([\d.]+)', text)
        height = re.search(r'\bheight="([\d.]+)', text)
        if width and height:
            return int(float(width.group(1))), int(float(height.group(1)))
    return None


def dim_attrs(size: tuple[int, int] | None) -> str:
    if not size:
        return ""
    width, height = size
    return f' width="{width}" height="{height}"'


def paragraphs(body: str) -> str:
    chunks = re.split(r"\n\s*\n", body.strip())
    html = []
    for chunk in chunks:
        text = re.sub(r"\s*\n\s*", " ", chunk).strip()
        if text:
            html.append(f"<p>{esc(text)}</p>")
    return "\n".join(html)


def meta_description(body: str, fallback: str) -> str:
    flat = re.sub(r"\s+", " ", body).strip()
    if not flat:
        return fallback
    if len(flat) <= 160:
        return flat
    cut = flat[:157].rsplit(" ", 1)[0]
    return cut + "…"


def display_title(slot: str, title: str) -> str:
    if title:
        return title
    if slot == "primer":
        return "Образец страницы"
    return f"Картина {slot}"


def corner_label(slot: str) -> str:
    if slot == "primer":
        return "Образец"
    return slot


def status_text(body: str, image: Path | None, audio: Path | None) -> tuple[str, str]:
    missing = []
    if not body.strip():
        missing.append("текста")
    if image is None:
        missing.append("изображения")
    if audio is None:
        missing.append("аудио")
    if not missing:
        return "готово", "is-ready"
    if len(missing) == 1:
        return f"нет {missing[0]}", "is-missing"
    if len(missing) == 2:
        return f"нет {missing[0]} и {missing[1]}", "is-missing"
    return "нет текста, изображения и аудио", "is-missing"


def asset_url(base: str, name: str) -> str:
    return f"{base}/media/{name}"


def document(
    *,
    html_class: str,
    body_class: str,
    title: str,
    description: str,
    asset_prefix: str,
    canonical: str,
    extra_head: str,
    theme: str,
    body: str,
) -> str:
    if theme == "light":
        theme_meta = '<meta name="theme-color" content="#f4f1eb">'
    else:
        theme_meta = "\n".join(
            [
                '<meta name="theme-color" media="(prefers-color-scheme: light)" content="#f4f1eb">',
                '<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#141311">',
            ]
        )
    html_attr = f' class="{html_class}"' if html_class else ""
    canonical_tag = f'<link rel="canonical" href="{esc(canonical)}">' if canonical else ""
    return f"""<!DOCTYPE html>
<html lang="ru"{html_attr}>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<script>document.documentElement.classList.add("js")</script>
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
{theme_meta}
<link rel="icon" href="{asset_prefix}assets/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="{asset_prefix}assets/style.css">
{canonical_tag}
{extra_head}
<script defer src="{asset_prefix}assets/guide.js"></script>
</head>
<body class="{body_class}">
{body}
</body>
</html>
"""


def player_html(src: str) -> str:
    return f"""<div class="dock" data-player hidden>
  <div class="dock__inner">
    <button type="button" class="play-cta" data-start>
      <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M9 7.2v9.6L16.8 12 9 7.2z"/></svg>
      <span>Слушать описание</span>
      <span class="cta-duration" data-cta-duration hidden></span>
    </button>
    <div class="transport" data-transport hidden>
      <div class="transport__top">
        <button type="button" class="toggle" data-toggle aria-pressed="true" aria-label="Пауза">
          <span class="mark" aria-hidden="true">
            <svg data-icon-play hidden viewBox="0 0 24 24"><path d="M9 7.2v9.6L16.8 12 9 7.2z"/></svg>
            <svg data-icon-pause viewBox="0 0 24 24"><path d="M8 6.5h2.6v11H8zm5.4 0H16v11h-2.6z"/></svg>
          </span>
          <span data-toggle-label>Пауза</span>
        </button>
        <button type="button" class="speed" data-speed aria-label="Скорость воспроизведения 1×">1×</button>
      </div>
      <div class="transport__bottom">
        <span class="time-current" data-current>0:00</span>
        <input class="seek" data-seek type="range" min="0" max="1000" value="0" step="1" aria-label="Позиция воспроизведения" aria-valuemin="0" aria-valuemax="1000" aria-valuenow="0" aria-valuetext="0:00">
        <span class="time-duration" data-duration>0:00</span>
      </div>
    </div>
    <p class="player__error" data-error hidden role="alert">Не удалось загрузить аудио. Проверьте соединение и откройте страницу ещё раз.</p>
  </div>
</div>
<audio controls preload="metadata" data-audio src="{esc(src)}"></audio>
<script>document.querySelector("[data-player]")?.removeAttribute("hidden")</script>"""


def figure_html(src: str | None, alt: str, dims: str) -> str:
    if not src:
        return """<figure class="figure">
  <div class="frame frame--empty" role="img" aria-label="Изображение ещё не добавлено"></div>
</figure>"""
    return f"""<figure class="figure">
  <button type="button" class="zoom" data-zoom>
    <img src="{esc(src)}" alt="{esc(alt)}"{dims}>
    <span class="sr-only">Увеличить изображение</span>
  </button>
  <figcaption>Нажмите на изображение, чтобы увеличить</figcaption>
</figure>"""


def lightbox_html(src: str | None, alt: str, dims: str) -> str:
    if not src:
        return ""
    return f"""<dialog class="lightbox" data-lightbox aria-label="Увеличенное изображение">
  <button type="button" class="lightbox__close" data-close aria-label="Закрыть">
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M7 7l10 10M17 7L7 17" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
  </button>
  <div class="lightbox__stage">
    <img src="{esc(src)}" alt="" {dims}>
  </div>
</dialog>"""


def guide_page(site: dict, slot: str) -> dict:
    meta, body = load_text(slot)
    image = find_media(slot, IMAGE_EXTS)
    audio = find_media(slot, AUDIO_EXTS)
    title = display_title(slot, meta["title"])
    byline = ", ".join(part for part in (meta["author"], meta["year"]) if part)
    prefix = "../"
    image_src = f"{prefix}media/{image.name}" if image else None
    audio_src = f"{prefix}media/{audio.name}" if audio else None
    dims = dim_attrs(image_size(image)) if image else ""
    alt = title if not meta["author"] else f"{title}. {meta['author']}"
    blank = not any((meta["title"], meta["author"], meta["year"], body, image, audio))
    text_html = paragraphs(body)
    if blank:
        text_html = '<p class="pending">Материалы этой картины ещё не опубликованы.</p>'
    elif text_html:
        text_html = f'<div class="text">\n{text_html}\n</div>'
    else:
        text_html = ""
    byline_html = f'<p class="byline">{esc(byline)}</p>' if byline else ""
    player = player_html(audio_src) if audio_src else ""
    description = meta_description(body, f"{site['kicker']}. {title}.")
    page_title = f"{title} — {site['kicker']}"
    canonical = f"{site['baseUrl']}/{slot}/" if site["baseUrl"] else ""
    extra = [
        f'<meta property="og:type" content="article">',
        f'<meta property="og:title" content="{esc(page_title)}">',
        f'<meta property="og:description" content="{esc(description)}">',
        '<meta property="og:locale" content="ru_RU">',
    ]
    if image and site["baseUrl"] and image.suffix.lower() != ".svg":
        extra.append(f'<meta property="og:image" content="{esc(asset_url(site["baseUrl"], image.name))}">')
    classes = "guide has-audio" if audio else "guide"
    body_html = f"""<main class="sheet">
  <article>
    <header class="heading">
      <div class="kicker-row">
        <p class="kicker">{esc(site["kicker"])}</p>
        <p class="number">{esc(corner_label(slot))}</p>
      </div>
      <h1>{esc(title)}</h1>
      {byline_html}
    </header>
    {figure_html(image_src, alt, dims)}
    {text_html}
  </article>
</main>
{player}
{lightbox_html(image_src, alt, dims)}"""
    html = document(
        html_class="",
        body_class=classes,
        title=page_title,
        description=description,
        asset_prefix=prefix,
        canonical=canonical,
        extra_head="\n".join(extra),
        theme="both",
        body=body_html,
    )
    state, state_class = status_text(body, image, audio)
    return {
        "slot": slot,
        "title": title,
        "html": html,
        "state": state,
        "state_class": state_class,
        "url": canonical or f"{slot}/",
    }


def index_page(site: dict, primer: dict | None, pages: list[dict]) -> str:
    def row(page: dict) -> str:
        return f"""<li class="row">
  <a class="row__id" href="{esc(page["slot"])}/">{esc(corner_label(page["slot"]))}</a>
  <div>
    <a class="row__title" href="{esc(page["slot"])}/">{esc(page["title"])}</a>
    <p class="row__status {page["state_class"]}">{esc(page["state"])}</p>
    <p class="row__url"><a href="{esc(page["url"])}">{esc(page["url"])}</a></p>
  </div>
  <button type="button" class="button" data-copy="{esc(page["url"])}">Копировать</button>
</li>"""

    primer_html = ""
    if primer:
        primer_html = f"<h2>Образец</h2>\n<ul class=\"catalog\">\n{row(primer)}\n</ul>"
    rows = "\n".join(row(page) for page in pages)
    qr_href = "qr/"
    body = f"""<main class="sheet sheet--wide">
  <header class="heading">
    <p class="kicker">{esc(site["kicker"])}</p>
    <h1>Страницы для QR</h1>
    <p class="lead">18 адресов, по одному на картину. Номер в ссылке не меняется: код можно печатать сразу, а фотографию, текст и аудио добавить позже.</p>
    <div class="actions no-print">
      <a class="button" href="{qr_href}">Печать QR-кодов</a>
    </div>
  </header>
  {primer_html}
  <h2>Картины</h2>
  <ul class="catalog">
    {rows}
  </ul>
</main>"""
    canonical = f"{site['baseUrl']}/" if site["baseUrl"] else ""
    return document(
        html_class="",
        body_class="index",
        title=f"Страницы для QR — {site['kicker']}",
        description="Страницы аудиогида: изображение, текст и аудио для каждой картины.",
        asset_prefix="",
        canonical=canonical,
        extra_head="",
        theme="both",
        body=body,
    )


def qr_page(site: dict, pages: list[dict]) -> str:
    cards = []
    for page in pages:
        cards.append(
            f"""<a class="qr-card" href="../{esc(page["slot"])}/">
  <img src="{esc(page["slot"])}.svg" alt="QR-код, картина {esc(page["slot"])}">
  <span class="qr-card__id">{esc(page["slot"])}</span>
  <span class="qr-card__title">{esc(page["title"])}</span>
</a>"""
        )
    body = f"""<main class="sheet sheet--wide">
  <header class="heading">
    <p class="kicker">{esc(site["kicker"])}</p>
    <h1>QR-коды</h1>
    <p class="lead">По одному коду на картину. Перед тем как крепить, наведите камеру телефона и проверьте номер.</p>
    <div class="actions no-print">
      <button type="button" class="button" data-print>Печать</button>
      <a class="button" href="../">Все страницы</a>
    </div>
  </header>
  <div class="qr-grid">
    {chr(10).join(cards)}
  </div>
</main>"""
    canonical = f"{site['baseUrl']}/qr/" if site["baseUrl"] else ""
    return document(
        html_class="theme-light",
        body_class="qr",
        title=f"QR-коды — {site['kicker']}",
        description="Лист QR-кодов для табличек рядом с картинами.",
        asset_prefix="../",
        canonical=canonical,
        extra_head="",
        theme="light",
        body=body,
    )


def missing_page(site: dict) -> str:
    home = f"{site['baseUrl']}/" if site["baseUrl"] else "./"
    style = f"{site['baseUrl']}/assets/style.css" if site["baseUrl"] else "assets/style.css"
    icon = f"{site['baseUrl']}/assets/favicon.svg" if site["baseUrl"] else "assets/favicon.svg"
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Такой страницы нет — {esc(site["kicker"])}</title>
<link rel="icon" href="{esc(icon)}" type="image/svg+xml">
<link rel="stylesheet" href="{esc(style)}">
</head>
<body class="index">
<main class="sheet">
  <p class="kicker">{esc(site["kicker"])}</p>
  <h1>Такой страницы нет</h1>
  <p class="lead">Проверьте номер на табличке. Список картин — на главной.</p>
  <div class="actions"><a class="button" href="{esc(home)}">Все страницы</a></div>
</main>
</body>
</html>
"""


def write_qr(url: str, dest: Path) -> None:
    code = segno.make(url, error="h", micro=False)
    code.save(dest, scale=4, border=4, dark="#1c1916", light="#ffffff")


def main() -> None:
    site = load_site()
    primer = guide_page(site, "primer")
    pages = [guide_page(site, slot) for slot in SLOTS]
    write(ROOT / "index.html", index_page(site, primer, pages))
    write(ROOT / "primer" / "index.html", primer["html"])
    write(ROOT / "404.html", missing_page(site))
    write(ROOT / "qr" / "index.html", qr_page(site, pages))
    prefix = urlparse(site["baseUrl"]).path.rstrip("/") if site["baseUrl"] else ""
    for page in pages:
        write(ROOT / page["slot"] / "index.html", page["html"])
        target = f"{site['baseUrl']}/{page['slot']}/" if site["baseUrl"] else f"{prefix}/{page['slot']}/"
        write_qr(target, ROOT / "qr" / f"{page['slot']}.svg")
    ready = sum(1 for page in pages if page["state_class"] == "is-ready")
    print(f"Страниц картин: {len(pages)}")
    print(f"Полностью готовы: {ready}")
    print(f"Образец: {primer['url']}")
    print(f"QR: {site['baseUrl']}/qr/" if site["baseUrl"] else "QR: qr/")


if __name__ == "__main__":
    main()
