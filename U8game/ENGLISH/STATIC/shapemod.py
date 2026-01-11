#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Replace shape 523 with frames from NewShape523.bmp.
Assumes the BMP uses the exact same arrangement as the vanilla:
- frames packed left->right; wrap to a new row when width would overflow
- each imported frame keeps the original width/height and XOff/YOff
- palette index 255 = transparency

Requires: Pillow  (pip install pillow)
"""

import os, sys, struct, shutil
from typing import List, Tuple

# ---------- Config ----------
SHAPES_FLX = "U8SHAPES.FLX"
SHEET_PATH = "NewShape523.bmp"
TARGET_SHAPE_INDEX = 523
# ----------------------------

# ---------- Tiny utils ----------
def u16(b, o=0):  return b[o] | (b[o+1] << 8)
def i16(b, o=0):  return struct.unpack_from("<h", b, o)[0]
def put_u16(v):   return struct.pack("<H", v)
def put_u24(v):   return bytes((v & 0xFF, (v>>8)&0xFF, (v>>16)&0xFF))

# ---------- FLX parsing ----------
def load_flx_table(blob: bytearray):
    """0-based offsets; at 84: uint16 Count; at 128: Count*(uint32 off, uint32 size)."""
    if len(blob) < 136:
        raise ValueError("FLX too small.")
    count = u16(blob, 84)
    table_off = 128
    recs = []
    for i in range(count):
        off  = int.from_bytes(blob[table_off + i*8 + 0: table_off + i*8 + 4], "little")
        size = int.from_bytes(blob[table_off + i*8 + 4: table_off + i*8 + 8], "little")
        recs.append({"off": off, "size": size})
    return count, recs

def read_type_chunk(blob: bytearray, rec):
    """Return dict with head, frame headers and full bytes for a type (shape)."""
    off = rec["off"]; size = rec["size"]
    chunk = blob[off: off+size]
    if len(chunk) != size:
        raise ValueError("Type chunk truncated.")
    head04 = chunk[0:4]                 # keep as-is
    num_frames = u16(chunk, 4)
    frames = []
    pos = 6
    for _ in range(num_frames):
        rel = chunk[pos] | (chunk[pos+1]<<8) | (chunk[pos+2]<<16)
        unk = chunk[pos+3]
        sz  = u16(chunk, pos+4)
        frames.append({"rel": rel, "unk": unk, "size": sz})
        pos += 6
    return {"raw_head04": head04, "num_frames": num_frames, "frames": frames, "chunk": chunk}

def read_frame_attrs(blob: bytearray, abs_off: int):
    """Return (comp, xlen, ylen, xoff, yoff)."""
    comp = u16(blob, abs_off + 8)
    xlen = u16(blob, abs_off + 10)
    ylen = u16(blob, abs_off + 12)
    xoff = i16(blob, abs_off + 14)
    yoff = i16(blob, abs_off + 16)
    return comp, xlen, ylen, xoff, yoff

# ---------- U8 RLE encode (compression=1; per u8view.bas) ----------
def encode_frame_u8(index_grid: List[List[int]], xlen: int, ylen: int, xoff: int, yoff: int) -> bytes:
    """
    Build a compressed=1 frame chunk:

      0:2  TypeNum (patched later)
      2:2  FrameNum (patched later)
      4:4  0
      8:2  1 (compression)
     10:2  xlen
     12:2  ylen
     14:2  xoff
     16:2  yoff
     18:   ylen*2 line-offset words
      ..   row RLE data

    Row format (per u8view.bas):
      gap = 1 byte (transparent count)
      dlen = 1 byte
        if dlen&1 == 1: repeated color follows; paints (dlen>>1) pixels
        else: (dlen>>1) literal bytes follow
    """
    if xlen > 255:
        raise ValueError("Width > 255 not encodable with 1-byte row opcodes.")

    lines: List[bytes] = []
    for y in range(ylen):
        row = index_grid[y]
        rle = bytearray()
        xpos = 0
        while xpos < xlen:
            # skip transparent gap
            start = xpos
            while start < xlen and row[start] == 255:
                start += 1

            # write gap (may be zero)
            rle.append((start - xpos) & 0xFF)
            xpos = start
            if xpos >= xlen:
                break

            # non-transparent run [xpos .. end)
            end = xpos
            while end < xlen and row[end] != 255:
                end += 1

            p = xpos
            while p < end:
                chunk = min(127, end - p)  # max we can encode in one op
                # check if repeated color
                c0 = row[p]
                repeated = True
                for xx in range(p+1, p+chunk):
                    if row[xx] != c0:
                        repeated = False
                        break
                if repeated:
                    d = (chunk * 2) | 1
                    rle.append(d & 0xFF)
                    rle.append(c0 & 0xFF)
                else:
                    d = (chunk * 2)
                    rle.append(d & 0xFF)
                    rle.extend((row[p+i] & 0xFF) for i in range(chunk))
                p += chunk
            xpos = end

        lines.append(bytes(rle))

    # Build line-offset table (word per line): remaining_words*2 + bytes_of_prev_lines
    rle_blob = bytearray()
    offsets = []
    sofar = 0
    for i, line in enumerate(lines):
        offsets.append((ylen - i) * 2 + sofar)
        rle_blob.extend(line)
        sofar += len(line)

    header = struct.pack("<HHIHHHHH",
                         0, 0, 0,  # patched later
                         1,        # compression
                         xlen, ylen,
                         xoff, yoff)

    off_table = bytearray()
    for v in offsets:
        off_table += put_u16(v & 0xFFFF)

    return header + off_table + rle_blob

def patch_type_frame(frame_bytes: bytes, type_index: int, frame_index: int) -> bytes:
    b = bytearray(frame_bytes)
    b[0:2] = put_u16(type_index)
    b[2:4] = put_u16(frame_index)
    return bytes(b)

# ---------- Rebuild helpers ----------
def try_inplace_write(blob: bytearray, recs, type_index: int, frame_index: int, new_frame: bytes) -> bool:
    rec = recs[type_index]
    tinfo = read_type_chunk(blob, rec)
    frames = tinfo["frames"]
    abs_off = rec["off"] + frames[frame_index]["rel"]
    orig_sz = frames[frame_index]["size"]
    if len(new_frame) > orig_sz:
        return False
    blob[abs_off: abs_off+len(new_frame)] = new_frame
    if len(new_frame) < orig_sz:
        blob[abs_off+len(new_frame): abs_off+orig_sz] = b"\x00" * (orig_sz - len(new_frame))
    return True

def rebuild_type_and_file(blob: bytearray, recs, type_index: int, frame_replacements: dict) -> bytearray:
    rec = recs[type_index]
    tinfo = read_type_chunk(blob, rec)
    nf = tinfo["num_frames"]
    frames = tinfo["frames"]

    new_head = bytearray()
    new_head += tinfo["raw_head04"]
    new_head += put_u16(nf)

    base_rel = 6 + nf*6
    rel_cursor = base_rel
    new_frame_headers = bytearray()
    new_frames_data = bytearray()

    for i in range(nf):
        unk = frames[i]["unk"]
        abs_off = rec["off"] + frames[i]["rel"]
        orig_size = frames[i]["size"]
        data = frame_replacements.get(i, bytes(blob[abs_off:abs_off+orig_size]))

        new_frame_headers += put_u24(rel_cursor)
        new_frame_headers += bytes((unk,))
        new_frame_headers += put_u16(len(data))

        new_frames_data += data
        rel_cursor += len(data)

    new_chunk = bytes(new_head + new_frame_headers + new_frames_data)

    # Splice into file
    before = blob[:rec["off"]]
    after  = blob[rec["off"] + rec["size"]:]
    new_blob = bytearray(before + new_chunk + after)

    # Fix record table
    count = u16(new_blob, 84)
    table_off = 128
    # update this record size
    new_blob[table_off + type_index*8 + 4: table_off + type_index*8 + 8] = len(new_chunk).to_bytes(4, "little")
    # shift later records by delta
    delta = len(new_chunk) - rec["size"]
    for i in range(type_index+1, count):
        off = int.from_bytes(new_blob[table_off + i*8 + 0: table_off + i*8 + 4], "little")
        if off != 0:
            off += delta
            new_blob[table_off + i*8 + 0: table_off + i*8 + 4] = off.to_bytes(4, "little")

    return new_blob

# ---------- Sheet loading (indexed, keep palette indices) ----------
def load_sheet_indices(path: str) -> Tuple[List[List[int]], int, int]:
    from PIL import Image  # require Pillow
    im = Image.open(path)
    if im.mode != "P":
        im = im.convert("P")
    w, h = im.size
    raw = list(im.getdata())  # indices 0..255
    grid = [raw[y*w:(y+1)*w] for y in range(h)]
    return grid, w, h

# ---------- Main ----------
def main():
    # Locate FLX
    flx_path = SHAPES_FLX if os.path.exists(SHAPES_FLX) else os.path.join("STATIC", "U8SHAPES.FLX")
    if not os.path.exists(flx_path):
        raise FileNotFoundError("U8SHAPES.FLX not found.")

    with open(flx_path, "rb") as f:
        blob = bytearray(f.read())

    count, recs = load_flx_table(blob)
    if not (0 <= TARGET_SHAPE_INDEX < count):
        raise IndexError("TARGET_SHAPE_INDEX out of range.")

    rec = recs[TARGET_SHAPE_INDEX]
    tinfo = read_type_chunk(blob, rec)
    nf = tinfo["num_frames"]
    print(f"Shape {TARGET_SHAPE_INDEX}: {nf} frames")

    # Gather vanilla frame sizes & offsets to replicate exactly
    dims = []
    offs = []
    for i in range(nf):
        abs_off = rec["off"] + tinfo["frames"][i]["rel"]
        comp, xlen, ylen, xoff, yoff = read_frame_attrs(blob, abs_off)
        dims.append((xlen, ylen))
        offs.append((xoff, yoff))

    # Load the replacement sheet (indexed)
    sheet, sw, sh = load_sheet_indices(SHEET_PATH)
    print(f"Loaded sheet: {SHEET_PATH} -> {sw}x{sh} (indexed)")

    # Compute rectangles by replaying vanilla packing (left->right, wrap when needed)
    rects = []
    curx = 0
    cury = 0
    row_h = 0
    for i in range(nf):
        w, h = dims[i]
        if w == 0 or h == 0:
            rects.append((curx, cury, 1, 1))
            continue
        if curx + w > sw:
            curx = 0
            cury += row_h
            row_h = 0
        rects.append((curx, cury, w, h))
        curx += w
        if h > row_h: row_h = h
    expected_h = cury + row_h
    if expected_h != sh:
        print(f"WARNING: computed sheet height {expected_h} != actual {sh}. "
              f'Check that your BMP uses the same packing as vanilla.')

    # Build new frames with original offsets; respect index 255 transparency
    frame_bytes_by_index = {}
    for i in range(nf):
        x0, y0, w, h = rects[i]
        # extract indices into grid[h][w]
        grid = [sheet[y0+yy][x0:x0+w] for yy in range(h)]
        # enforce: outside-of-rect remains transparent, inside is whatever indices are
        xoff, yoff = offs[i]
        encoded = encode_frame_u8(grid, w, h, xoff, yoff)
        encoded = patch_type_frame(encoded, TARGET_SHAPE_INDEX, i)
        frame_bytes_by_index[i] = encoded

    # Try in-place; otherwise rebuild
    inplace_ok = True
    for i in range(nf):
        if len(frame_bytes_by_index[i]) > tinfo["frames"][i]["size"]:
            inplace_ok = False
            break

    if inplace_ok:
        mod_blob = blob
        for i in range(nf):
            ok = try_inplace_write(mod_blob, recs, TARGET_SHAPE_INDEX, i, frame_bytes_by_index[i])
            if not ok:
                inplace_ok = False
                break
        if not inplace_ok:
            mod_blob = rebuild_type_and_file(blob, recs, TARGET_SHAPE_INDEX, frame_bytes_by_index)
    else:
        mod_blob = rebuild_type_and_file(blob, recs, TARGET_SHAPE_INDEX, frame_bytes_by_index)

    # Backup & write
    bak = flx_path + ".bak"
    if not os.path.exists(bak):
        shutil.copyfile(flx_path, bak)
        print(f"Backed up original -> {bak}")
    else:
        print(f"Backup exists: {bak}")

    with open(flx_path, "wb") as f:
        f.write(mod_blob)

    print("Done: shape 523 replaced with your sheet frames (keeping vanilla offsets).")

if __name__ == "__main__":
    try:
        main()
    except ImportError as e:
        print("This script needs Pillow. Install with: pip install pillow")
        raise
    except Exception as e:
        print("ERROR:", e)
        raise
