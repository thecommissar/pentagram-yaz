# u8_shape_targeted_remap_v2.py
# Remap only palette indices 32..47 -> 64..79 for SHAPE_INDEX = 1.
# Produces a new FLX beside the original and prints verification stats.

from pathlib import Path
from collections import defaultdict

IN_FLX  = Path("STATIC") / "U8SHAPES.FLX"
OUT_FLX = Path("STATIC") / "U8SHAPES_paltest.FLX"
SHAPE_INDEX = 1

FROM_START = 32     # inclusive
FROM_END   = 47     # inclusive
TO_START   = 64     # destination base (maps to 64..79)
DRY_RUN    = False  # True = don't write, just report stats

# ----------------- helpers -----------------

def u16(b, o): return b[o] | (b[o+1] << 8)
def u24(b, o): return b[o] | (b[o+1] << 8) | (b[o+2] << 16)
def u32(b, o): return (b[o] | (b[o+1] << 8) | (b[o+2] << 16) | (b[o+3] << 24)) & 0xFFFFFFFF

def in_window(idx: int) -> bool:
    return FROM_START <= idx <= FROM_END

def remap_idx(idx: int) -> int:
    return TO_START + (idx - FROM_START) if in_window(idx) else idx

def load_type_table(buf: bytearray):
    # FLX header (0-based, per updated doc):
    #  84: uint16 type_count
    # 128: type_count * 8 records: { uint32 offset, uint32 size }
    count = u16(buf, 84)
    base  = 128
    recs  = []
    for i in range(count):
        off = u32(buf, base + 8*i + 0)
        siz = u32(buf, base + 8*i + 4)
        recs.append((off, siz))
    return recs

# ----------------- core edit with stats -----------------

def process_shape(buf: bytearray, shape_index: int):
    type_tbl = load_type_table(buf)
    if not (0 <= shape_index < len(type_tbl)):
        raise IndexError(f"Shape index {shape_index} out of range (0..{len(type_tbl)-1})")

    type_off, type_size = type_tbl[shape_index]
    if type_off == 0 or type_size == 0:
        raise ValueError(f"Type {shape_index} is empty")

    frames = u16(buf, type_off + 4)
    print(f"Shape {shape_index}: {frames} frame(s)")

    frame_tbl = type_off + 6

    total_pixels = 0
    changed_pixels = 0
    changes_by_src = defaultdict(int)  # counts per original index (only those in window)
    touched_frames = 0

    for fi in range(frames):
        rel = u24(buf, frame_tbl + fi*6 + 0)
        frame_off = type_off + rel

        comp  = u16(buf, frame_off + 8)
        xlen  = u16(buf, frame_off + 10)
        ylen  = u16(buf, frame_off + 12)

        if ylen == 0 or xlen == 0:
            continue

        linepos_base = frame_off + 18
        rle_base     = linepos_base + 2*ylen

        frame_changed = False

        for y in range(ylen):
            # Pentagram/U8 interpretation: line offset is relative to the *start of linepos entry*
            # Adjust to get a pointer relative to rle_base.
            val = u16(buf, linepos_base + 2*y)
            line_rel = val - ((ylen - y) * 2)
            p = rle_base + line_rel

            xpos = buf[p]; p += 1  # Step 1: starting XPos
            while True:
                if xpos == xlen:
                    break

                dlen = buf[p]; p += 1

                if comp == 0:
                    # Raw run: exactly dlen literal pixels
                    run_len = dlen
                    total_pixels += run_len
                    # edit literal bytes in place
                    for i in range(run_len):
                        old = buf[p]
                        new = remap_idx(old)
                        if new != old:
                            buf[p] = new
                            changed_pixels += 1
                            if in_window(old): changes_by_src[old] += 1
                            frame_changed = True
                        p += 1
                    xpos += run_len
                else:
                    if (dlen & 1) == 1:
                        # Repeated-color run: length = dlen >> 1, next byte is the color
                        run_len = dlen >> 1
                        total_pixels += run_len
                        old = buf[p]
                        new = remap_idx(old)
                        if new != old:
                            buf[p] = new
                            changed_pixels += run_len
                            if in_window(old): changes_by_src[old] += run_len
                            frame_changed = True
                        p += 1
                        xpos += run_len
                    else:
                        # Literal run: (dlen >> 1) literal pixels
                        run_len = dlen >> 1
                        total_pixels += run_len
                        for i in range(run_len):
                            old = buf[p]
                            new = remap_idx(old)
                            if new != old:
                                buf[p] = new
                                changed_pixels += 1
                                if in_window(old): changes_by_src[old] += 1
                                frame_changed = True
                            p += 1
                        xpos += run_len

                if xpos < xlen:
                    # gap byte: transparent pixels; do not edit, just advance
                    skip = buf[p]; p += 1
                    xpos += skip

        if frame_changed:
            touched_frames += 1

    return {
        "frames": frames,
        "total_pixels": total_pixels,
        "changed_pixels": changed_pixels,
        "changes_by_src": dict(sorted(changes_by_src.items())),
        "touched_frames": touched_frames,
    }

def main():
    if not IN_FLX.exists():
        raise SystemExit(f"Cannot find {IN_FLX}")

    data_in  = bytearray(IN_FLX.read_bytes())
    data_out = bytearray(data_in)  # edit a copy

    print(f"Loaded {IN_FLX} ({len(data_in)} bytes)")
    print(f"Remap rule: {FROM_START}-{FROM_END} → {TO_START}-{TO_START + (FROM_END-FROM_START)} on shape {SHAPE_INDEX}")

    stats = process_shape(data_out, SHAPE_INDEX)

    # Print verification
    print("\n=== Verification ===")
    print(f"Frames touched: {stats['touched_frames']} / {stats['frames']}")
    print(f"Pixels total in runs: {stats['total_pixels']}")
    print(f"Pixels changed:       {stats['changed_pixels']}")
    if stats["changed_pixels"]:
        print("Changes by source index (only 32..47 should appear):")
        for src, cnt in stats["changes_by_src"].items():
            print(f"  {src:3d} → {TO_START + (src-FROM_START):3d} : {cnt}")

    if DRY_RUN:
        print("\nDRY_RUN=True; not writing output.")
        return

    OUT_FLX.write_bytes(data_out)
    print(f"\nWritten {OUT_FLX} (original left unchanged).")

if __name__ == "__main__":
    main()
