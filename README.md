# Аудиогид

Страницы для QR-кодов на картинах. Адрес не меняется, когда появляются фотография, текст и запись.

Сайт: https://evgenisasim.github.io/gallery/

Лист QR: https://evgenisasim.github.io/gallery/qr/

## Материалы

Номера `01`–`18`.

- `media/01.jpg` — изображение (jpg, png, webp). Длинная сторона около 1600 px
- `media/01.mp3` — голос (mp3 или m4a, для речи хватает 96 kbps)
- `content/01.md` — название и текст

```markdown
---
title: Название
author: Автор
year: 1916
---

Первый абзац.

Второй абзац.
```

Образец готовой карточки: `content/primer.md`, `media/primer.svg`, `media/primer.m4a`.

## Публикация правок

```sh
./build.sh
git add -A
git commit -m "Обновить материалы картин"
git push
```
