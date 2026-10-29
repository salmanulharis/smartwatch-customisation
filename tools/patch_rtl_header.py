#!/usr/bin/env python3
"""Patch the T_IMG_CTRL_HEADER_FORMAT in a Realtek OTA firmware binary.

The GCC SDK's prepend_header tool (plus Hex2Bin) produces a binary whose
first 12 bytes are T_IMG_CTRL_HEADER_FORMAT:

    uint8_t  ic_type        (byte 0)
    uint8_t  secure_version (byte 1)
    uint16_t ctrl_flag      (bytes 2-3, LE)
    uint16_t image_id       (bytes 4-5, LE)
    uint16_t crc16          (bytes 6-7, LE)
    uint32_t payload_len    (bytes 8-11, LE)

The generic Bee2 SDK sets ic_type=0x05 and ctrl_flag=0x0101.
The TechLife S100 (RTL8762C) expects ic_type=0x09 and ctrl_flag=0x0901.

This script patches those two fields. payload_len is left untouched
because prepend_header already sets it correctly.

Usage:
    python patch_rtl_header.py <input_MP.bin> [output.bin]
"""
import struct
import sys

MP_MAGIC = bytes([0x01, 0x00, 0x02])
MP_SIZE = 512

IC_TYPE_TARGET = 0x09
CTRL_FLAG_TARGET = 0x0901

def main():
    if len(sys.argv) < 2:
        print("Usage: %s <input_MP.bin> [output.bin]" % sys.argv[0])
        sys.exit(1)

    in_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else None

    data = bytearray(open(in_path, "rb").read())

    hdr_off = 0
    if data[:3] == MP_MAGIC:
        hdr_off = MP_SIZE
        print("MP header detected at offset 0")

    ic_type = data[hdr_off]
    secure_ver = data[hdr_off + 1]
    ctrl_flag = struct.unpack_from("<H", data, hdr_off + 2)[0]
    image_id = struct.unpack_from("<H", data, hdr_off + 4)[0]
    crc16 = struct.unpack_from("<H", data, hdr_off + 6)[0]
    payload_len = struct.unpack_from("<I", data, hdr_off + 8)[0]

    print("Original T_IMG_CTRL_HEADER_FORMAT:")
    print("  ic_type=%d (0x%02x)  secure_ver=%d" % (ic_type, ic_type, secure_ver))
    print("  ctrl_flag=0x%04x  image_id=0x%04x  crc16=0x%04x" % (ctrl_flag, image_id, crc16))
    print("  payload_len=%d (0x%08x)" % (payload_len, payload_len))

    changes = []
    if ic_type != IC_TYPE_TARGET:
        data[hdr_off] = IC_TYPE_TARGET
        changes.append("ic_type: 0x%02x -> 0x%02x" % (ic_type, IC_TYPE_TARGET))
    if ctrl_flag != CTRL_FLAG_TARGET:
        struct.pack_into("<H", data, hdr_off + 2, CTRL_FLAG_TARGET)
        changes.append("ctrl_flag: 0x%04x -> 0x%04x" % (ctrl_flag, CTRL_FLAG_TARGET))

    if not changes:
        print("No changes needed.")
        return

    for c in changes:
        print("Patched: %s" % c)
    print("payload_len left unchanged: %d" % payload_len)

    dest = out_path or in_path
    open(dest, "wb").write(data)
    print("Written: %s (%d bytes)" % (dest, len(data)))

if __name__ == "__main__":
    main()
