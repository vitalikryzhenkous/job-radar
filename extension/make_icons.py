"""Пиксельная иконка «радар» 16×16 -> icons/icon{16,32,48,128}.png, масштаб без сглаживания (8-bit).

Рисунок считается формулой (кольца, перекрестье, луч со шлейфом, точка-вакансия), без PIL: zlib + struct.
Запуск: python3 extension/make_icons.py
"""
import math
import struct
import zlib
from pathlib import Path

N, C = 16, 7.5
BG, EDGE, GRID, TRAIL, BEAM, BLIP = (12, 36, 12), (139, 172, 15), (36, 84, 36), (48, 110, 40), (200, 236, 60), (255, 90, 60)
BEAM_DEG = 45                     # луч смотрит вверх-вправо, шлейф — против часовой на 50°


def pixel(x: int, y: int) -> tuple:
    dx, dy = x - C, C - y
    r = math.hypot(dx, dy)
    if r > 7.9:
        return (0, 0, 0, 0)
    if r > 6.9:
        return (*EDGE, 255)
    if (x, y) in {(9, 3), (10, 3), (9, 4), (10, 4)}:
        return (*BLIP, 255)
    ux, uy = math.cos(math.radians(BEAM_DEG)), math.sin(math.radians(BEAM_DEG))
    if dx * ux + dy * uy > -0.3 and abs(dx * uy - dy * ux) < 0.75:          # луч: близко к прямой из центра
        return (*BEAM, 255)
    off = (math.degrees(math.atan2(dy, dx)) - BEAM_DEG) % 360
    if 0 < off < 55:
        return (*TRAIL, 255)
    if abs(r - 4.0) < 0.55 or abs(dx) < 0.6 or abs(dy) < 0.6:
        return (*GRID, 255)
    return (*BG, 255)


def png(rows: list[list[tuple]], path: Path) -> None:
    h, w = len(rows), len(rows[0])
    raw = b"".join(b"\0" + b"".join(bytes(px) for px in r) for r in rows)
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main() -> None:
    art = [[pixel(x, y) for x in range(N)] for y in range(N)]
    out = Path(__file__).with_name("icons")
    out.mkdir(exist_ok=True)
    for size in (16, 32, 48, 128):
        k = size // N
        png([[px for px in row for _ in range(k)] for row in art for _ in range(k)], out / f"icon{size}.png")


if __name__ == "__main__":
    main()
