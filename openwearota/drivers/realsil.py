"""Realsil RTL876x DFU driver.

Protocol reverse-engineered from Realsil's own Android SDK:
  DfuService.java, BinInputStream.java, RealsilDfu.java
  (package com.realsil.android.blehub.dfu, Apache-2.0 licence)

Two-phase process
-----------------
**Phase 1 — App-mode handover (FULL_FUNCTION / normal firmware):**
Connect to the device running normal firmware, write the one-byte enter-OTA
command (0x01) to the OTA_RESET characteristic, then disconnect.  The device
reboots into DFU mode and starts advertising under a *new* MAC address (or the
same address, depending on chip variant).  OpenWearOTA re-scans and reconnects
to the DFU-mode device.

**Phase 2 — DFU transfer:**
Connect to the DFU-mode device (DFU_SERVICE_UUID), exchange control-point
opcodes on CONTROL_POINT (write-with-response + notify), stream image bytes
on DATA (write-no-response), then validate and activate.

This driver supports OTA_MODE_LIMIT_FUNCTION (device is already in DFU mode)
directly, and makes a best-effort attempt at the full handover for
OTA_MODE_FULL_FUNCTION.  The handover scan step is platform-limited in bleak
— if it fails, pass ``limit_function=True`` to skip directly to phase 2.

See DOCUMENTATION.md ?7 for the full protocol reference.
"""
from __future__ import annotations

import asyncio
import struct
from pathlib import Path

from ..aes import AES256ECB

# ?? GATT UUIDs (DFU / OTA mode) ?????????????????????????????????????????????

DFU_SERVICE_UUID     = "00006287-3c17-d293-8e48-14fe2e4da212"
DFU_DATA_UUID        = "00006387-3c17-d293-8e48-14fe2e4da212"
DFU_CONTROL_PT_UUID  = "00006487-3c17-d293-8e48-14fe2e4da212"

# Normal-firmware (app-mode) OTA-handover service/characteristic.
# The SDK also mentions an older variant (0000ffd0 / 0000ffd1) but the
# "new spec" service below is what DfuService.java dispatches to first.
OTA_SERVICE_UUID_NEW = "0000d0ff-3c17-d293-8e48-14fe2e4da212"
OTA_SERVICE_UUID_OLD = "0000ffd0-0000-1000-8000-00805f9b34fb"
OTA_RESET_CHAR_UUID  = "0000ffd1-0000-1000-8000-00805f9b34fb"

# ?? Control-point opcodes (written to DFU_CONTROL_PT_UUID) ??????????????????

OP_START_DFU                    = 0x01  # begin transfer  (17-byte payload, AES-encrypted metadata)
OP_RECEIVE_FW_IMAGE             = 0x02  # arm data channel  (7-byte payload: sig + offset)
OP_VALIDATE_FW_IMAGE            = 0x03  # verify after transfer  (3-byte: opcode + sig LE)
OP_ACTIVE_IMAGE_RESET           = 0x04  # activate + reboot  (1 byte)
OP_RESET                        = 0x05  # abort / reset  (1 byte)
OP_REPORT_RECEIVED_IMAGE_INFO   = 0x06  # query current image info  (3-byte: opcode + sig LE)
OP_CONNECTION_PARAMETER_UPDATE  = 0x07  # request faster conn params  (9-byte payload)
OP_BUFFER_CHECK_ENABLE          = 0x09  # enable buffer-check mode  (1-byte payload)
OP_REPORT_BUFFER_CRC            = 0x0A  # host→device buffer CRC report  (5-byte payload)

# ?? Notification response byte (byte 0 of every notification) ???????????????
#
# DfuService always checks byte[0] == 0x10 before processing; byte[1] is
# the opcode being acked; byte[2] is the status code below.

NOTIFY_RESPONSE_CODE = 0x10  # responseType that marks a valid control-point reply

# ?? DFU status codes (byte[2] of notifications) ?????????????????????????????

DFU_STATUS_SUCCESS              = 0x01
DFU_STATUS_INVALID_PARAM        = 0x02
DFU_STATUS_OPERATION_FAILED     = 0x03
DFU_STATUS_DATA_SIZE_EXCEEDS    = 0x04
DFU_STATUS_CRC_ERROR            = 0x05
DFU_STATUS_BUFFER_CHECK_ERROR   = 0x06
DFU_STATUS_NOT_SUPPORTED        = 0xFE

DFU_STATUS_NAMES = {
    DFU_STATUS_SUCCESS:          "SUCCESS",
    DFU_STATUS_INVALID_PARAM:    "INVALID_PARAM",
    DFU_STATUS_OPERATION_FAILED: "OPERATION_FAILED",
    DFU_STATUS_DATA_SIZE_EXCEEDS:"DATA_SIZE_EXCEEDS_LIMIT",
    DFU_STATUS_CRC_ERROR:        "CRC_ERROR",
    DFU_STATUS_BUFFER_CHECK_ERROR:"BUFFER_CHECK_LENGTH_ERROR",
    DFU_STATUS_NOT_SUPPORTED:    "NOT_SUPPORTED",
}

# ?? Connection parameter update constants (from DfuService.java) ?????????????

CONN_INTERVAL_MIN      = 0x0006
CONN_INTERVAL_MAX      = 0x0011
SLAVE_LATENCY          = 0x0000
SUPERVISION_TIMEOUT    = 500

# ?? Bin file header layout ???????????????????????????????????????????????????
#
# Parsed by BinInputStream.parseBinFileHeader() — 12 bytes, all LE:
#   offset      uint16   flash write offset of the image body (relative to app start)
#   signature   uint16   product/image type identifier (must match target's expected sig)
#   version     uint16   firmware version
#   checksum    uint16   simple checksum of the image body
#   length      uint16   image body length in *4-byte units* (so byte_len = length * 4)
#   ota_flag    uint8    OTA flags
#   reserved_8  uint8    reserved
#
# Total header = 12 bytes; image body follows immediately.

BIN_HEADER_SIZE = 12

# ?? MAX_PACKET_SIZE ??????????????????????????????????????????????????????????
#
# DfuService.java hardcodes 20 bytes (the ATT_MTU=23 default minus the 3-byte
# ATT write header).  On modern phones the MTU can be negotiated higher;
# DfuService doesn't do that negotiation.  We follow the same conservative
# default but accept whatever MTU bleak negotiates.

MAX_PACKET_SIZE = 20

# Big-image skip: DfuService.java skips body bytes 104,000–143,360 for images > 100 KB.
BIG_IMAGE_THRESHOLD = 100 * 1024          # 102,400 bytes (file size including header)
BIG_IMAGE_SKIP_FROM = 104000              # body byte offset where skip begins
BIG_IMAGE_SKIP_TO   = 140 * 1024          # 143,360 = body byte offset where skip ends

# MP header: some firmware files have a 512-byte "MP header" prepended before
# the actual BinHeader.  Detected by first three bytes == 01 00 02.
MP_HEADER_SIZE = 512
MP_HEADER_MAGIC = bytes([0x01, 0x00, 0x02])

# Default AES-256 key from Realtek SDK, with bytes 5–10 replaced by ASCII "UTE_RK"
# (used by realme Fit / UTE-based companion apps).
REALSIL_DEFAULT_AES_KEY = bytes([
    0x4E, 0x46, 0xF8, 0xC5, 0x09, 0x55, 0x54, 0x45,
    0x5F, 0x52, 0x4B, 0x0C, 0xD1, 0xF6, 0x10, 0xFB,
    0x1F, 0x67, 0x63, 0xDF, 0x80, 0x7A, 0x7E, 0x70,
    0x96, 0x0D, 0x4C, 0xD3, 0x11, 0x8E, 0x60, 0x1A,
])

REALSIL_STOCK_AES_KEY = bytes([
    0x4E, 0x46, 0xF8, 0xC5, 0x09, 0x2B, 0x29, 0xE2,
    0x9A, 0x97, 0x1A, 0x0C, 0xD1, 0xF6, 0x10, 0xFB,
    0x1F, 0x67, 0x63, 0xDF, 0x80, 0x7A, 0x7E, 0x70,
    0x96, 0x0D, 0x4C, 0xD3, 0x11, 0x8E, 0x60, 0x1A,
])


# ?? Bin header parser ????????????????????????????????????????????????????????

class BinHeader:
    """Parsed representation of the 12-byte Realsil .bin file header."""

    __slots__ = ("offset", "signature", "version", "checksum",
                 "length", "ota_flag", "reserved_8", "body_size")

    def __init__(self, raw: bytes) -> None:
        if len(raw) < BIN_HEADER_SIZE:
            raise ValueError(f"BIN header too short: {len(raw)} < {BIN_HEADER_SIZE}")
        # Same 12 bytes as T_IMG_CTRL_HEADER_FORMAT: "signature" is ctrl_flag
        # and "version" is the image_id the DFU commands must carry.
        (self.offset, self.signature, self.version,
         self.checksum, self.length) = struct.unpack_from("<HHHHH", raw, 0)
        self.ota_flag   = raw[10]
        self.reserved_8 = raw[11]
        # length field is in 4-byte units (BinInputStream: "toUnsigned(length)*4")
        self.body_size  = (self.length & 0xFFFF) * 4

    def __repr__(self) -> str:
        return (
            f"BinHeader(offset=0x{self.offset:04x}, sig=0x{self.signature:04x}, "
            f"ver=0x{self.version:04x}, chk=0x{self.checksum:04x}, "
            f"body={self.body_size}B, ota_flag=0x{self.ota_flag:02x})"
        )


# ?? XOR CRC for buffer-check protocol ????????????????????????????????????????

def xor_crc16(data: bytes) -> int:
    """XOR-based 16-bit CRC used by Realtek buffer-check protocol.

    XOR every little-endian 16-bit word, then byte-swap the result.
    Translated from BaseDfuTask.java lines 445-451.
    """
    crc = 0
    for i in range(0, len(data) - 1, 2):
        crc ^= data[i] | (data[i + 1] << 8)
    if len(data) % 2:
        crc ^= data[-1]
    return ((crc & 0xFF) << 8) | ((crc >> 8) & 0xFF)


# ?? Command builders ?????????????????????????????????????????????????????????

def build_conn_param_update() -> bytes:
    """9-byte connection-parameter-update command (opcode 0x07)."""
    return struct.pack(
        "<BHHHHH",
        OP_CONNECTION_PARAMETER_UPDATE,
        CONN_INTERVAL_MIN,
        CONN_INTERVAL_MAX,
        SLAVE_LATENCY,
        SUPERVISION_TIMEOUT,
        0,  # padding to reach 9 bytes (matches Java array size)
    )[:9]


def build_report_image_info(signature: int) -> bytes:
    """3-byte query-image-info command (opcode 0x06)."""
    return struct.pack("<BH", OP_REPORT_RECEIVED_IMAGE_INFO, signature & 0xFFFF)


def build_start_dfu(
    hdr: BinHeader,
    update_offset: int = 0,
    *,
    aes_key: bytes | None = None,
) -> bytes:
    """17-byte START_DFU command (opcode 0x01).

    The 16 metadata bytes (bytes 1–16) are AES-256-ECB encrypted when an
    ``aes_key`` is provided (mandatory for protocol type 0x12 / UTE devices).
    """
    payload = struct.pack(
        "<HHHHHBB",
        hdr.offset     & 0xFFFF,
        hdr.signature  & 0xFFFF,
        hdr.version    & 0xFFFF,
        hdr.checksum   & 0xFFFF,
        hdr.length     & 0xFFFF,
        hdr.ota_flag,
        hdr.reserved_8,
    )  # 12 bytes
    payload += b"\x00" * 4  # pad to 16 bytes
    if aes_key is not None:
        cipher = AES256ECB(aes_key)
        payload = cipher.encrypt_block(payload[:16])
    return bytes([OP_START_DFU]) + payload[:16]


def build_receive_fw_image(signature: int, update_offset: int) -> bytes:
    """7-byte RECEIVE_FW_IMAGE command (opcode 0x02).

    For icType > 3 (RTL8762C), offset 0 means "send from the beginning,
    including the 12-byte BinHeader in the data stream".  The SDK passes the
    raw mImageUpdateOffset (0 for fresh, device-reported value for resume).
    """
    return struct.pack("<BHI", OP_RECEIVE_FW_IMAGE, signature & 0xFFFF, update_offset)


def build_validate(signature: int) -> bytes:
    """3-byte VALIDATE_FW_IMAGE command (opcode 0x03)."""
    return struct.pack("<BH", OP_VALIDATE_FW_IMAGE, signature & 0xFFFF)


# ?? DFU transfer ?????????????????????????????????????????????????????????????

async def identify_realsil_chip(client) -> str | None:
    """
    Attempts to identify the specific Realtek chipset.
    Currently returns None as no universal ID characteristic is identified.
    """
    return None


async def run_realsil_upgrade(
    client,
    firmware_path: Path,
    *,
    verbose: bool = False,
    limit_function: bool = False,
    aes_key: bytes | None = REALSIL_DEFAULT_AES_KEY,
) -> bool:
    """OTA-flash a Realsil RTL876x device.

    Parameters
    ----------
    client:
        A connected ``bleak.BleakClient``.
    firmware_path:
        Path to the Realsil ``.bin`` firmware file (with 12-byte header).
    verbose:
        Print raw notification bytes for debugging.
    limit_function:
        ``True`` — device is already in DFU mode (skip phase-1 handover).
        ``False`` — attempt phase-1 handover first.
    aes_key:
        AES-256 key for encrypting the START_DFU metadata and firmware body.
        Defaults to ``REALSIL_DEFAULT_AES_KEY`` (UTE variant).  Pass ``None``
        to disable encryption (only works on devices that accept plaintext).
    """
    raw_firmware = firmware_path.read_bytes()

    # Detect and skip MP header (512-byte prefix starting with 01 00 02).
    img_offset = 0
    if (len(raw_firmware) >= MP_HEADER_SIZE + BIN_HEADER_SIZE
            and raw_firmware[:3] == MP_HEADER_MAGIC):
        img_offset = MP_HEADER_SIZE
        if verbose:
            print(f"[*] MP header detected — BinHeader at offset {img_offset}")

    if len(raw_firmware) < img_offset + BIN_HEADER_SIZE:
        print(f"[!] File too small to contain Realsil header ({len(raw_firmware)} bytes).")
        return False

    hdr = BinHeader(raw_firmware[img_offset:])
    print(f"[*] {hdr}")

    body_start = img_offset + BIN_HEADER_SIZE
    body = raw_firmware[body_start:]
    if len(body) == 0:
        print("[!] Firmware file has no body after header.")
        return False

    # ?? Phase 1: handover (normal firmware ? DFU mode) ????????????????????
    if not limit_function:
        print("[*] Phase 1: sending enter-OTA command to normal firmware…")
        entered = await _enter_ota_mode(client, verbose=verbose)
        if not entered:
            print(
                "[!] Could not trigger OTA handover.  If the device is already in "
                "DFU mode, pass limit_function=True (CLI: --limit-function)."
            )
            return False
        print(
            "[!] Device rebooting into DFU mode.  You must re-scan, reconnect "
            "to the DFU-mode device (may have a different MAC address), and "
            "re-run with --limit-function."
        )
        # After sending enter-OTA the device disconnects immediately; we cannot
        # continue in this same bleak session.  Return False so the caller knows
        # to reconnect.
        return False

    # ?? Phase 2: DFU transfer ?????????????????????????????????????????????
    return await _run_dfu_transfer(
        client, hdr, body, verbose=verbose, aes_key=aes_key,
    )


# ?? Phase 1 helper ???????????????????????????????????????????????????????????

async def _enter_ota_mode(client, *, verbose: bool) -> bool:
    """Write the one-byte enter-OTA command to the normal-firmware OTA char."""
    service_uuids = {str(s.uuid).lower() for s in client.services}

    ota_char_uuid: str | None = None
    if OTA_SERVICE_UUID_NEW.lower() in service_uuids:
        ota_char_uuid = OTA_RESET_CHAR_UUID
        if verbose:
            print(f"    Using new OTA service {OTA_SERVICE_UUID_NEW}")
    elif OTA_SERVICE_UUID_OLD.lower() in service_uuids:
        ota_char_uuid = OTA_RESET_CHAR_UUID
        if verbose:
            print(f"    Using legacy OTA service {OTA_SERVICE_UUID_OLD}")

    if ota_char_uuid is None:
        print("[!] Neither OTA handover service found on this device.")
        return False

    try:
        # write-no-response, matches DfuService: WRITE_TYPE_NO_RESPONSE
        await client.write_gatt_char(ota_char_uuid, bytes([0x01]), response=False)
        if verbose:
            print("    Enter-OTA command sent (0x01, write-no-response).")
        await asyncio.sleep(1.0)  # give chip time to reboot into DFU mode
        return True
    except Exception as exc:
        print(f"[!] Failed to write enter-OTA command: {exc}")
        return False


# ?? Phase 2 helper ???????????????????????????????????????????????????????????

async def _run_dfu_transfer(
    client,
    hdr: BinHeader,
    body: bytes,
    *,
    verbose: bool,
    aes_key: bytes | None = None,
) -> bool:
    notif_queue: asyncio.Queue[bytes] = asyncio.Queue()

    def _handler(_sender, data: bytes) -> None:
        notif_queue.put_nowait(bytes(data))

    await client.start_notify(DFU_CONTROL_PT_UUID, _handler)

    ble_mtu = getattr(client, "mtu_size", 23)
    raw_pkt = ble_mtu - 3
    # Without buffer check the device flushes its temp buffer only when it
    # holds exactly (BUF - BUF % 20) bytes and resets on overflow, so the
    # packet size must divide that.  1020 divides it for 1K/2K/4K buffers.
    packet_size = max(d for d in range(20, max(raw_pkt, 20) + 1) if 1020 % d == 0)
    buf_check_max = 0
    buf_check_mtu = 0

    async def send_cp(data: bytes) -> None:
        await client.write_gatt_char(DFU_CONTROL_PT_UUID, data, response=True)

    async def wait_notif(timeout: float = 10.0) -> bytes:
        return await asyncio.wait_for(notif_queue.get(), timeout=timeout)

    def _check_notif(raw: bytes, expect_op: int, what: str) -> bool:
        """Validate a control-point notification.

        Notifications are [responseType=0x10, requestOpCode, statusCode, ...]
        """
        if len(raw) < 3:
            print(f"[!] {what}: notification too short ({raw.hex()})")
            return False
        if raw[0] != NOTIFY_RESPONSE_CODE:
            # The connection-parameter-update opcode (0x07) generates a
            # notification that DfuService explicitly ignores; skip it.
            if raw[1] == OP_CONNECTION_PARAMETER_UPDATE:
                if verbose:
                    print(f"    (ignored conn-param-update notification: {raw.hex()})")
                return True  # caller should loop for the real notification
            if verbose:
                print(f"    unexpected notification type {raw[0]:#04x}: {raw.hex()}")
            return False
        if raw[1] != expect_op:
            print(f"[!] {what}: expected ack for op {expect_op:#04x}, got {raw[1]:#04x}")
            return False
        status = raw[2]
        if status != DFU_STATUS_SUCCESS:
            name = DFU_STATUS_NAMES.get(status, f"status {status:#04x}")
            print(f"[!] {what}: device returned {name} (raw: {raw.hex()})")
            return False
        return True

    async def send_and_ack(data: bytes, expect_op: int, what: str,
                           timeout: float = 10.0) -> bool:
        await send_cp(data)
        while True:
            raw = await wait_notif(timeout)
            if verbose:
                print(f"    notif ({what}): {raw.hex()}")
            # skip conn-param-update notifications transparently
            if len(raw) >= 2 and raw[1] == OP_CONNECTION_PARAMETER_UPDATE:
                continue
            return _check_notif(raw, expect_op, what)

    try:
        # ?? Step 0: buffer-check mode (opcode 0x09) ????????????????????????
        # Reply: 10 09 <enabled> <buffer size LE16> <device MTU LE16>.
        # With buffer check the device verifies and writes each buffer and
        # acks it, which large images need.
        await send_cp(bytes([OP_BUFFER_CHECK_ENABLE]))
        try:
            while True:
                raw = await wait_notif(timeout=5.0)
                if verbose:
                    print(f"    notif (BufferCheckEn): {raw.hex()}")
                if len(raw) >= 2 and raw[1] == OP_BUFFER_CHECK_ENABLE:
                    break
        except asyncio.TimeoutError:
            raw = b""
        if len(raw) >= 7 and raw[2] == 1:
            buf_check_max = struct.unpack_from("<H", raw, 3)[0]
            buf_check_mtu = struct.unpack_from("<H", raw, 5)[0]
            mtu = min(ble_mtu, buf_check_mtu) if buf_check_mtu else ble_mtu
            packet_size = max(16, ((mtu - 3) // 16) * 16)
            print(f"[*] Buffer check on: buffer {buf_check_max} B, "
                  f"packet {packet_size} B (MTU {mtu})")
        else:
            print(f"[*] Packet size: {packet_size} (MTU {ble_mtu}, no buffer check)")

        # ?? Step 1: request faster connection parameters ?????????????????
        print("[*] Requesting faster connection parameters…")
        await send_cp(build_conn_param_update())
        try:
            raw = await asyncio.wait_for(notif_queue.get(), timeout=1.5)
            if verbose:
                print(f"    conn-param notif (ignored): {raw.hex()}")
        except asyncio.TimeoutError:
            pass

        # ?? Step 2: query existing image info (resume support) ???????????
        print("[*] Querying device image info…")
        await send_cp(build_report_image_info(hdr.version))
        while True:
            raw_info_notif = await wait_notif(timeout=10.0)
            if verbose:
                print(f"    notif (ImageInfo): {raw_info_notif.hex()}")
            if len(raw_info_notif) >= 2 and raw_info_notif[1] == OP_CONNECTION_PARAMETER_UPDATE:
                continue
            break
        if not _check_notif(raw_info_notif, OP_REPORT_RECEIVED_IMAGE_INFO, "ReportImageInfo"):
            return False

        # Notification: 10 06 status | version (LE32) | offset (LE32)
        original_version = 0
        device_offset    = 0
        if len(raw_info_notif) >= 11:
            original_version = struct.unpack_from("<I", raw_info_notif, 3)[0]
            device_offset    = struct.unpack_from("<I", raw_info_notif, 7)[0]
        print(
            f"[*] Device image version: 0x{original_version:08x}  "
            f"reported offset: {device_offset}"
        )
        # Bee2 resets cur_offset to 0 on this command (no re-OTA support),
        # so always start a fresh transfer.
        update_offset = 0

        # ?? Step 3: START_DFU ????????????????????????????????????????????
        print("[*] Sending START_DFU (full image)…")
        ok = await send_and_ack(
            build_start_dfu(hdr, update_offset, aes_key=aes_key),
            OP_START_DFU,
            "StartDfu",
        )
        if not ok:
            return False

        # ?? Step 4: RECEIVE_FW_IMAGE — arm data channel ??????????????????
        # SDK (j() in e.java) always converts offset 0→12 for fresh transfer.
        # RECEIVE_FW_IMAGE does NOT produce a notification — write-with-
        # response ack at the BLE level is the only confirmation.
        effective_offset = update_offset if update_offset > 0 else BIN_HEADER_SIZE
        print(f"[*] Sending RECEIVE_FW_IMAGE (offset={effective_offset})…")
        await send_cp(build_receive_fw_image(hdr.version, effective_offset))

        # ?? Step 5: stream body with host-initiated buffer check ?????????
        # Body only, no header prepend (SDK Case B: offset==12).
        # First buffer is maxBuf - 12 because the header already counts.
        total = len(body)
        idx = 0
        buf_active = buf_check_max > 0
        is_first_buf = (effective_offset == BIN_HEADER_SIZE)
        cipher = AES256ECB(aes_key) if aes_key is not None else None

        print(f"[*] Streaming {total} bytes "
              f"({packet_size}B/pkt, bufCheck={buf_check_max}"
              f", AES={'on' if cipher else 'off'})…")
        while idx < total:
            # SDK Case B first buffer: maxBuf - 12 (header already counted).
            if is_first_buf and buf_active:
                buf_size = min(buf_check_max - BIN_HEADER_SIZE, total - idx)
                is_first_buf = False
            elif buf_active:
                buf_size = min(buf_check_max, total - idx)
            else:
                buf_size = total - idx

            buf_start = idx
            buf_end = idx + buf_size

            # Packetize (and encrypt) this buffer.  Device decrypts whole
            # 16-byte blocks and keeps any tail as-is, so tails stay plain.
            chunks = []
            pos = buf_start
            while pos < buf_end:
                pkt_len = min(packet_size, buf_end - pos)
                plain = body[pos:pos + pkt_len]
                if cipher:
                    full = pkt_len - (pkt_len % 16)
                    chunk = b"".join(
                        cipher.encrypt_block(plain[blk:blk + 16])
                        for blk in range(0, full, 16)
                    ) + plain[full:]
                else:
                    chunk = plain
                chunks.append(chunk)
                pos += pkt_len

            for attempt in range(3):
                for chunk in chunks:
                    await client.write_gatt_char(
                        DFU_DATA_UUID, chunk, response=False)
                if not buf_active:
                    break

                # Host-initiated buffer check (opcode 0x0A); CRC is over the
                # bytes as sent (encrypted).
                crc = xor_crc16(b"".join(chunks))
                if verbose:
                    print(f"\n    buf-check @{buf_end}: len={buf_size} "
                          f"crc=0x{crc:04x}")
                await send_cp(struct.pack(
                    "<BHH", OP_REPORT_BUFFER_CRC, buf_size, crc))

                status = None
                try:
                    while True:
                        raw = await wait_notif(timeout=10.0)
                        if verbose:
                            print(f"    notif: {raw.hex()}")
                        if (len(raw) >= 3 and raw[0] == NOTIFY_RESPONSE_CODE
                                and raw[1] == OP_REPORT_BUFFER_CRC):
                            status = raw[2]
                            break
                except asyncio.TimeoutError:
                    print(f"\n[!] No buffer-check reply at offset {buf_end}.")
                    return False

                if status == DFU_STATUS_SUCCESS:
                    break
                if status in (0x05, 0x06, 0x07) and attempt < 2:
                    print(f"\n[*] Buffer CRC error @{buf_end} "
                          f"({DFU_STATUS_NAMES.get(status, hex(status))}), resending…")
                    continue
                name = DFU_STATUS_NAMES.get(status, f"{status:#04x}")
                print(f"\n[!] Buffer check failed @{buf_end}: {name} (raw {raw.hex()})")
                return False

            idx = buf_end

            pct = 100 * idx // total
            print(f"\r[*] Progress: {pct:3d}%  ({idx}/{total})",
                  end="", flush=True)
        print()

        # Drain stray notifications before VALIDATE.
        while not notif_queue.empty():
            stray = notif_queue.get_nowait()
            if verbose:
                print(f"    drained stray notif: {stray.hex()}")

        # ?? Step 6: VALIDATE_FW_IMAGE ????????????????????????????????????
        if not client.is_connected:
            print("[!] Device disconnected after streaming.")
            return False

        print("[*] Validating firmware image…")
        try:
            ok = await send_and_ack(
                build_validate(hdr.version),
                OP_VALIDATE_FW_IMAGE,
                "ValidateFW",
                timeout=30.0,
            )
        except Exception as exc:
            print(f"[!] Connection lost during validate ({exc}).")
            print("[!] No validate result received and image was NOT activated; "
                  "the device will most likely stay on its current firmware.")
            return False
        if not ok:
            await _send_reset(client, verbose)
            return False

        # ?? Step 7: ACTIVE_IMAGE_RESET — activate + reboot ???????????????
        print("[*] Activating image and rebooting…")
        try:
            await send_cp(bytes([OP_ACTIVE_IMAGE_RESET]))
        except Exception:
            pass  # device resets on this command; a lost link is expected

        print("[+] Image validated and activated. The device reboots; the "
              "bootloader decides whether to install it — re-scan to confirm.")
        return True
        return True

    except asyncio.TimeoutError:
        print("[!] Timed out waiting for device notification.")
        await _send_reset(client, verbose)
        return False
    except Exception as exc:
        print(f"[!] DFU error: {exc}")
        await _send_reset(client, verbose)
        return False
    finally:
        try:
            await client.stop_notify(DFU_CONTROL_PT_UUID)
        except Exception:
            pass


async def _send_reset(client, verbose: bool) -> None:
    """Best-effort: send RESET so the device doesn't stay stuck in DFU mode."""
    try:
        await client.write_gatt_char(
            DFU_CONTROL_PT_UUID, bytes([OP_RESET]), response=True
        )
        if verbose:
            print("    Reset command sent.")
    except Exception:
        pass