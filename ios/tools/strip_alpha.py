#!/usr/bin/env python3
"""Rewrite an 8-bit RGBA PNG as 8-bit RGB. Standard library only.

Why this exists: `sips` rasterises design/icon.svg with an alpha channel,
and App Store Connect rejects a 1024x1024 app icon that has one, even when
every pixel is opaque ("Invalid Large App Icon"). Xcode's asset compiler
copies the PNG through as-is, so the alpha has to go before it lands in the
catalog. No Pillow on this Mac, so: parse the chunks, inflate, unfilter,
drop the fourth byte, refilter (None), deflate, write.

Usage:  strip_alpha.py IN.png OUT.png
Exit 2 if any pixel is not fully opaque - that would mean the SVG changed
shape and the icon needs a look before it ships, not a silent flatten.
"""
import struct
import sys
import zlib

SIG = b"\x89PNG\r\n\x1a\n"


def chunks(data):
    pos = 8
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        ctype = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        yield ctype, body
        pos += 12 + length


def chunk(ctype, body):
    return (struct.pack(">I", len(body)) + ctype + body
            + struct.pack(">I", zlib.crc32(ctype + body) & 0xFFFFFFFF))


def paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def unfilter(raw, width, height, bpp):
    stride = width * bpp
    out = bytearray()
    prev = bytearray(stride)
    pos = 0
    for _ in range(height):
        ftype = raw[pos]
        pos += 1
        line = bytearray(raw[pos:pos + stride])
        pos += stride
        if ftype == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif ftype == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                upleft = prev[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + paeth(left, prev[i], upleft)) & 0xFF
        elif ftype != 0:
            raise SystemExit("unknown PNG filter type %d" % ftype)
        out += line
        prev = line
    return bytes(out)


def main(src, dst):
    with open(src, "rb") as fh:
        data = fh.read()
    if data[:8] != SIG:
        raise SystemExit("%s is not a PNG" % src)
    idat = b""
    ihdr = None
    for ctype, body in chunks(data):
        if ctype == b"IHDR":
            ihdr = body
        elif ctype == b"IDAT":
            idat += body
    width, height, depth, ctype_, comp, filt, interlace = struct.unpack(">IIBBBBB", ihdr)
    if (depth, ctype_, interlace) != (8, 6, 0):
        raise SystemExit("expected 8-bit non-interlaced RGBA, got depth=%d type=%d interlace=%d"
                         % (depth, ctype_, interlace))
    pixels = unfilter(zlib.decompress(idat), width, height, 4)
    rgb = bytearray()
    translucent = 0
    for y in range(height):
        rgb.append(0)                                   # filter: None
        row = pixels[y * width * 4:(y + 1) * width * 4]
        for x in range(width):
            r, g, b, a = row[x * 4:x * 4 + 4]
            if a != 255:
                translucent += 1
            rgb += bytes((r, g, b))
    if translucent:
        sys.stderr.write("%d pixels are not opaque - refusing to flatten silently\n" % translucent)
        sys.exit(2)
    new_ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    body = SIG + chunk(b"IHDR", new_ihdr) + chunk(b"IDAT", zlib.compress(bytes(rgb), 9)) + chunk(b"IEND", b"")
    with open(dst, "wb") as fh:
        fh.write(body)
    print("%s: %dx%d RGB, %d bytes, all %d pixels opaque" % (dst, width, height, len(body), width * height))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
