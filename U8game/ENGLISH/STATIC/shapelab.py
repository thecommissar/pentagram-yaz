#!/usr/bin/env python3
# Ultima VIII Shape Lab — single-frame resize + offset editing
# Drop this next to U8SHAPES.FLX / U8PAL.PAL (or run from STATIC)

import os, sys, struct, shutil
from typing import List, Tuple, Dict, Optional

import pygame
from pygame import Surface, Rect

# ----- optional file dialog (no visible window) -----
try:
    import tkinter as tk
    from tkinter import filedialog
    HAS_TK = True
except Exception:
    HAS_TK = False

# ---------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------

DEFAULT_FLX = "U8SHAPES.FLX"
DEFAULT_PAL = "U8PAL.PAL"

W, H = 1280, 860
UI_W = 460
PADDING = 14
FPS = 60

CANVAS_BG = (18, 18, 18)
PANEL_BG  = (28, 28, 28)
PANEL_FG  = (230, 230, 230)
ACCENT    = (120, 170, 255)
OKC       = (130, 215, 130)
GRID_DK   = (36, 36, 36)
GRID_LT   = (48, 48, 48)

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def clamp(v, a, b): return a if v < a else b if v > b else v
def u16(b, o=0): return b[o] | (b[o+1] << 8)
def i16(b, o=0): return struct.unpack_from("<h", b, o)[0]
def put_u16(v):  return struct.pack("<H", v)
def put_u24(v):  return bytes((v & 0xFF, (v>>8)&0xFF, (v>>16)&0xFF))

def mm_to_rgb(v):  # VGA 0..63 -> 0..255
    x = int(v) * 4
    return 255 if x > 255 else x

# ---------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------

def load_palette(path: str) -> List[Tuple[int,int,int]]:
    with open(path, "rb") as f:
        raw = f.read()
    if len(raw) < 4 + 768:
        raise ValueError("U8PAL.PAL too small or wrong file.")
    base = 4
    out = []
    for i in range(256):
        r = mm_to_rgb(raw[base + 3*i + 0])
        g = mm_to_rgb(raw[base + 3*i + 1])
        b = mm_to_rgb(raw[base + 3*i + 2])
        out.append((r,g,b))
    return out

# ---------------------------------------------------------------------
# FLX parsing
# ---------------------------------------------------------------------

def load_flx_table(blob: bytearray):
    if len(blob) < 136:
        raise ValueError("U8SHAPES.FLX too small.")
    count = u16(blob, 84)
    recs = []
    table_off = 128
    for i in range(count):
        off  = int.from_bytes(blob[table_off + i*8 + 0: table_off + i*8 + 4], "little")
        size = int.from_bytes(blob[table_off + i*8 + 4: table_off + i*8 + 8], "little")
        recs.append({"off": off, "size": size})
    return count, recs

def read_type_chunk(blob: bytearray, rec):
    off = rec["off"]; size = rec["size"]
    chunk = blob[off: off+size]
    head04 = chunk[0:4]
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

# ---------------------------------------------------------------------
# U8 frame decode / encode (matches U8VIEW.BAS logic)
# ---------------------------------------------------------------------

def decode_frame_to_indices(blob: bytearray, abs_off: int):
    comp = u16(blob, abs_off + 8)
    xlen = u16(blob, abs_off + 10)
    ylen = u16(blob, abs_off + 12)
    xoff = i16(blob, abs_off + 14)
    yoff = i16(blob, abs_off + 16)

    if xlen == 0 or ylen == 0:
        return [[255]*max(1,xlen) for _ in range(max(1,ylen))], xlen, ylen, xoff, yoff, comp

    grid = [[255]*xlen for _ in range(ylen)]
    offsets_start = abs_off + 18

    for y in range(ylen):
        word_pos = offsets_start + 2*y
        rel = u16(blob, word_pos)
        p = word_pos + rel

        xpos = blob[p]; p += 1
        while True:
            if xpos == xlen:
                break
            dlen = blob[p]; p += 1
            if comp == 0:
                for i in range(dlen):
                    if 0 <= xpos+i < xlen:
                        grid[y][xpos+i] = blob[p+i]
                p += dlen
            else:
                if (dlen & 1) == 1:
                    run = dlen >> 1
                    color = blob[p]; p += 1
                    for i in range(run):
                        if 0 <= xpos+i < xlen:
                            grid[y][xpos+i] = color
                    dlen = run
                else:
                    run = dlen >> 1
                    for i in range(run):
                        if 0 <= xpos+i < xlen:
                            grid[y][xpos+i] = blob[p+i]
                    p += run
                    dlen = run
            xpos += dlen
            if xpos < xlen:
                skip = blob[p]; p += 1
                xpos += skip
    return grid, xlen, ylen, xoff, yoff, comp

def encode_frame_u8(index_grid: List[List[int]], xlen: int, ylen: int, xoff: int, yoff: int) -> bytes:
    """Compression=1 stream, with simple literal vs repeated runs."""
    lines: List[bytes] = []
    for y in range(ylen):
        row = index_grid[y]
        rle = bytearray()
        xpos = 0
        while xpos < xlen:
            # gap of transparent (255)
            start = xpos
            while start < xlen and row[start] == 255:
                start += 1
            rle.append((start - xpos) & 0xFF)
            xpos = start
            if xpos >= xlen:
                break
            # run of opaque
            end = xpos
            while end < xlen and row[end] != 255:
                end += 1
            p = xpos
            while p < end:
                chunk = min(127, end - p)  # 7-bit length
                c0 = row[p]
                repeated = True
                for k in range(1, chunk):
                    if row[p+k] != c0:
                        repeated = False
                        break
                if repeated:
                    rle.append((chunk << 1) | 1)
                    rle.append(c0 & 0xFF)
                else:
                    rle.append((chunk << 1) | 0)
                    rle.extend((row[p+i] & 0xFF) for i in range(chunk))
                p += chunk
            xpos = end
        lines.append(bytes(rle))

    # line-offsets (relative) are written as: (remaining_lines*2) + bytes_before_this_line
    offsets = []
    sofar = 0
    for i, line in enumerate(lines):
        offsets.append((len(lines) - i) * 2 + sofar)
        sofar += len(line)

    header = struct.pack("<HHIHHHHH",
                         0, 0, 0,      # type, frame, unknown (not used)
                         1,            # compression
                         xlen, ylen,
                         xoff, yoff)

    off_table = bytearray()
    for v in offsets:
        off_table += put_u16(v & 0xFFFF)

    return header + off_table + b"".join(lines)

def patch_type_frame(frame_bytes: bytes, type_index: int, frame_index: int) -> bytes:
    b = bytearray(frame_bytes)
    b[0:2] = put_u16(type_index)
    b[2:4] = put_u16(frame_index)
    return bytes(b)

# ---------------------------------------------------------------------
# Palette mapping / image loading
# ---------------------------------------------------------------------

def nearest_index(rgb: Tuple[int,int,int], pal: List[Tuple[int,int,int]]) -> int:
    r,g,b = rgb
    best = 0
    bd = 1e12
    for i,(pr,pg,pb) in enumerate(pal):
        dr = r - pr; dg = g - pg; db = b - pb
        d = dr*dr + dg*dg + db*db
        if d < bd:
            bd = d; best = i
    return best

def pil_load_indices(path: str, pal: List[Tuple[int,int,int]]) -> Tuple[List[List[int]], int, int]:
    from PIL import Image
    im = Image.open(path).convert("RGBA")
    w, h = im.size
    px = im.load()
    grid = []
    for y in range(h):
        row = []
        for x in range(w):
            r,g,b,a = px[x,y]
            if a < 128:
                row.append(255)
            else:
                row.append(nearest_index((r,g,b), pal))
        grid.append(row)
    return grid, w, h

# ---------------------------------------------------------------------
# Sheet slicing (transparency-aligned)
# ---------------------------------------------------------------------

def slice_sheet_to_grids(path: str, pal: List[Tuple[int,int,int]], frames_meta: List[Dict]) -> Dict[int, List[List[int]]]:
    """Cut a multi-frame sheet into exact frame sizes, starting each frame
       at the first opaque column of the row band (tolerates transparent gutters)."""
    from PIL import Image
    im = Image.open(path).convert("RGBA")
    sw, sh = im.size
    px = im.load()

    def col_has_opaque(x, y0, y1):
        y1 = min(y1, sh)
        for yy in range(y0, y1):
            if x >= sw: return False
            if px[x, yy][3] >= 128:
                return True
        return False

    rows = []
    cur = []; curw = 0; row_h = 0
    for fr in frames_meta:
        w = max(1, fr["w"]); h = max(1, fr["h"])
        if cur and curw + w > sw:
            rows.append((cur, row_h))
            cur = []; curw = 0; row_h = 0
        cur.append((w, h))
        curw += w
        row_h = max(row_h, h)
    if cur:
        rows.append((cur, row_h))

    grids: Dict[int, List[List[int]]] = {}
    fi = 0
    y = 0
    for dims, row_h in rows:
        # skip transparent rows above the content band
        while y < sh:
            band_has_opaque = any(px[x, yy][3] >= 128
                                  for yy in range(y, min(y+row_h, sh))
                                  for x in range(sw))
            if band_has_opaque: break
            y += 1

        # find row start
        x = 0
        while x < sw and not col_has_opaque(x, y, y+row_h):
            x += 1

        for (w, h) in dims:
            g = [[255]*w for _ in range(h)]
            for yy in range(h):
                for xx in range(w):
                    if x+xx >= sw or y+yy >= sh:
                        continue
                    r,gg,b,a = px[x+xx, y+yy]
                    g[yy][xx] = 255 if a < 128 else nearest_index((r,gg,b), pal)
            grids[fi] = g
            fi += 1

            # advance to next opaque column after the block
            x += w
            while x < sw and not col_has_opaque(x, y, y+row_h):
                x += 1

        y += row_h
    return grids

# ---------------------------------------------------------------------
# Surface building
# ---------------------------------------------------------------------

def make_surface_from_indices(grid: List[List[int]], pal: List[Tuple[int,int,int]], scale=1.0) -> Surface:
    h = len(grid)
    w = len(grid[0]) if h else 1
    surf = pygame.Surface((w, h), pygame.SRCALPHA, 32)

    rgb = pygame.surfarray.pixels3d(surf)
    a = pygame.surfarray.pixels_alpha(surf)
    for y in range(h):
        row = grid[y]
        for x in range(w):
            idx = row[x]
            if idx == 255:
                rgb[x, y] = (0, 0, 0); a[x, y] = 0
            else:
                r, g, b = pal[idx]
                rgb[x, y] = (r, g, b); a[x, y] = 255
    del rgb, a

    if scale != 1.0:
        surf = pygame.transform.scale(surf, (int(w*scale), int(h*scale)))
    return surf

# ---------------------------------------------------------------------
# Save helpers
# ---------------------------------------------------------------------

def try_inplace_write(blob: bytearray, recs, type_index: int, frame_index: int, new_frame: bytes) -> bool:
    rec = recs[type_index]
    tinfo = read_type_chunk(blob, rec)
    abs_off = rec["off"] + tinfo["frames"][frame_index]["rel"]
    orig_sz = tinfo["frames"][frame_index]["size"]
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

    head = bytearray()
    head += tinfo["raw_head04"]
    head += put_u16(nf)

    base_rel = 6 + nf*6
    rel_cursor = base_rel
    hdrs = bytearray()
    data = bytearray()

    for i in range(nf):
        unk = frames[i]["unk"]
        abs_off = rec["off"] + frames[i]["rel"]
        orig = blob[abs_off: abs_off + frames[i]["size"]]
        chunk = frame_replacements.get(i, orig)
        hdrs += put_u24(rel_cursor)
        hdrs += bytes((unk,))
        hdrs += put_u16(len(chunk))
        data += chunk
        rel_cursor += len(chunk)

    new_chunk = bytes(head + hdrs + data)

    before = blob[:rec["off"]]
    after  = blob[rec["off"] + rec["size"]:]
    new_blob = bytearray(before + new_chunk + after)

    count = u16(new_blob, 84)
    table_off = 128
    new_blob[table_off + type_index*8 + 4: table_off + type_index*8 + 8] = len(new_chunk).to_bytes(4, "little")
    delta = len(new_chunk) - rec["size"]
    for i in range(type_index+1, count):
        off = int.from_bytes(new_blob[table_off + i*8 + 0: table_off + i*8 + 4], "little")
        if off != 0:
            off += delta
            new_blob[table_off + i*8 + 0: table_off + i*8 + 4] = off.to_bytes(4, "little")
    return new_blob

# ---------------------------------------------------------------------
# UI widgets (simple)
# ---------------------------------------------------------------------

class Button:
    def __init__(self, rect: Rect, label: str, cb):
        self.rect = Rect(rect); self.label = label; self.cb = cb
    def draw(self, surf, font):
        pygame.draw.rect(surf, (50,50,60), self.rect, border_radius=8)
        pygame.draw.rect(surf, (90,90,110), self.rect, 2, border_radius=8)
        txt = font.render(self.label, True, PANEL_FG)
        surf.blit(txt, txt.get_rect(center=self.rect.center))
    def handle(self, ev):
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.rect.collidepoint(ev.pos):
            self.cb()

class Stepper:
    def __init__(self, rect: Rect, label: str, getter, setter, step=1, minv=0, maxv=9999):
        self.rect = Rect(rect)
        self.label = label; self.getter = getter; self.setter = setter
        self.step = step; self.minv = minv; self.maxv = maxv
        w = self.rect.w
        self.r_lbl = Rect(self.rect.x, self.rect.y, w, 18)
        y2 = self.rect.y + 24
        self.r_minus = Rect(self.rect.x, y2, (w//2)-6, 30)
        self.r_plus  = Rect(self.rect.x+(w//2)+6, y2, (w//2)-6, 30)
    def _maxv(self):
        return self.maxv() if callable(self.maxv) else self.maxv
    def draw(self, surf, font):
        cap = f"{self.label}: {self.getter()}"
        surf.blit(font.render(cap, True, PANEL_FG), (self.r_lbl.x+4, self.r_lbl.y))
        for r in (self.r_minus, self.r_plus):
            pygame.draw.rect(surf, (50,50,60), r, border_radius=6)
            pygame.draw.rect(surf, (90,90,110), r, 2, border_radius=6)
        t1 = font.render("-", True, PANEL_FG); t2 = font.render("+", True, PANEL_FG)
        surf.blit(t1, t1.get_rect(center=self.r_minus.center))
        surf.blit(t2, t2.get_rect(center=self.r_plus.center))
    def handle(self, ev):
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            if self.r_minus.collidepoint(ev.pos):
                self.setter(clamp(self.getter()-self.step, self.minv, self._maxv()))
            elif self.r_plus.collidepoint(ev.pos):
                self.setter(clamp(self.getter()+self.step, self.minv, self._maxv()))

class Toggle:
    def __init__(self, rect, label, getter, setter):
        self.rect = Rect(rect); self.label = label; self.getter = getter; self.setter = setter
    def draw(self, surf, font):
        val = self.getter()
        pygame.draw.rect(surf, (50,50,60), self.rect, border_radius=8)
        pygame.draw.rect(surf, (90,90,110), self.rect, 2, border_radius=8)
        cap = f"{self.label}: {'On' if val else 'Off'}"
        txt = font.render(cap, True, OKC if val else PANEL_FG)
        surf.blit(txt, txt.get_rect(center=self.rect.center))
    def handle(self, ev):
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.rect.collidepoint(ev.pos):
            self.setter(not self.getter())

class InputBox:
    def __init__(self, rect: Rect, label: str, getter, setter, numeric=True):
        self.rect = Rect(rect)
        self.label = label; self.getter = getter; self.setter = setter
        self.numeric = numeric
        self.text = str(getter())
        self.focus = False
        self.cursor = len(self.text)
        self.blink = 0
    def draw(self, surf, font):
        lab = font.render(self.label, True, PANEL_FG)
        surf.blit(lab, (self.rect.x, self.rect.y-20))
        inner = Rect(self.rect)
        pygame.draw.rect(surf, (50,50,60), inner, border_radius=6)
        pygame.draw.rect(surf, (90,90,110), inner, 2, border_radius=6)
        txt = font.render(self.text, True, PANEL_FG)
        surf.blit(txt, (inner.x+8, inner.y+6))
        if self.focus:
            self.blink = (self.blink + 1) % 60
            if self.blink < 30:
                cx = inner.x + 8 + font.size(self.text[:self.cursor])[0]
                cy = inner.y + 6
                pygame.draw.line(surf, PANEL_FG, (cx, cy), (cx, cy+font.get_height()), 1)
    def handle(self, ev):
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            self.focus = self.rect.collidepoint(ev.pos)
        if not self.focus: return
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_RETURN:
                try:
                    v = int(self.text) if self.numeric else self.text
                    self.setter(v)
                except: pass
                self.text = str(self.getter()); self.cursor = len(self.text)
            elif ev.key == pygame.K_BACKSPACE:
                if self.cursor > 0:
                    self.text = self.text[:self.cursor-1] + self.text[self.cursor:]
                    self.cursor -= 1
            elif ev.key == pygame.K_DELETE:
                if self.cursor < len(self.text):
                    self.text = self.text[:self.cursor] + self.text[self.cursor+1:]
            elif ev.key == pygame.K_LEFT:
                self.cursor = max(0, self.cursor-1)
            elif ev.key == pygame.K_RIGHT:
                self.cursor = min(len(self.text), self.cursor+1)
            else:
                ch = ev.unicode
                if self.numeric:
                    if ch in "+-" or ch.isdigit():
                        self.text = self.text[:self.cursor] + ch + self.text[self.cursor:]
                        self.cursor += 1
                else:
                    if ch and ch.isprintable():
                        self.text = self.text[:self.cursor] + ch + self.text[self.cursor:]
                        self.cursor += 1

# ---------------------------------------------------------------------
# App
# ---------------------------------------------------------------------

class ShapeLab:
    def __init__(self, screen: Surface, flx_path: str, pal_path: str):
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas,menlo,monospace", 16)
        self.font_small = pygame.font.SysFont("consolas,menlo,monospace", 13)

        self.flx_path = flx_path
        self.pal = load_palette(pal_path)

        with open(self.flx_path, "rb") as f:
            self.flx_blob = bytearray(f.read())
        self.count, self.recs = load_flx_table(self.flx_blob)

        self.shape_idx = 523
        self.frame_idx = 0
        self.show_all = False
        self.zoom = 2.0

        # loaded frame data cache
        self.shape_frames: Dict[int, Dict] = {}
        self.ensure_shape_loaded(self.shape_idx)

        # preview state
        self.preview_shape_sheet: Optional[Dict[int, List[List[int]]]] = None
        self.preview_frame_grid: Optional[List[List[int]]] = None
        self.preview_resize: bool = False      # true when preview frame differs in size
        self.preview_w = 0
        self.preview_h = 0
        self.preview_xoff = 0
        self.preview_yoff = 0

        self.widgets: List = []
        self.build_ui()

        if HAS_TK:
            self.tk = tk.Tk(); self.tk.withdraw()

    # ---------- data ----------
    def ensure_shape_loaded(self, idx: int):
        if idx in self.shape_frames:
            return
        rec = self.recs[idx]
        t = read_type_chunk(self.flx_blob, rec)
        frames_data = []
        for i, fh in enumerate(t["frames"]):
            abs_off = rec["off"] + fh["rel"]
            grid, w, h, xoff, yoff, comp = decode_frame_to_indices(self.flx_blob, abs_off)
            surf = make_surface_from_indices(grid, self.pal)
            frames_data.append({"w":w,"h":h,"xoff":xoff,"yoff":yoff,"grid":grid,"surf":surf,"abs_off":abs_off,"size":fh["size"]})
        self.shape_frames[idx] = {"num": t["num_frames"], "frames": frames_data, "rec": rec, "tinfo": t}
        self.frame_idx = clamp(self.frame_idx, 0, self.shape_frames[idx]["num"]-1)

    # ---------- UI ----------
    def build_ui(self):
        px = W-UI_W + PADDING
        y  = 16
        self.widgets = []
        y += 90

        # Shape step + input
        label_h = 20; btn_h = 32; row_h = label_h + 6 + btn_h
        self.shape_minus = Button(Rect(px, y+label_h+6, 48, btn_h), "−", lambda: self.set_shape(self.shape_idx-1))
        self.shape_input = InputBox(Rect(px+54, y+label_h+6, 200, btn_h), "Shape #", self.get_shape, self.set_shape, numeric=True)
        self.shape_plus  = Button(Rect(px+54+200+6, y+label_h+6, 48, btn_h), "+", lambda: self.set_shape(self.shape_idx+1))
        self.widgets += [self.shape_minus, self.shape_input, self.shape_plus]
        y += row_h + 16

        # frame stepper
        self.step_frame = Stepper(
            Rect(px, y, UI_W - 2*PADDING, 56),
            "Frame",
            self.get_frame,
            self.set_frame,
            step=1, minv=0, maxv=lambda:self.shape_frames[self.shape_idx]["num"]-1
        )
        self.widgets.append(self.step_frame)
        y += 18 + 6 + 30 + 16

        # show all toggle
        self.widgets.append(Toggle(Rect(px, y, UI_W - 2*PADDING, 34), "Show all frames", self.get_show_all, self.set_show_all))
        y += 34 + 16

        # zoom
        self.step_zoom = Stepper(Rect(px, y, UI_W - 2*PADDING, 56), "Zoom x", self.get_zoom_i, self.set_zoom_i,
                                 step=1, minv=1, maxv=8)
        self.widgets.append(self.step_zoom)
        y += 18 + 6 + 30 + 16

        # imports
        self.widgets.append(Button(Rect(px, y, UI_W - 2*PADDING, 38), "Import single frame (keep size)...", self.import_frame_keep))
        y += 38 + 10
        self.widgets.append(Button(Rect(px, y, UI_W - 2*PADDING, 38), "Import single frame (resize allowed)...", self.import_frame_resize))
        y += 38 + 10
        self.widgets.append(Button(Rect(px, y, UI_W - 2*PADDING, 38), "Import whole shape (sheet)...", self.import_sheet))
        y += 38 + 10

        # preview / offsets / save
        self.widgets.append(Button(Rect(px, y, UI_W - 2*PADDING, 34), "Clear preview", self.clear_preview))
        y += 34 + 14

        # offset inputs (active when preview_resize or single preview exists)
        self.in_xoff = InputBox(Rect(px, y, (UI_W-2*PADDING-10)//2, 32), "X offset", self.get_xoff_ui, self.set_xoff_ui, numeric=True)
        self.in_yoff = InputBox(Rect(px + (UI_W-2*PADDING-10)//2 + 10, y, (UI_W-2*PADDING-10)//2, 32), "Y offset", self.get_yoff_ui, self.set_yoff_ui, numeric=True)
        self.widgets += [self.in_xoff, self.in_yoff]
        y += 32 + 18

        self.widgets.append(Button(Rect(px, y, UI_W - 2*PADDING, 44), "Save changes", self.commit_save))

    # getters/setters
    def get_shape(self): return self.shape_idx
    def set_shape(self, v):
        v = clamp(int(v), 0, self.count-1)
        if v != self.shape_idx:
            self.shape_idx = v
            self.ensure_shape_loaded(v)
            self.frame_idx = clamp(self.frame_idx, 0, self.shape_frames[self.shape_idx]["num"]-1)
            if isinstance(self.shape_input, InputBox):
                self.shape_input.text = str(self.shape_idx)
                self.shape_input.cursor = len(self.shape_input.text)
            self.clear_preview()
    def get_frame(self): return self.frame_idx
    def set_frame(self, v):
        self.frame_idx = clamp(int(v), 0, self.shape_frames[self.shape_idx]["num"]-1)
        self.sync_offset_inputs()
    def get_show_all(self): return self.show_all
    def set_show_all(self, v): self.show_all = bool(v)
    def get_zoom_i(self): return int(self.zoom)
    def set_zoom_i(self, vi): self.zoom = clamp(float(vi), 1.0, 8.0)

    # offset UI
    def get_xoff_ui(self):
        if self.preview_resize or (self.preview_frame_grid is not None):
            return self.preview_xoff
        return self.shape_frames[self.shape_idx]["frames"][self.frame_idx]["xoff"]
    def get_yoff_ui(self):
        if self.preview_resize or (self.preview_frame_grid is not None):
            return self.preview_yoff
        return self.shape_frames[self.shape_idx]["frames"][self.frame_idx]["yoff"]
    def set_xoff_ui(self, v):
        v = int(v)
        if self.preview_resize or (self.preview_frame_grid is not None):
            self.preview_xoff = v
        else:
            self.shape_frames[self.shape_idx]["frames"][self.frame_idx]["xoff"] = v
    def set_yoff_ui(self, v):
        v = int(v)
        if self.preview_resize or (self.preview_frame_grid is not None):
            self.preview_yoff = v
        else:
            self.shape_frames[self.shape_idx]["frames"][self.frame_idx]["yoff"] = v
    def sync_offset_inputs(self):
        fr = self.shape_frames[self.shape_idx]["frames"][self.frame_idx]
        self.preview_xoff = fr["xoff"]; self.preview_yoff = fr["yoff"]
        if isinstance(self.in_xoff, InputBox):
            self.in_xoff.text = str(self.get_xoff_ui()); self.in_xoff.cursor = len(self.in_xoff.text)
        if isinstance(self.in_yoff, InputBox):
            self.in_yoff.text = str(self.get_yoff_ui()); self.in_yoff.cursor = len(self.in_yoff.text)

    # ---------- Import / preview ----------
    def ask_file(self, title):
        if not HAS_TK:
            print("tkinter not available; put your file path here:")
            return input("Path: ").strip()
        path = filedialog.askopenfilename(title=title)
        return path or ""

    def import_frame_keep(self):
        path = self.ask_file("Choose replacement frame image (keep size)")
        if not path: return
        grid, w, h = pil_load_indices(path, self.pal)
        fr = self.shape_frames[self.shape_idx]["frames"][self.frame_idx]
        if w != fr["w"] or h != fr["h"]:
            # rescale to match original frame
            tmp = make_surface_from_indices(grid, self.pal)
            tmp = pygame.transform.smoothscale(tmp, (fr["w"], fr["h"]))
            px = pygame.surfarray.pixels3d(tmp)
            al = pygame.surfarray.pixels_alpha(tmp)
            g2 = []
            for y in range(fr["h"]):
                row=[]
                for x in range(fr["w"]):
                    if al[x,y] < 128: row.append(255)
                    else: row.append(nearest_index(tuple(px[x,y]), self.pal))
                g2.append(row)
            del px, al
            grid = g2
        self.preview_frame_grid = grid
        self.preview_resize = False
        self.preview_w, self.preview_h = fr["w"], fr["h"]
        self.preview_xoff, self.preview_yoff = fr["xoff"], fr["yoff"]
        self.preview_shape_sheet = None

    def import_frame_resize(self):
        path = self.ask_file("Choose replacement frame image (allow resize)")
        if not path: return
        grid, w, h = pil_load_indices(path, self.pal)
        fr = self.shape_frames[self.shape_idx]["frames"][self.frame_idx]
        # keep old offsets by default so the anchor remains stable
        self.preview_frame_grid = grid
        self.preview_resize = True
        self.preview_w, self.preview_h = w, h
        self.preview_xoff, self.preview_yoff = fr["xoff"], fr["yoff"]
        self.preview_shape_sheet = None
        self.sync_offset_inputs()

    def import_sheet(self):
        path = self.ask_file("Choose replacement sheet for WHOLE SHAPE")
        if not path: return
        shinfo = self.shape_frames[self.shape_idx]
        frames = shinfo["frames"]
        meta = [{"w":f["w"], "h":f["h"]} for f in frames]
        grids = slice_sheet_to_grids(path, self.pal, meta)
        self.preview_shape_sheet = grids
        self.preview_frame_grid = None
        self.preview_resize = False

    def clear_preview(self):
        self.preview_frame_grid = None
        self.preview_shape_sheet = None
        self.preview_resize = False

    # ---------- Save ----------
    def commit_save(self):
        if (self.preview_frame_grid is None) and (self.preview_shape_sheet is None):
            print("Nothing to save.")
            return

        tinfo = self.shape_frames[self.shape_idx]
        frames = tinfo["frames"]
        repl: Dict[int, bytes] = {}

        if self.preview_shape_sheet is not None:
            for i, fr in enumerate(frames):
                grid = self.preview_shape_sheet.get(i)
                if grid is None: continue
                enc = encode_frame_u8(grid, fr["w"], fr["h"], fr["xoff"], fr["yoff"])
                enc = patch_type_frame(enc, self.shape_idx, i)
                repl[i] = enc

        if self.preview_frame_grid is not None:
            # use preview size/offsets (may differ from original)
            if self.preview_resize:
                w, h = self.preview_w, self.preview_h
                xo, yo = self.preview_xoff, self.preview_yoff
            else:
                fr = frames[self.frame_idx]
                w, h = fr["w"], fr["h"]
                xo, yo = fr["xoff"], fr["yoff"]
            enc = encode_frame_u8(self.preview_frame_grid, w, h, xo, yo)
            enc = patch_type_frame(enc, self.shape_idx, self.frame_idx)
            repl[self.frame_idx] = enc

        # try in-place then rebuild if needed
        inplace_ok = True
        for i, enc in repl.items():
            if len(enc) > frames[i]["size"]:
                inplace_ok = False
                break

        if inplace_ok:
            mod = self.flx_blob
            for i, enc in repl.items():
                ok = try_inplace_write(mod, self.recs, self.shape_idx, i, enc)
                if not ok:
                    inplace_ok = False
                    break
            if not inplace_ok:
                mod = rebuild_type_and_file(self.flx_blob, self.recs, self.shape_idx, repl)
        else:
            mod = rebuild_type_and_file(self.flx_blob, self.recs, self.shape_idx, repl)

        bak = self.flx_path + ".bak"
        if not os.path.exists(bak):
            shutil.copyfile(self.flx_path, bak)
            print(f"Backed up original -> {bak}")
        with open(self.flx_path, "wb") as f:
            f.write(mod)
        print("Saved changes to U8SHAPES.FLX")

        self.flx_blob = mod
        if self.shape_idx in self.shape_frames:
            del self.shape_frames[self.shape_idx]
        self.ensure_shape_loaded(self.shape_idx)
        self.clear_preview()

    # ---------- Drawing ----------
    def draw_checker(self, surf: Surface, rect: Rect, cell=16):
        x0,y0,w,h = rect
        for y in range(y0, y0+h, cell):
            for x in range(x0, x0+w, cell):
                c = GRID_DK if ((x//cell + y//cell) & 1) else GRID_LT
                pygame.draw.rect(surf, c, (x,y,cell,cell))

    def draw_panel(self, surf: Surface):
        px = W-UI_W
        pygame.draw.rect(surf, PANEL_BG, (px,0,UI_W,H))

        title = self.font.render("Ultima VIII Shape Lab", True, PANEL_FG)
        surf.blit(title, (px+PADDING, 12))

        info = [
            f"FLX: {os.path.basename(self.flx_path)}",
            f"Shapes: {self.count}",
            f"Shape #{self.shape_idx} frames: {self.shape_frames[self.shape_idx]['num']}",
            "Keys: ←/→ frame   ↑/↓ shape   A toggle grid",
            "      +/- zoom    Shift+arrows = offset x5",
        ]
        y = 12 + 28
        for s in info:
            surf.blit(self.font_small.render(s, True, PANEL_FG), (px+PADDING, y))
            y += 18

        for w in self.widgets:
            if hasattr(w, "draw"):
                w.draw(surf, self.font)

        y = H-92
        if self.preview_frame_grid is not None:
            msg = "Preview: single frame ({}size)".format("RESIZED " if self.preview_resize else "kept ")
            surf.blit(self.font_small.render(msg, True, ACCENT), (px+PADDING, y)); y+=18
        if self.preview_shape_sheet is not None:
            surf.blit(self.font_small.render("Preview: whole shape (sheet)", True, ACCENT), (px+PADDING, y)); y+=18
        surf.blit(self.font_small.render("Index 255 = transparent", True, (170,170,170)), (px+PADDING, y))

    def draw_canvas(self, surf: Surface):
        rect = Rect(0,0,W-UI_W,H)
        self.draw_checker(surf, rect)

        sh = self.shape_frames[self.shape_idx]
        frames = sh["frames"]

        if self.show_all:
            pad = 12
            x = pad; y = pad; rowh = 0
            scale = self.zoom
            for i, fr in enumerate(frames):
                # Replace from sheet preview if available
                if (self.preview_shape_sheet is not None) and (i in self.preview_shape_sheet):
                    img = make_surface_from_indices(self.preview_shape_sheet[i], self.pal, scale=scale)
                else:
                    img = make_surface_from_indices(fr["grid"], self.pal, scale=scale)

                if x + img.get_width() > rect.w - pad:
                    x = pad; y += rowh + pad; rowh = 0
                surf.blit(img, (x, y))
                lbl = self.font_small.render(str(i), True, PANEL_FG)
                surf.blit(lbl, (x, y + img.get_height() + 2))
                rowh = max(rowh, img.get_height() + 18)
                x += img.get_width() + pad
        else:
            i = self.frame_idx
            fr = frames[i]

            if self.preview_frame_grid is not None:
                # Show exactly the preview (supports different size)
                base = make_surface_from_indices(self.preview_frame_grid, self.pal, scale=self.zoom)
                xo, yo = self.preview_xoff, self.preview_yoff
            elif (self.preview_shape_sheet is not None) and (i in self.preview_shape_sheet):
                base = make_surface_from_indices(self.preview_shape_sheet[i], self.pal, scale=self.zoom)
                xo, yo = fr["xoff"], fr["yoff"]
            else:
                base = make_surface_from_indices(fr["grid"], self.pal, scale=self.zoom)
                xo, yo = fr["xoff"], fr["yoff"]

            x = (rect.w - base.get_width())//2
            y = (rect.h - base.get_height())//2
            surf.blit(base, (x,y))

            # draw anchor cross using current offsets (preview or original)
            ox = int(x + (-xo) * self.zoom)
            oy = int(y + (-yo) * self.zoom)
            pygame.draw.line(surf, (255,80,80), (ox-20, oy), (ox+20, oy), 1)
            pygame.draw.line(surf, (255,80,80), (ox, oy-20), (ox, oy+20), 1)

            sz = f"{base.get_width()}x{base.get_height()} @ zoom {self.zoom:.1f}"
            cap = f"Frame {i}  off({xo},{yo})   {sz}"
            surf.blit(self.font.render(cap, True, PANEL_FG), (16, 16))

    # ---------- Loop ----------
    def run(self):
        self.sync_offset_inputs()
        running = True
        while running:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT: running = False
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE: running = False
                    if ev.key in (pygame.K_a, pygame.K_SPACE): self.set_show_all(not self.show_all)
                    if ev.key == pygame.K_LEFT:  self.set_frame(self.frame_idx-1)
                    if ev.key == pygame.K_RIGHT: self.set_frame(self.frame_idx+1)
                    if ev.key == pygame.K_UP:    self.set_shape(self.shape_idx+1)
                    if ev.key == pygame.K_DOWN:  self.set_shape(self.shape_idx-1)
                    if ev.key in (pygame.K_EQUALS, pygame.K_PLUS): self.set_zoom_i(self.get_zoom_i()+1)
                    if ev.key == pygame.K_MINUS: self.set_zoom_i(self.get_zoom_i()-1)

                    # offset nudges (active when preview is showing a single frame)
                    if self.preview_frame_grid is not None:
                        step = 5 if (pygame.key.get_mods() & pygame.KMOD_SHIFT) else 1
                        if ev.key == pygame.K_LEFT:  self.set_xoff_ui(self.get_xoff_ui()+step)   # move anchor right => increase xoff
                        if ev.key == pygame.K_RIGHT: self.set_xoff_ui(self.get_xoff_ui()-step)
                        if ev.key == pygame.K_UP:    self.set_yoff_ui(self.get_yoff_ui()+step)
                        if ev.key == pygame.K_DOWN:  self.set_yoff_ui(self.get_yoff_ui()-step)

                for w in self.widgets:
                    if hasattr(w, "handle"): w.handle(ev)

            self.screen.fill(CANVAS_BG)
            self.draw_canvas(self.screen)
            self.draw_panel(self.screen)
            pygame.display.flip()
            self.clock.tick(FPS)

# ---------------------------------------------------------------------
# Boot
# ---------------------------------------------------------------------

def main():
    flx = DEFAULT_FLX if os.path.exists(DEFAULT_FLX) else os.path.join("STATIC", DEFAULT_FLX)
    pal = DEFAULT_PAL if os.path.exists(DEFAULT_PAL) else os.path.join("STATIC", DEFAULT_PAL)
    if not os.path.exists(flx):
        print("U8SHAPES.FLX not found next to the script. Put it here or run from STATIC.")
        sys.exit(1)
    if not os.path.exists(pal):
        print("U8PAL.PAL not found next to the script. Put it here or run from STATIC.")
        sys.exit(1)

    pygame.init()
    pygame.display.set_caption("Ultima VIII Shape Lab")
    screen = pygame.display.set_mode((W, H))
    app = ShapeLab(screen, flx, pal)
    app.run()

if __name__ == "__main__":
    main()
