from __future__ import annotations

import base64
from dataclasses import dataclass


class BocError(ValueError):
    pass


@dataclass(frozen=True)
class BocShape:
    bit_length: int
    refs_count: int
    opcode: int | None
    byte_length: int


def decode_boc_base64(value: str) -> bytes:
    value = value.strip()
    padded = value + "=" * ((4 - len(value) % 4) % 4)
    try:
        return base64.b64decode(padded, validate=True)
    except Exception:
        try:
            return base64.urlsafe_b64decode(padded)
        except Exception as exc:
            raise BocError("Invalid base64 BoC") from exc


def _read_uint(data: bytes, pos: int, size: int) -> tuple[int, int]:
    if size <= 0 or pos + size > len(data):
        raise BocError("Truncated BoC")
    return int.from_bytes(data[pos : pos + size], "big"), pos + size


def inspect_boc(value: str) -> BocShape:
    data = decode_boc_base64(value)
    if len(data) < 8:
        raise BocError("BoC is too short")
    magic = data[:4]
    pos = 4
    if magic == bytes.fromhex("b5ee9c72"):
        flags = data[pos]
        pos += 1
        has_idx = bool(flags & 0x80)
        size_bytes = flags & 0x07
    elif magic in {bytes.fromhex("68ff65f3"), bytes.fromhex("acc3a728")}:
        has_idx = True
        size_bytes = data[pos]
        pos += 1
    else:
        raise BocError("Unsupported BoC magic")
    if not 1 <= size_bytes <= 4:
        raise BocError("Invalid BoC size field")
    offset_bytes = data[pos]
    pos += 1
    cells_num, pos = _read_uint(data, pos, size_bytes)
    roots_num, pos = _read_uint(data, pos, size_bytes)
    _, pos = _read_uint(data, pos, size_bytes)  # absent cells
    _, pos = _read_uint(data, pos, offset_bytes)
    roots: list[int] = []
    for _ in range(roots_num):
        root, pos = _read_uint(data, pos, size_bytes)
        roots.append(root)
    if not roots or cells_num < 1 or roots[0] >= cells_num:
        raise BocError("Invalid BoC roots")
    if has_idx:
        pos += cells_num * offset_bytes
        if pos > len(data):
            raise BocError("Truncated BoC index")

    shapes: list[BocShape] = []
    for _ in range(cells_num):
        if pos + 2 > len(data):
            raise BocError("Truncated BoC cell")
        d1, d2 = data[pos], data[pos + 1]
        pos += 2
        refs_count = d1 & 0x07
        byte_length = (d2 + 1) // 2
        if pos + byte_length + refs_count * size_bytes > len(data):
            raise BocError("Truncated BoC cell data")
        cell_data = data[pos : pos + byte_length]
        pos += byte_length + refs_count * size_bytes
        if d2 % 2 == 0:
            bit_length = byte_length * 8
        elif not cell_data:
            bit_length = 0
        else:
            last = cell_data[-1]
            if last == 0:
                raise BocError("Invalid top-up bit")
            trailing_zeros = (last & -last).bit_length() - 1
            bit_length = byte_length * 8 - trailing_zeros - 1
        opcode = int.from_bytes(cell_data[:4], "big") if bit_length >= 32 else None
        shapes.append(
            BocShape(
                bit_length=bit_length,
                refs_count=refs_count,
                opcode=opcode,
                byte_length=byte_length,
            )
        )
    return shapes[roots[0]]
