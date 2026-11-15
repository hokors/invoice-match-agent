"""Makes a clean invoice image look like a cheap office scan or a phone photo."""
from __future__ import annotations

import random

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps


def _speckle(img: Image.Image, rng: random.Random, amount: int) -> Image.Image:
    noise = Image.effect_noise(img.size, rng.uniform(18, 30)).convert("L")
    noise = ImageEnhance.Contrast(noise).enhance(0.25 + amount / 100)
    return ImageChops.multiply(img.convert("L"), ImageOps.autocontrast(noise, cutoff=(0, 60))).convert("RGB")


def scan(img: Image.Image, rng: random.Random) -> Image.Image:
    """Grayscale, slightly rotated, toner noise, soft focus, light streak, low JPEG quality."""
    out = ImageOps.grayscale(img).convert("RGB")
    out = out.rotate(rng.uniform(-1.6, 1.6), resample=Image.BICUBIC, expand=False, fillcolor=(245, 245, 245))
    out = _speckle(out, rng, amount=10)
    out = out.filter(ImageFilter.GaussianBlur(rng.uniform(0.4, 0.9)))
    out = ImageEnhance.Contrast(out).enhance(rng.uniform(1.1, 1.35))
    out = ImageEnhance.Brightness(out).enhance(rng.uniform(0.95, 1.05))
    # vertical scanner streak
    d = ImageDraw.Draw(out)
    x = rng.randint(int(out.width * 0.1), int(out.width * 0.9))
    d.line([(x, 0), (x, out.height)], fill=(222, 222, 222), width=rng.randint(1, 2))
    return out


def _solve8(a: list[list[float]], b: list[float]) -> list[float]:
    """Gaussian elimination for the 8x8 perspective system (avoids a numpy dependency)."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[piv] = m[piv], m[col]
        for r in range(n):
            if r != col:
                f = m[r][col] / m[col][col]
                for c in range(col, n + 1):
                    m[r][c] -= f * m[col][c]
    return [m[i][n] / m[i][i] for i in range(n)]


def perspective(img: Image.Image, rng: random.Random) -> Image.Image:
    w, h = img.size
    j = lambda s: rng.uniform(0, s)
    dst = [(j(w * 0.06), j(h * 0.04)), (w - j(w * 0.06), j(h * 0.04)),
           (w - j(w * 0.03), h - j(h * 0.03)), (j(w * 0.03), h - j(h * 0.03))]
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    a, b = [], []
    for (x, y), (u, v) in zip(dst, src):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); b.append(u)
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y]); b.append(v)
    coeffs = _solve8(a, b)
    return img.transform((w, h), Image.PERSPECTIVE, coeffs, Image.BICUBIC, fillcolor=(70, 60, 50))


def photo(img: Image.Image, rng: random.Random) -> Image.Image:
    """Tilted phone shot on a desk: perspective, warm light, shadow gradient, blur, noise."""
    out = img.rotate(rng.uniform(-4, 4), resample=Image.BICUBIC, expand=True, fillcolor=(70, 60, 50))
    out = perspective(out, rng)
    # warm indoor light
    r, g, b = out.split()
    out = Image.merge("RGB", (r.point(lambda v: min(255, v * 1.03)), g, b.point(lambda v: v * rng.uniform(0.85, 0.93))))
    # shadow from the phone/hand across one side
    shadow = Image.linear_gradient("L").resize(out.size)
    if rng.random() < 0.5:
        shadow = shadow.rotate(90, expand=False)
    strength = rng.uniform(0.25, 0.45)
    shadow = shadow.point(lambda v: int(255 - v * strength)).filter(ImageFilter.GaussianBlur(25))
    out = ImageChops.multiply(out, Image.merge("RGB", (shadow, shadow, shadow)))
    out = out.filter(ImageFilter.GaussianBlur(rng.uniform(0.6, 1.3)))
    noise = Image.effect_noise(out.size, 10).convert("L").filter(ImageFilter.GaussianBlur(0.8))
    noise = noise.point(lambda v: 225 + v // 9)  # faint sensor grain, no banding
    out = ImageChops.multiply(out, Image.merge("RGB", (noise, noise, noise)))
    return out.resize((int(out.width * 0.8), int(out.height * 0.8)), Image.LANCZOS)
