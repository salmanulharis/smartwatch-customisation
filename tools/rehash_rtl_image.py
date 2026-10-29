#!/usr/bin/env python3
"""Recompute the SHA-256 integrity field of a Realtek RTL8762x app image.

Used after binary-patching a stock image (e.g. the TechLife S100 firmware).
Coverage matches the Realtek SDK (slient_dfu_check_sha256): header bytes
12..371, 404..751 and 1008..(1024 + payload_len); the digest is stored at 372.
Only valid for images whose ctrl-header crc16 is 0 (SHA-256 mode).

Usage:
    python rehash_rtl_image.py <in.bin> <out.bin> [--version REV]
        --version REV  set git_ver revision field (header +96) before hashing
"""
import argparse
import hashlib
import struct

MP_MAGIC = bytes([0x01, 0x00, 0x02])
MP_SIZE = 512


def image_digest(img) -> bytes:
    payload_len = struct.unpack_from("<I", img, 8)[0]
    h = hashlib.sha256()
    for part in (img[12:372], img[404:752], img[1008:1024 + payload_len]):
        h.update(part)
    return h.digest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("inp")
    ap.add_argument("out")
    ap.add_argument("--version", type=int, help="new git_ver revision (0..32767)")
    args = ap.parse_args()

    data = bytearray(open(args.inp, "rb").read())
    off = MP_SIZE if data[:3] == MP_MAGIC else 0
    img = memoryview(data)[off:]

    crc16 = struct.unpack_from("<H", img, 6)[0]
    if crc16 != 0:
        raise SystemExit(f"crc16=0x{crc16:04x}: image uses CRC16 mode, not SHA-256")
    payload_len = struct.unpack_from("<I", img, 8)[0]
    if len(img) < 1024 + payload_len:
        raise SystemExit("file shorter than header payload_len")

    old_ok = bytes(img[372:404]) == image_digest(img)
    print(f"stored hash valid before patching: {old_ok}")

    if args.version is not None:
        ver = struct.unpack_from("<I", img, 96)[0]
        new = (ver & ~(0x7FFF << 12)) | ((args.version & 0x7FFF) << 12)
        struct.pack_into("<I", img, 96, new)
        print(f"git_ver 0x{ver:08x} -> 0x{new:08x} (revision {args.version})")

    img[372:404] = image_digest(img)
    open(args.out, "wb").write(data)
    print(f"new SHA-256 {bytes(img[372:404]).hex()}")
    print(f"written {args.out} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
