# u8_map_viewer.py  —  Single-file Ultima VIII map viewer (Tkinter + PIL)
# - Correct U8 shape decoding per Pentagram (row-offset 'unfudge')
# - Correct GLOB expansion and dimetric projection
# - Mouse zoom/pan, arrow-key pan, PNG export
#
# Requirements: Pillow (PIL)
#   pip install pillow

import io
import os
import struct
from pathlib import Path
from dataclasses import dataclass
from typing import List, Tuple, Optional

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk


# ---------- Low-level helpers ----------

def rd_u8(f) -> int:
    b = f.read(1)
    if len(b) != 1:
        raise EOFError
    return b[0]

def rd_u16(f) -> int:
    b = f.read(2)
    if len(b) != 2:
        raise EOFError
    return struct.unpack('<H', b)[0]

def rd_u24(f) -> int:
    b = f.read(3)
    if len(b) != 3:
        raise EOFError
    return b[0] | (b[1] << 8) | (b[2] << 16)

def rd_u32(f) -> int:
    b = f.read(4)
    if len(b) != 4:
        raise EOFError
    return struct.unpack('<I', b)[0]


# ---------- FLX archive ----------

class FlexArchive:
    """
    Minimal FLX reader:
      - Count at offset 0x54 (84)
      - Record table starts at 0x90 (144)
      - Each record: <u32 offset><u32 length>; zero=empty
    """
    def __init__(self, path: Path):
        self.path = Path(path)
        self.count = 0
        self.records: List[Tuple[int, int]] = []
        with open(self.path, 'rb') as f:
            f.seek(0x54)
            self.count = rd_u32(f)
            f.seek(0x90)
            for _ in range(self.count):
                off = rd_u32(f)
                ln = rd_u32(f)
                self.records.append((off, ln))
        self.size = self.path.stat().st_size

    def get_record(self, idx: int) -> Optional[bytes]:
        if idx < 0 or idx >= self.count:
            return None
        off, ln = self.records[idx]
        if off == 0 or ln == 0:
            return None
        with open(self.path, 'rb') as f:
            f.seek(off)
            return f.read(ln)


# ---------- Palette ----------

def load_palette(pal_path: Path) -> List[Tuple[int, int, int, int]]:
    """
    U8 palette: first 4 bytes often junk/unused, then 256*3 bytes (0..63) per channel.
    We expand to 0..255. Index 255 is transparent.
    """
    raw = Path(pal_path).read_bytes()
    if len(raw) < 4 + 256*3:
        raise ValueError("Palette file too small")
    raw_rgb = raw[4:4+256*3]
    pal: List[Tuple[int,int,int,int]] = []
    for i in range(256):
        r = raw_rgb[i*3 + 0] * 4
        g = raw_rgb[i*3 + 1] * 4
        b = raw_rgb[i*3 + 2] * 4
        a = 0 if i == 255 else 255
        pal.append((r, g, b, a))
    return pal


# ---------- Shapes ----------

@dataclass
class U8Frame:
    width: int
    height: int
    xoff: int
    yoff: int
    rgba: Image.Image  # premade RGBA image

class ShapeArchive:
    """
    Wraps u8shapes.flx (U8 shape format).
    - Frame headers inside a shape are 6 bytes:
        u24 frame_offset (relative to shape start)
        u8  unknown
        u16 frame_size
    - Frame chunk:
        0: u16 shape_index (ignored)
        2: u16 frame_index
        4: u32 unknown
        8: u16 compression (0 or 1)
       10: u16 width
       12: u16 height
       14: u16 xoff
       16: u16 yoff
       18: height * u16 line offsets (each entry must be "unfudged" like Pentagram)
        ... RLE row data
    """
    def __init__(self, flx_path: Path, palette: List[Tuple[int,int,int,int]]):
        self.flx = FlexArchive(flx_path)
        self.palette = palette
        self.cache: dict[Tuple[int, int], U8Frame] = {}  # (shape, frame) -> U8Frame

    def _decode_frame(self, shape_blob: bytes, frame_offset: int, frame_size: int) -> U8Frame:
        f = io.BytesIO(shape_blob)
        f.seek(frame_offset)

        # Frame header
        _shape_index = rd_u16(f)
        _frame_index = rd_u16(f)
        _unk4 = rd_u32(f)
        compression = rd_u16(f)
        width = rd_u16(f)
        height = rd_u16(f)
        xoff = struct.unpack('<h', f.read(2))[0]  # signed
        yoff = struct.unpack('<h', f.read(2))[0]

        # Row offsets table starts here
        row_table_start = f.tell()
        # Pentagram "unfudge": stored offsets are relative, and we subtract (height - i) * 2
        # Then row data actual start = row_table_start + 2*height + unfudged
        row_offsets_unf = []
        for i in range(height):
            rel = rd_u16(f)
            unf = rel - (height - i) * 2
            if unf < 0:
                # fallback to non-unfudged if this looks wrong
                unf = rel
            row_offsets_unf.append(unf)

        row_data_base = row_table_start + 2 * height

        # Build RGBA image
        img = Image.new('RGBA', (max(1, width), max(1, height)))
        px = img.load()

        # Decode rows
        for y in range(height):
            row_pos = row_data_base + row_offsets_unf[y]
            if row_pos < 0 or row_pos >= len(shape_blob):
                continue
            f.seek(row_pos)
            xpos = 0
            # Loop until row filled
            while xpos < width:
                skip = rd_u8(f)
                xpos += skip
                if xpos >= width:
                    break
                dlen = rd_u8(f)
                if compression == 1:
                    rtype = dlen & 1
                    dcount = dlen >> 1
                    if rtype == 0:
                        # literal run
                        for _ in range(dcount):
                            if xpos >= width:
                                break
                            col = rd_u8(f)
                            rgba = self.palette[col]
                            px[xpos, y] = rgba
                            xpos += 1
                    else:
                        # repeat run
                        col = rd_u8(f)
                        rgba = self.palette[col]
                        for _ in range(dcount):
                            if xpos >= width:
                                break
                            px[xpos, y] = rgba
                            xpos += 1
                else:
                    # uncompressed: dlen literal bytes
                    for _ in range(dlen):
                        if xpos >= width:
                            break
                        col = rd_u8(f)
                        rgba = self.palette[col]
                        px[xpos, y] = rgba
                        xpos += 1

        return U8Frame(width, height, xoff, yoff, img)

    def get_frame(self, shape_index: int, frame_index: int) -> Optional[U8Frame]:
        key = (shape_index, frame_index)
        if key in self.cache:
            return self.cache[key]

        blob = self.flx.get_record(shape_index)
        if not blob:
            return None
        f = io.BytesIO(blob)
        if len(blob) < 6:
            return None

        # Shape header: 0..1?, 2..3?, 4..5=frame count
        f.seek(4)
        frame_count = rd_u16(f)
        if frame_index < 0 or frame_index >= frame_count:
            return None

        # Read frame headers
        frames: List[Tuple[int, int]] = []  # (offset, size)
        f.seek(6)
        for _ in range(frame_count):
            off = rd_u24(f)
            _unknown = rd_u8(f)
            size = rd_u16(f)
            frames.append((off, size))

        off, size = frames[frame_index]
        fr = self._decode_frame(blob, off, size)
        self.cache[key] = fr
        return fr


# ---------- Map and glob ----------

@dataclass
class MapObj:
    x: int
    y: int
    z: int
    shape: int
    frame: int

class GlobArchive:
    def __init__(self, path: Path):
        self.flx = FlexArchive(path)

    def expand(self, baseX: int, baseY: int, baseZ: int, glob_idx: int) -> List[MapObj]:
        blob = self.flx.get_record(glob_idx)
        if not blob:
            return []
        f = io.BytesIO(blob)
        count = rd_u16(f)
        out: List[MapObj] = []
        for _ in range(count):
            gx = rd_u8(f)
            gy = rd_u8(f)
            gz = rd_u8(f)
            shape = rd_u16(f)
            frame = rd_u8(f)
            wx = baseX + 2 * gx
            wy = baseY + 2 * gy
            wz = baseZ + gz
            out.append(MapObj(wx, wy, wz, shape, frame))
        return out


def read_map_record(blob: bytes) -> List[MapObj]:
    """
    16 bytes per object:
      0 u16 X
      2 u16 Y
      4 u8  Z
      5 u16 ShapeIndex
      7 u8  FrameIndex
      8 u16 Flags
     10 u16 Quality (or Glob index if shape==2)
     12 u8  NpcIndex
     13 u8  MapIndex
     14 u16 NextId
    """
    objs: List[MapObj] = []
    n = len(blob) // 16
    f = io.BytesIO(blob)
    for _ in range(n):
        x = rd_u16(f)
        y = rd_u16(f)
        z = rd_u8(f)
        shape = rd_u16(f)
        frame = rd_u8(f)
        _flags = rd_u16(f)
        quality = rd_u16(f)
        _npc = rd_u8(f)
        _map = rd_u8(f)
        _next = rd_u16(f)
        objs.append(MapObj(x, y, z, shape, frame))
        # We keep quality available by returning separate list if needed
        # For glob we will handle in renderer, because we must mix-glob with normal objs
        objs[-1].quality = quality  # type: ignore
    return objs


# ---------- Renderer ----------

def project_to_screen(x: int, y: int, z: int) -> Tuple[int, int]:
    sx = (x - y) // 4
    sy = (x + y) // 8 - z
    return sx, sy

def render_map_to_image(
    fixed_flex: FlexArchive,
    nonfixed_flex: Optional[FlexArchive],
    map_idx: int,
    shapes: ShapeArchive,
    globs: GlobArchive,
    glob_y_bias_minus_576: bool,
    cull_margin: Optional[Tuple[int,int,int,int]] = None,
) -> Image.Image:
    # collect objects from fixed and (optionally) nonfixed
    objs: List[MapObj] = []
    blob = fixed_flex.get_record(map_idx)
    if blob:
        objs.extend(read_map_record(blob))
    if nonfixed_flex:
        nb = nonfixed_flex.get_record(map_idx)
        if nb:
            objs.extend(read_map_record(nb))

    # Expand globs (shape==2, quality is glob index)
    expanded: List[MapObj] = []
    for o in objs:
        if o.shape == 2:
            gidx = getattr(o, 'quality', 0)  # type: ignore
            if glob_y_bias_minus_576:
                # This toggle mimics the old doc fudge; we bias Y before expanding.
                expanded.extend(
                    [MapObj(x=oo.x, y=oo.y - 576, z=oo.z, shape=oo.shape, frame=oo.frame)
                     for oo in globs.expand(o.x, o.y, o.z, gidx)]
                )
            else:
                expanded.extend(globs.expand(o.x, o.y, o.z, gidx))
        else:
            expanded.append(o)

    # Determine bounds and build draw list with screen coords
    draw_list = []
    minx = miny =  10**9
    maxx = maxy = -10**9

    for o in expanded:
        fr = shapes.get_frame(o.shape, o.frame)
        if not fr:
            continue
        sx, sy = project_to_screen(o.x, o.y, o.z)
        # Anchor: subtract hotspot offsets
        sx -= fr.xoff
        sy -= fr.yoff

        # bounds
        minx = min(minx, sx)
        miny = min(miny, sy)
        maxx = max(maxx, sx + fr.width)
        maxy = max(maxy, sy + fr.height)

        draw_list.append((o.x + o.y, o.z, o.x, sx, sy, fr))

    if not draw_list:
        return Image.new('RGBA', (1, 1), (0, 0, 0, 0))

    # Optional culling by screen bbox (before allocating big image)
    if cull_margin is not None:
        left, top, right, bottom = cull_margin
        draw_list = [d for d in draw_list if not (
            d[3] > right or d[4] > bottom or
            d[3] + d[5].width < left or d[4] + d[5].height < top
        )]
        if not draw_list:
            return Image.new('RGBA', (1, 1), (0, 0, 0, 0))

    # normalize
    ox = -minx
    oy = -miny
    W = max(1, maxx - minx)
    H = max(1, maxy - miny)
    out = Image.new('RGBA', (W, H), (0,0,0,0))

    # z-order: (X+Y, Z, X)
    draw_list.sort(key=lambda t: (t[0], t[1], t[2]))

    for _, _, _, sx, sy, fr in draw_list:
        out.alpha_composite(fr.rgba, dest=(sx + ox, sy + oy))

    return out


# ---------- Tk app ----------

class MapViewerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Ultima 8 Map Viewer (Pentagram-accurate decoding)")
        self.geometry("1200x800")

        # State
        self.game_dir: Optional[Path] = None
        self.fixed: Optional[FlexArchive] = None
        self.nonfixed: Optional[FlexArchive] = None
        self.glob: Optional[GlobArchive] = None
        self.shapes: Optional[ShapeArchive] = None
        self.palette: Optional[List[Tuple[int,int,int,int]]] = None

        self.map_idx = 0
        self.use_nonfixed = tk.BooleanVar(value=True)
        self.glob_y_bias_toggle = tk.BooleanVar(value=False)
        self.cull_toggle = tk.BooleanVar(value=True)

        # Canvas + controls
        self._build_ui()

        # View transform
        self.base_image: Optional[Image.Image] = None
        self.display_image: Optional[ImageTk.PhotoImage] = None
        self.zoom = 1.0
        self.pan_x = 0
        self.pan_y = 0

        # Bindings
        self.bind("<MouseWheel>", self.on_wheel)          # Windows/mac (delta signs differ)
        self.bind("<Button-4>", self.on_wheel)            # X11 up
        self.bind("<Button-5>", self.on_wheel)            # X11 down
        self.canvas.bind("<ButtonPress-3>", self.on_pan_start)
        self.canvas.bind("<B3-Motion>", self.on_pan_drag)
        self.bind("<Key>", self.on_key)

    def _build_ui(self):
        top = ttk.Frame(self, padding=6)
        top.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(top, text="Game folder:").pack(side=tk.LEFT)
        self.folder_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.folder_var, width=60).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Browse…", command=self.choose_folder).pack(side=tk.LEFT)
        ttk.Button(top, text="Load Data", command=self.load_game).pack(side=tk.LEFT, padx=6)

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=4)

        toolbar = ttk.Frame(self, padding=6)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(toolbar, text="Map:").pack(side=tk.LEFT)
        self.map_var = tk.IntVar(value=0)
        self.map_spin = ttk.Spinbox(toolbar, from_=0, to=255, textvariable=self.map_var, width=5, command=self.render_map)
        self.map_spin.pack(side=tk.LEFT, padx=4)

        ttk.Checkbutton(toolbar, text="Use NONFIXED.DAT", variable=self.use_nonfixed, command=self.render_map).pack(side=tk.LEFT, padx=8)
        ttk.Checkbutton(toolbar, text="Apply -576 glob Y-bias (old docs hack)", variable=self.glob_y_bias_toggle, command=self.render_map).pack(side=tk.LEFT, padx=8)
        ttk.Checkbutton(toolbar, text="Cull offscreen before render", variable=self.cull_toggle, command=self.render_map).pack(side=tk.LEFT, padx=8)

        ttk.Button(toolbar, text="Render", command=self.render_map).pack(side=tk.LEFT, padx=10)
        ttk.Button(toolbar, text="Reset View (R)", command=self.reset_view).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Export PNG…", command=self.export_png).pack(side=tk.LEFT, padx=6)

        self.status = ttk.Label(self, text="Ready")
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

        self.canvas = tk.Canvas(self, bg="#000000")
        self.canvas.pack(fill=tk.BOTH, expand=True)

    # -------- I/O --------

    def choose_folder(self):
        d = filedialog.askdirectory(title="Select Ultima 8 game folder (contains static/ and gamedat/)")
        if not d:
            return
        self.game_dir = Path(d)
        self.folder_var.set(str(self.game_dir))

    def load_game(self):
        if not self.game_dir:
            messagebox.showerror("Error", "Pick your Ultima 8 folder first.")
            return
        static = self.game_dir / "static"
        gamedat = self.game_dir / "gamedat"
        try:
            pal = load_palette(static / "U8PAL.PAL")
            self.palette = pal
            self.shapes = ShapeArchive(static / "U8SHAPES.FLX", pal)
            self.fixed = FlexArchive(static / "FIXED.DAT")
            self.glob = GlobArchive(static / "GLOB.FLX")
            if (gamedat / "NONFIXED.DAT").exists():
                self.nonfixed = FlexArchive(gamedat / "NONFIXED.DAT")
            else:
                self.nonfixed = None
        except Exception as e:
            messagebox.showerror("Load error", f"Failed to load data:\n{e}")
            return
        self.status.config(text="Loaded. Choose a map and click Render.")
        self.focus_set()

    # -------- Render --------

    def render_map(self):
        if not (self.fixed and self.shapes and self.glob):
            messagebox.showerror("Error", "Load data first.")
            return
        self.map_idx = max(0, min(255, int(self.map_var.get())))
        use_nonfixed = self.use_nonfixed.get()
        cull = self.cull_toggle.get()
        cull_box = None
        if cull:
            # approximate cull window from current view (inverse transform)
            w = max(1, self.canvas.winfo_width())
            h = max(1, self.canvas.winfo_height())
            # map canvas window to image coords
            if self.zoom <= 0:
                self.zoom = 1.0
            left = int(-self.pan_x / self.zoom) - 128
            top = int(-self.pan_y / self.zoom) - 128
            right = int((w - self.pan_x) / self.zoom) + 128
            bottom = int((h - self.pan_y) / self.zoom) + 128
            cull_box = (left, top, right, bottom)

        try:
            img = render_map_to_image(
                fixed_flex=self.fixed,
                nonfixed_flex=self.nonfixed if use_nonfixed else None,
                map_idx=self.map_idx,
                shapes=self.shapes,
                globs=self.glob,
                glob_y_bias_minus_576=self.glob_y_bias_toggle.get(),
                cull_margin=cull_box,
            )
        except Exception as e:
            messagebox.showerror("Render error", f"{e}")
            return

        self.base_image = img
        self.zoom = 1.0
        self.pan_x = self.pan_y = 0
        self.update_canvas_image()
        self.status.config(text=f"Rendered map {self.map_idx} — {img.width}×{img.height}px")

    def update_canvas_image(self):
        if not self.base_image:
            return
        # scale via PIL
        if self.zoom != 1.0:
            w = max(1, int(self.base_image.width * self.zoom))
            h = max(1, int(self.base_image.height * self.zoom))
            disp = self.base_image.resize((w, h), resample=Image.NEAREST)
        else:
            disp = self.base_image

        self.display_image = ImageTk.PhotoImage(disp)
        self.canvas.delete("all")
        # draw anchored at (pan_x, pan_y)
        self.canvas.create_image(self.pan_x, self.pan_y, anchor='nw', image=self.display_image)

    # -------- Controls --------

    def on_wheel(self, event):
        if not self.base_image:
            return
        # Normalize delta across platforms
        delta = 0
        if hasattr(event, "delta") and event.delta:
            delta = event.delta
        elif event.num == 4:
            delta = 120
        elif event.num == 5:
            delta = -120

        if delta == 0:
            return

        # Zoom factor
        factor = 1.0 + (0.1 if delta > 0 else -0.1)
        old_zoom = self.zoom
        new_zoom = max(0.1, min(8.0, self.zoom * factor))
        if abs(new_zoom - old_zoom) < 1e-6:
            return

        # Zoom around cursor
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        self.pan_x = cx - (cx - self.pan_x) * (new_zoom / old_zoom)
        self.pan_y = cy - (cy - self.pan_y) * (new_zoom / old_zoom)
        self.zoom = new_zoom
        self.update_canvas_image()

    def on_pan_start(self, event):
        self._pstart = (event.x, event.y)

    def on_pan_drag(self, event):
        if not hasattr(self, "_pstart"):
            return
        dx = event.x - self._pstart[0]
        dy = event.y - self._pstart[1]
        self._pstart = (event.x, event.y)
        self.pan_x += dx
        self.pan_y += dy
        self.update_canvas_image()

    def on_key(self, event):
        if event.char.lower() == 'r':
            self.reset_view()
            return
        step = 40
        if event.state & 0x0001:  # Shift
            step = 120
        if event.keysym == "Left":
            self.pan_x += step
        elif event.keysym == "Right":
            self.pan_x -= step
        elif event.keysym == "Up":
            self.pan_y += step
        elif event.keysym == "Down":
            self.pan_y -= step
        else:
            return
        self.update_canvas_image()

    def reset_view(self):
        self.zoom = 1.0
        self.pan_x = self.pan_y = 0
        self.update_canvas_image()

    # -------- Export --------

    def export_png(self):
        if not self.base_image:
            messagebox.showinfo("Export", "Render a map first.")
            return
        fn = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG", "*.png")],
            title="Export current map as PNG"
        )
        if not fn:
            return
        try:
            self.base_image.save(fn)
        except Exception as e:
            messagebox.showerror("Export failed", str(e))
            return
        self.status.config(text=f"Saved {fn}")


if __name__ == "__main__":
    app = MapViewerApp()
    app.mainloop()
