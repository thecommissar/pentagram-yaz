# viewer.py
# Ultima VIII shape viewer with an in-app GUI (faithful to u8view.bas).
# Place this in the STATIC folder alongside U8PAL.PAL and U8SHAPES.FLX.
# Requires: pygame

import os
import pygame

# -------------------- binary helpers --------------------

def ru8(f):
    b = f.read(1)
    if not b:
        raise EOFError("EOF reading u8")
    return b[0]

def ru16(f, signed=False):
    b = f.read(2)
    if len(b) != 2:
        raise EOFError("EOF reading u16")
    return int.from_bytes(b, "little", signed=signed)

def ru24(f):
    b = f.read(3)
    if len(b) != 3:
        raise EOFError("EOF reading u24")
    return b[0] | (b[1] << 8) | (b[2] << 16)

def ru32(f):
    b = f.read(4)
    if len(b) != 4:
        raise EOFError("EOF reading u32")
    return int.from_bytes(b, "little", signed=False)

# -------------------- palette --------------------

def load_palette(path):
    with open(path, "rb") as f:
        _unk4 = f.read(4)  # ignored
        raw = f.read(256 * 3)
        if len(raw) != 256*3:
            raise ValueError("Palette file too short")
        pal = []
        for i in range(256):
            r = raw[i*3+0] * 4
            g = raw[i*3+1] * 4
            b = raw[i*3+2] * 4
            pal.append((min(r,255), min(g,255), min(b,255)))
        return pal

# -------------------- FLX access --------------------

class ShapeFrameInfo:
    __slots__ = ("pos", "size")
    def __init__(self, pos, size):
        self.pos = pos
        self.size = size

class ShapeTypeInfo:
    __slots__ = ("pos", "size", "frames")
    def __init__(self, pos, size, frames):
        self.pos = pos
        self.size = size
        self.frames = frames

class U8Shapes:
    def __init__(self, flx_path):
        self.path = flx_path
        self.f = open(flx_path, "rb")
        self.num_types = self._read_num_types()
        self.type_index = [None] * self.num_types
        self.frame_counts = self._read_frame_counts_only()

    def close(self):
        try:
            self.f.close()
        except:
            pass

    def _read_num_types(self):
        self.f.seek(84, os.SEEK_SET)
        return ru16(self.f, signed=False)

    def _read_type_record(self, type_index):
        table_off = 128 + type_index * 8
        self.f.seek(table_off, os.SEEK_SET)
        type_pos = ru32(self.f)
        type_size = ru32(self.f)
        return type_pos, type_size

    def _read_type_info(self, type_index):
        if self.type_index[type_index] is not None:
            return self.type_index[type_index]
        type_pos, type_size = self._read_type_record(type_index)
        self.f.seek(type_pos, os.SEEK_SET)
        _unknown4 = self.f.read(4)   # ignored
        num_frames = ru16(self.f, signed=False)
        frames = []
        for _ in range(num_frames):
            rel = ru24(self.f)
            _unk1 = ru8(self.f)
            fsize = ru16(self.f, signed=False)
            frames.append(ShapeFrameInfo(type_pos + rel, fsize))
        ti = ShapeTypeInfo(type_pos, type_size, frames)
        self.type_index[type_index] = ti
        return ti

    def _read_frame_counts_only(self):
        counts = [0] * self.num_types
        for i in range(self.num_types):
            type_pos, _ = self._read_type_record(i)
            self.f.seek(type_pos, os.SEEK_SET)
            _unknown4 = self.f.read(4)
            num_frames = ru16(self.f, signed=False)
            counts[i] = num_frames
        return counts

    def get_frame_info(self, type_index, frame_index):
        ti = self._read_type_info(type_index)
        if not (0 <= frame_index < len(ti.frames)):
            raise IndexError("Frame index out of range")
        return ti.frames[frame_index]

# -------------------- exact VB frame draw --------------------

def draw_frame_vb_exact(f, frame_info, target_surface, palette):
    """
    Exact translation of u8view.bas frame decode/draw.

    Frame header:
      0  u16 TypNum  (ignored)
      2  u16 FrmNum  (ignored)
      4  4  unknown  (ignored)
      8  u16 Compr
     10  u16 XLen
     12  u16 YLen
     14  i16 XOff
     16  i16 YOff
     18  YLen * u16 line position deltas
           (absolute file offset = position_of_this_word + delta)
    """
    f.seek(frame_info.pos, os.SEEK_SET)

    _typnum = ru16(f)       # not used by VB viewer
    _frmnum = ru16(f)
    _unk4   = f.read(4)
    compr   = ru16(f)
    xlen    = ru16(f)
    ylen    = ru16(f)
    xoff    = ru16(f, signed=True)
    yoff    = ru16(f, signed=True)

    # Build absolute line offsets using *current* word position + delta
    line_offsets = []
    for _ in range(ylen):
        base = f.tell()
        delta = ru16(f)
        line_offsets.append(base + delta)

    # VB starting pos
    st_xpos = 160 - xoff
    st_ypos = 150 - yoff

    # Clear to color 0
    target_surface.fill(palette[0])

    xpos = xlen
    y = -1
    while True:
        # Advance to next line with valid StartX
        while xpos >= xlen:
            y += 1
            if y >= ylen:
                return  # all lines done
            f.seek(line_offsets[y], os.SEEK_SET)
            xpos = ru8(f)  # StartX

        datlen = ru8(f)

        if compr == 1:
            if (datlen & 1) == 1:
                # Repeat: len = datlen \ 2, one color byte
                run = datlen // 2
                color = ru8(f)
                if run > 0:
                    ypix = y + st_ypos
                    if 0 <= ypix < 200:
                        start = xpos + st_xpos
                        for i in range(run):
                            xpix = start + i
                            if 0 <= xpix < 320:
                                target_surface.set_at((xpix, ypix), palette[color])
            else:
                # Literal: len = datlen \ 2, then that many bytes
                run = datlen // 2
                if run > 0:
                    ypix = y + st_ypos
                    if 0 <= ypix < 200:
                        start = xpos + st_xpos
                        for i in range(run):
                            color = ru8(f)
                            xpix = start + i
                            if 0 <= xpix < 320:
                                target_surface.set_at((xpix, ypix), palette[color])
                    else:
                        # offscreen but still consume
                        _ = f.read(run)
        else:
            # Uncompressed: datlen literal pixels
            run = datlen
            if run > 0:
                ypix = y + st_ypos
                if 0 <= ypix < 200:
                    start = xpos + st_xpos
                    for i in range(run):
                        color = ru8(f)
                        xpix = start + i
                        if 0 <= xpix < 320:
                            target_surface.set_at((xpix, ypix), palette[color])
                else:
                    _ = f.read(run)

        # Step 4: advance by run length (already halved when compressed)
        xpos += run

        # Step 5: optional gap byte
        if xpos < xlen:
            gap = ru8(f)
            xpos += gap
        # when xpos == xlen, next loop iteration will advance to next line

# -------------------- GUI helpers --------------------

class Button:
    def __init__(self, rect, label):
        self.rect = pygame.Rect(rect)
        self.label = label

    def draw(self, surf, font, enabled=True):
        bg = (36,36,36) if enabled else (18,18,18)
        fg = (230,230,230) if enabled else (120,120,120)
        pygame.draw.rect(surf, bg, self.rect, border_radius=6)
        pygame.draw.rect(surf, (90,90,90), self.rect, 1, border_radius=6)
        txt = font.render(self.label, True, fg)
        surf.blit(txt, txt.get_rect(center=self.rect.center))

    def hit(self, pos):
        return self.rect.collidepoint(pos)

def draw_panel(surf, font, shape_idx, frame_idx, total_shapes, total_frames, status_msg):
    surf.fill((12,12,12))
    lines = [
        "U8 Shape Viewer",
        f"Shapes: {total_shapes}",
        f"Shape:  {shape_idx}",
        f"Frames in shape: {total_frames}",
        f"Frame:  {frame_idx}",
        "",
        "Controls:",
        "A/D = prev/next shape",
        "W/S = prev/next frame",
        "Home/End = first/last frame",
        "PgUp/PgDn = -/+ 10 shapes",
        "Wheel = frame, Shift+Wheel = shape",
        "",
        status_msg or ""
    ]
    y = 12
    for s in lines:
        surf.blit(font.render(s, True, (210,210,210)), (12, y))
        y += 20

# -------------------- app --------------------

def main():
    base = os.getcwd()
    pal_path = os.path.join(base, "U8PAL.PAL")
    flx_path = os.path.join(base, "U8SHAPES.FLX")

    pygame.init()
    pygame.display.set_caption("U8 Shape Viewer")
    font = pygame.font.SysFont("consolas,menlo,monospace", 16)

    left_w, left_h = 640, 400   # 2x scale of 320x200
    right_w = 280
    win = pygame.display.set_mode((left_w + right_w, left_h))
    left_view = pygame.Surface((left_w, left_h))
    game_buf = pygame.Surface((320, 200))
    panel = pygame.Surface((right_w, left_h))

    btns = {
        "shape_prev": Button((20, 240, 110, 36), "Shape −"),
        "shape_next": Button((150, 240, 110, 36), "Shape +"),
        "frame_prev": Button((20, 286, 110, 36), "Frame −"),
        "frame_next": Button((150, 286, 110, 36), "Frame +"),
        "first_frame": Button((20, 332, 110, 36), "First"),
        "last_frame":  Button((150, 332, 110, 36), "Last"),
    }

    try:
        palette = load_palette(pal_path)
    except Exception as e:
        print("Failed to load palette:", e)
        return

    try:
        shapes = U8Shapes(flx_path)
    except Exception as e:
        print("Failed to open U8SHAPES.FLX:", e)
        return

    total_shapes = shapes.num_types
    shape_idx = 5  # start where you asked
    frame_idx = 0
    status = ""

    clock = pygame.time.Clock()
    running = True

    def clamp_frame():
        nonlocal frame_idx
        total = shapes.frame_counts[shape_idx]
        if total <= 0:
            frame_idx = 0
        else:
            frame_idx = max(0, min(frame_idx, total - 1))
        return total

    def redraw():
        nonlocal status
        status = ""
        total = shapes.frame_counts[shape_idx]
        if total == 0:
            game_buf.fill(palette[0])
            status = f"Shape {shape_idx} has 0 frames."
            return
        try:
            finfo = shapes.get_frame_info(shape_idx, frame_idx)
            draw_frame_vb_exact(shapes.f, finfo, game_buf, palette)
        except Exception as e:
            game_buf.fill((64, 0, 0))
            status = f"Error: {e}"

    clamp_frame()
    redraw()

    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False

            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
                elif ev.key in (pygame.K_a, pygame.K_LEFT):
                    shape_idx = max(0, shape_idx - 1); clamp_frame(); redraw()
                elif ev.key in (pygame.K_d, pygame.K_RIGHT):
                    shape_idx = min(total_shapes - 1, shape_idx + 1); clamp_frame(); redraw()
                elif ev.key in (pygame.K_w, pygame.K_UP):
                    frame_idx -= 1; clamp_frame(); redraw()
                elif ev.key in (pygame.K_s, pygame.K_DOWN):
                    frame_idx += 1; clamp_frame(); redraw()
                elif ev.key == pygame.K_HOME:
                    frame_idx = 0; clamp_frame(); redraw()
                elif ev.key == pygame.K_END:
                    frame_idx = max(0, shapes.frame_counts[shape_idx] - 1); redraw()
                elif ev.key == pygame.K_PAGEUP:
                    shape_idx = max(0, shape_idx - 10); clamp_frame(); redraw()
                elif ev.key == pygame.K_PAGEDOWN:
                    shape_idx = min(total_shapes - 1, shape_idx + 10); clamp_frame(); redraw()

            elif ev.type == pygame.MOUSEBUTTONDOWN:
                mx, my = ev.pos
                # mouse wheel
                if ev.button in (4, 5):
                    mods = pygame.key.get_mods()
                    if mx < left_w:
                        if mods & pygame.KMOD_SHIFT:
                            if ev.button == 4:
                                shape_idx = max(0, shape_idx - 1)
                            else:
                                shape_idx = min(total_shapes - 1, shape_idx + 1)
                            clamp_frame(); redraw()
                        else:
                            if ev.button == 4:
                                frame_idx -= 1
                            else:
                                frame_idx += 1
                            clamp_frame(); redraw()
                    continue

                # clicks on panel buttons
                if mx >= left_w:
                    px, py = mx - left_w, my
                    for key, btn in btns.items():
                        if btn.hit((px, py)):
                            if key == "shape_prev":
                                shape_idx = max(0, shape_idx - 1)
                            elif key == "shape_next":
                                shape_idx = min(total_shapes - 1, shape_idx + 1)
                            elif key == "frame_prev":
                                frame_idx -= 1
                            elif key == "frame_next":
                                frame_idx += 1
                            elif key == "first_frame":
                                frame_idx = 0
                            elif key == "last_frame":
                                frame_idx = max(0, shapes.frame_counts[shape_idx] - 1)
                            clamp_frame(); redraw()
                            break

        # scale 2x and draw
        pygame.transform.scale(game_buf, (left_w, left_h), left_view)
        win.blit(left_view, (0, 0))

        draw_panel(panel, font, shape_idx, frame_idx, shapes.num_types,
                   shapes.frame_counts[shape_idx], status)
        for btn in btns.values():
            btn.draw(panel, font, enabled=True)
        win.blit(panel, (left_w, 0))

        pygame.display.flip()
        clock.tick(60)

    shapes.close()
    pygame.quit()

if __name__ == "__main__":
    main()
