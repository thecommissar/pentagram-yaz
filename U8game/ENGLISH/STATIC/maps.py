# map_viewer.py
# Ultima VIII Map Viewer with GLOB expansion, Z-slice, dynamic UI layout.
# Place this next to U8PAL.PAL and U8SHAPES.FLX inside STATIC.

import os
import pygame
from collections import namedtuple

# ---------- binary helpers ----------
def ru8(f):  b=f.read(1);  if not b: raise EOFError; return b[0]
def ru16(f, signed=False):
    b=f.read(2);  if len(b)!=2: raise EOFError; return int.from_bytes(b,"little",signed=signed)
def ru24(f):
    b=f.read(3);  if len(b)!=3: raise EOFError; return b[0]|(b[1]<<8)|(b[2]<<16)
def ru32(f):
    b=f.read(4);  if len(b)!=4: raise EOFError; return int.from_bytes(b,"little")

# ---------- palette ----------
def load_palette(path):
    with open(path,"rb") as f:
        f.read(4)  # unknown
        raw=f.read(256*3)
    if len(raw)!=256*3: raise ValueError("U8PAL.PAL too short")
    pal=[]
    for i in range(256):
        r=raw[i*3+0]*4; g=raw[i*3+1]*4; b=raw[i*3+2]*4
        pal.append((min(r,255),min(g,255),min(b,255)))
    return pal

# ---------- shapes (U8SHAPES.FLX) ----------
class ShapeFrameInfo:
    __slots__=("pos","size")
    def __init__(self,pos,size): self.pos=pos; self.size=size

class ShapeTypeInfo:
    __slots__=("pos","size","frames")
    def __init__(self,pos,size,frames): self.pos=pos; self.size=size; self.frames=frames

class U8Shapes:
    def __init__(self, path):
        self.f = open(path,"rb")
        self.num_types = self._read_num_types()
        self.type_index = [None]*self.num_types
        self.frame_counts = self._read_frame_counts()

    def close(self):
        try: self.f.close()
        except: pass

    def _read_num_types(self):
        self.f.seek(0x54);  # 84
        return ru16(self.f)

    def _type_record(self, idx):
        self.f.seek(0x80 + idx*8)  # 128
        pos = ru32(self.f); size = ru32(self.f)
        return pos, size

    def _read_type(self, idx):
        if self.type_index[idx] is not None: return self.type_index[idx]
        tpos, tsize = self._type_record(idx)
        self.f.seek(tpos)
        self.f.read(4)   # unknown
        fcount = ru16(self.f)
        frames=[]
        for _ in range(fcount):
            rel = ru24(self.f)
            self.f.read(1)  # unknown
            fsz = ru16(self.f)
            frames.append(ShapeFrameInfo(tpos+rel, fsz))
        info = ShapeTypeInfo(tpos, tsize, frames)
        self.type_index[idx]=info
        return info

    def _read_frame_counts(self):
        counts=[0]*self.num_types
        for i in range(self.num_types):
            tpos,_=self._type_record(i)
            self.f.seek(tpos)
            self.f.read(4)
            counts[i]=ru16(self.f)
        return counts

    def frame_info(self, type_idx, frame_idx):
        t=self._read_type(type_idx)
        if not (0<=frame_idx<len(t.frames)): raise IndexError
        return t.frames[frame_idx]

def decode_frame_surface_vb_exact(f, finfo, palette):
    # VB-accurate decode from u8gfxfmt.txt / u8view.bas
    f.seek(finfo.pos)
    f.read(2)  # typenum
    f.read(2)  # framenum
    f.read(4)  # unknown
    compr = ru16(f)
    xlen  = ru16(f)
    ylen  = ru16(f)
    xoff  = ru16(f, signed=True)
    yoff  = ru16(f, signed=True)

    line_pos=[]
    for _ in range(ylen):
        base=f.tell()
        delta=ru16(f)
        line_pos.append(base+delta)

    surf = pygame.Surface((max(1,xlen), max(1,ylen)), pygame.SRCALPHA, 32)

    xpos = xlen; y = -1
    while True:
        while xpos >= xlen:
            y += 1
            if y >= ylen: return surf, xoff, yoff
            f.seek(line_pos[y])
            xpos = ru8(f)

        dlen = ru8(f)
        if compr==1:
            if (dlen & 1)==1:
                run = dlen//2
                color = ru8(f)
                if run>0:
                    clr = palette[color]
                    for i in range(run):
                        px = xpos+i
                        if 0<=px<xlen: surf.set_at((px,y),(clr[0],clr[1],clr[2],255))
            else:
                run = dlen//2
                for i in range(run):
                    color = ru8(f)
                    px = xpos+i
                    if 0<=px<xlen:
                        clr=palette[color]
                        surf.set_at((px,y),(clr[0],clr[1],clr[2],255))
        else:
            run = dlen
            for i in range(run):
                color = ru8(f)
                px = xpos+i
                if 0<=px<xlen:
                    clr=palette[color]
                    surf.set_at((px,y),(clr[0],clr[1],clr[2],255))
        xpos += run
        if xpos < xlen:
            gap = ru8(f)
            xpos += gap

# ---------- FLX archive reader for maps & globs ----------
class FLX:
    def __init__(self, path):
        self.path = path
        self.f = open(path,"rb")
        self.count = self._read_count()
        self.records = self._read_records()

    def close(self):
        try: self.f.close()
        except: pass

    def _read_count(self):
        self.f.seek(0x54)
        return ru32(self.f)

    def _read_records(self):
        recs=[]
        base=0x90
        for i in range(self.count):
            self.f.seek(base+i*8)
            off=ru32(self.f); length=ru32(self.f)
            recs.append((off,length))
        return recs

    def read(self, idx):
        off, ln = self.records[idx]
        if off==0 or ln==0: return b""
        self.f.seek(off)
        return self.f.read(ln)

# ---------- map archives ----------
MapObject = namedtuple("MapObject","x y z shape frame flags quality npc mapid nextid")

class MapArchive(FLX):
    def read_map(self, idx):
        off, ln = self.records[idx]
        for try_off in (off, off+1):
            try:
                self.f.seek(try_off)
                data=self.f.read(ln)
                if len(data)!=ln or ln%16!=0: continue
                objs=[]
                p=0
                for _ in range(ln//16):
                    x=int.from_bytes(data[p+0:p+2],"little")
                    y=int.from_bytes(data[p+2:p+4],"little")
                    z=data[p+4]
                    shape=int.from_bytes(data[p+5:p+7],"little")
                    frame=data[p+7]
                    flags=int.from_bytes(data[p+8:p+10],"little")
                    quality=int.from_bytes(data[p+10:p+12],"little")
                    npc=data[p+12]; mapid=data[p+13]
                    nextid=int.from_bytes(data[p+14:p+16],"little")
                    objs.append(MapObject(x,y,z,shape,frame,flags,quality,npc,mapid,nextid))
                    p+=16
                return objs, try_off
            except Exception:
                continue
        return [], None

# ---------- globs (GLOB.FLX) ----------
GlobObj = namedtuple("GlobObj","dx dy dz shape frame")

class GlobArchive(FLX):
    def __init__(self, path):
        super().__init__(path)
        self.cache = {}

    def get(self, idx):
        if idx in self.cache: return self.cache[idx]
        data = self.read(idx)
        if not data: self.cache[idx]=[]; return []
        n = int.from_bytes(data[0:2],"little")
        g=[]
        p=2
        for _ in range(n):
            dx=data[p]; dy=data[p+1]; dz=data[p+2]
            shape=int.from_bytes(data[p+3:p+5],"little")
            frame=data[p+5]
            g.append(GlobObj(dx,dy,dz,shape,frame))
            p+=6
        self.cache[idx]=g
        return g

# ---------- rendering helpers ----------
class ShapeCache:
    def __init__(self, shapes, palette):
        self.shapes=shapes; self.palette=palette; self.cache={}
    def get(self, shape, frame):
        k=(shape,frame)
        if k in self.cache: return self.cache[k]
        if not (0<=shape<self.shapes.num_types): raise IndexError
        fcount=self.shapes.frame_counts[shape]
        if fcount==0: raise IndexError
        frame = min(frame, fcount-1)
        finfo=self.shapes.frame_info(shape, frame)
        surf,xoff,yoff = decode_frame_surface_vb_exact(self.shapes.f, finfo, self.palette)
        self.cache[k]=(surf,xoff,yoff)
        return surf,xoff,yoff

def world_to_screen(x,y,z):
    # S=4 for regular objects (globs are expanded to regular coords)
    sx = (x - y) // 4
    sy = ((x + y) // 8) - z
    return sx, sy

# ---------- simple UI ----------
class Button:
    def __init__(self, rect, label): self.rect=pygame.Rect(rect); self.label=label
    def draw(self, surf, font, enabled=True):
        bg=(36,36,36) if enabled else (18,18,18)
        fg=(230,230,230) if enabled else (130,130,130)
        pygame.draw.rect(surf,bg,self.rect,border_radius=6)
        pygame.draw.rect(surf,(90,90,90),self.rect,1,border_radius=6)
        surf.blit(font.render(self.label,True,fg), font.render(self.label,True,fg).get_rect(center=self.rect.center))
    def hit(self,pos): return self.rect.collidepoint(pos)

def layout_buttons(panel_w, start_y):
    # 2 columns: 20..(20+130) and 170..(170+130); rows 36 high, 12 v-gap
    r=[]
    y=start_y
    def row(a,b):
        r.append(Button((20,y,130,36),a))
        r.append(Button((170,y,130,36),b))
    row("Map −","Map +");              y+=48
    row("Zoom −","Zoom +");            y+=48
    r.append(Button((20,y,280,36),"Fit to Map (F)"));     y+=48
    r.append(Button((20,y,280,36),"Reset View (R)"));     y+=48
    row("Fixed ✓","Nonfixed ✓");       y+=48
    r.append(Button((20,y,280,36),"Globs ✓"));            y+=48
    row("Z −","Z +");                  y+=48
    r.append(Button((20,y,280,36),"Z Filter: All"));      y+=48
    return r, y

def draw_panel(surf, font, lines, buttons):
    surf.fill((12,12,12))
    y=10
    for s in lines:
        surf.blit(font.render(s,True,(210,210,210)), (12,y))
        y+=20
    # place buttons under text area
    # (their rects are updated before draw elsewhere)

    for b in buttons:
        b.draw(surf, font, True)

# ---------- app ----------
def main():
    base_static = os.getcwd()
    base_root   = os.path.dirname(base_static)
    pal_path    = os.path.join(base_static,"U8PAL.PAL")
    shapes_path = os.path.join(base_static,"U8SHAPES.FLX")
    fixed_path  = os.path.join(base_static,"FIXED.DAT")
    nonfixed_path = os.path.join(base_root,"GAMEDAT","NONFIXED.DAT")
    glob_path_candidates = [os.path.join(base_static,"GLOB.FLX"),
                            os.path.join(base_static,"glob.flx")]

    pygame.init()
    pygame.display.set_caption("Ultima VIII Map Viewer")
    font = pygame.font.SysFont("consolas,menlo,monospace",16)

    view_w, view_h = 960, 720
    panel_w = 320
    win = pygame.display.set_mode((view_w+panel_w, view_h))
    panel = pygame.Surface((panel_w, view_h))

    # data
    palette = load_palette(pal_path)
    shapes  = U8Shapes(shapes_path)
    cache   = ShapeCache(shapes, palette)
    fixed = MapArchive(fixed_path) if os.path.exists(fixed_path) else None
    nonfixed = MapArchive(nonfixed_path) if os.path.exists(nonfixed_path) else None

    glob = None
    for gp in glob_path_candidates:
        if os.path.exists(gp):
            try:
                glob = GlobArchive(gp)
                break
            except Exception:
                pass

    # state
    show_fixed=True; show_nonfixed=True; use_globs=True
    map_index=0
    zoom_levels=[0.25,0.5,1.0,2.0,3.0]
    zoom_idx=2  # 1.0x
    cam_x=cam_y=0
    status_msg=""
    used_offsets={"fixed":None,"nonfixed":None}

    # Z filter
    z_filter_on=False
    z_ceil=64  # default “interior slice”
    def z_ok(z): return (not z_filter_on) or (z<=z_ceil)

    # dynamic buttons (positions filled at draw time)
    buttons,_=layout_buttons(panel_w, 0)
    (btn_map_minus, btn_map_plus,
     btn_zoom_minus, btn_zoom_plus,
     btn_fit, btn_reset,
     btn_fixed, btn_nonfixed,
     btn_globs,
     btn_z_minus, btn_z_plus,
     btn_z_toggle) = buttons

    # helpers -------------------------------------------------
    def get_zoom(): return zoom_levels[zoom_idx]

    def load_map(idx):
        nonlocal used_offsets
        used_offsets={"fixed":None,"nonfixed":None}
        fobjs=[]; nobjs=[]
        if show_fixed and fixed:
            fobjs, off = fixed.read_map(idx); used_offsets["fixed"]=off
        if show_nonfixed and nonfixed:
            nobjs, off = nonfixed.read_map(idx); used_offsets["nonfixed"]=off
        return fobjs, nobjs

    fixed_objs, nonfixed_objs = load_map(map_index)

    def expand_globs(objs):
        if not (use_globs and glob): return []
        out=[]
        for o in objs:
            if o.shape==2 and o.quality>0:  # glob entry
                g = glob.get(o.quality)
                for go in g:
                    # Convert per docs:
                    mx = go.dx*2 + o.x
                    my = go.dy*2 + o.y - 576
                    mz = go.dz + o.z
                    out.append(MapObject(mx,my,mz,go.shape,go.frame,0,0,0,0,0))
        return out

    def current_objects():
        base=[]
        if show_fixed:    base.extend(fixed_objs)
        if show_nonfixed: base.extend(nonfixed_objs)
        # expand globs into real drawables
        base.extend(expand_globs(base))
        # Z filter
        return [o for o in base if z_ok(o.z)]

    def sort_key(o): return (o.x + o.y, o.z, o.x)

    def compute_bounds_at_zoom1():
        objs=current_objects()
        if not objs: return None
        first=True
        minx=miny=maxx=maxy=0
        for o in objs:
            try:
                surf,xoff,yoff = cache.get(o.shape,o.frame)
            except Exception:
                continue
            sx,sy = world_to_screen(o.x,o.y,o.z)
            dx,dy = sx-xoff, sy-yoff
            w,h = surf.get_width(), surf.get_height()
            if first:
                minx, miny, maxx, maxy = dx, dy, dx+w, dy+h
                first=False
            else:
                if dx<minx: minx=dx
                if dy<miny: miny=dy
                if dx+w>maxx: maxx=dx+w
                if dy+h>maxy: maxy=dy+h
        if first: return None
        return (minx,miny,maxx,maxy)

    def fit_to_map():
        nonlocal cam_x,cam_y,zoom_idx,status_msg
        b=compute_bounds_at_zoom1()
        if not b: status_msg="Nothing to fit."; return
        minx,miny,maxx,maxy=b
        w=maxx-minx; h=maxy-miny
        if w<=0 or h<=0: status_msg="Degenerate bounds."; return
        z_des = min(view_w/w, view_h/h)
        # choose <= desired
        levels = zoom_levels
        best=0
        for i,z in enumerate(levels):
            if z<=z_des: best=i
            else: break
        zoom_idx=best
        z=levels[zoom_idx]
        cx=(minx+maxx)/2; cy=(miny+maxy)/2
        cam_x=int(-cx*z); cam_y=int(-cy*z)
        status_msg=f"Fit: zoom={z:.2f}x"

    def reset_view():
        nonlocal cam_x,cam_y,zoom_idx,status_msg
        cam_x=cam_y=0; zoom_idx=2; status_msg="View reset."

    # drawing ------------------------------------------------
    def redraw():
        nonlocal status_msg
        win.fill((0,0,0))
        z = get_zoom()
        # dynamic layout: compute info text then position buttons below it
        info = [
            "Ultima VIII Map Viewer",
            f"Map: {map_index}  (0..255)",
            f"Objects: fixed={len(fixed_objs) if show_fixed else 0}"
            f"  nonfixed={len(nonfixed_objs) if show_nonfixed else 0}",
            f"Shapes decoded (cached): {len(cache.cache)}",
            f"Zoom: {z:.2f}x    Camera: ({cam_x},{cam_y})",
            f"Globs: {'ON' if use_globs and glob else 'OFF'}   "
            f"Z filter: {'All' if not z_filter_on else '≤ '+str(z_ceil)}",
            "Offsets (debug): "
            f"  FIXED: " + (str(used_offsets['fixed']) if used_offsets['fixed'] else "-") + 
            "   NONFIXED: " + (str(used_offsets['nonfixed']) if used_offsets['nonfixed'] else "-"),
            status_msg or ""
        ]
        # position buttons below text
        text_height = 10 + 20*len(info) + 10
        # regenerate button rectangles
        y=text_height
        # 2 columns helper
        def place_row(b1,b2):
            b1.rect.topleft=(20,y); b1.rect.size=(130,36)
            b2.rect.topleft=(170,y); b2.rect.size=(130,36)
        place_row(btn_map_minus, btn_map_plus); y+=48
        place_row(btn_zoom_minus, btn_zoom_plus); y+=48
        btn_fit.rect.topleft=(20,y); btn_fit.rect.size=(280,36); y+=48
        btn_reset.rect.topleft=(20,y); btn_reset.rect.size=(280,36); y+=48
        place_row(btn_fixed, btn_nonfixed); y+=48
        btn_globs.rect.topleft=(20,y); btn_globs.rect.size=(280,36); y+=48
        place_row(btn_z_minus, btn_z_plus); y+=48
        btn_z_toggle.rect.topleft=(20,y); btn_z_toggle.rect.size=(280,36); y+=48

        # refresh button labels reflecting state
        btn_fixed.label   = "Fixed ✓" if show_fixed else "Fixed ✗"
        btn_nonfixed.label= "Nonfixed ✓" if show_nonfixed else "Nonfixed ✗"
        btn_globs.label   = "Globs ✓" if (use_globs and glob) else "Globs ✗"
        btn_z_toggle.label= "Z Filter: All" if not z_filter_on else f"Z Filter: ≤ {z_ceil}"

        # draw world
        view_rect = pygame.Rect(0,0,view_w,view_h)
        objs = sorted(current_objects(), key=sort_key)
        for o in objs:
            try:
                surf,xoff,yoff = cache.get(o.shape,o.frame)
            except Exception:
                continue
            sx,sy = world_to_screen(o.x,o.y,o.z)
            dx = (sx - xoff)*z + cam_x + view_w*0.5
            dy = (sy - yoff)*z + cam_y + view_h*0.5
            if z!=1.0:
                w=max(1,int(surf.get_width()*z)); h=max(1,int(surf.get_height()*z))
                scaled = pygame.transform.smoothscale(surf,(w,h))
                srect = scaled.get_rect(topleft=(int(dx),int(dy)))
                if srect.colliderect(view_rect): win.blit(scaled,srect.topleft)
            else:
                srect = surf.get_rect(topleft=(int(dx),int(dy)))
                if srect.colliderect(view_rect): win.blit(surf,srect.topleft)

        # draw panel
        panel = pygame.Surface((panel_w, view_h))
        draw_panel(panel, font, info, buttons)
        win.blit(panel, (view_w,0))
        pygame.display.flip()

    # util
    def step_zoom(d):
        nonlocal zoom_idx
        zoom_idx = max(0, min(len(zoom_levels)-1, zoom_idx + d))

    # initial draw
    redraw()

    # loop
    dragging=False; drag_start=(0,0); cam_start=(0,0)
    clock=pygame.time.Clock(); running=True
    while running:
        for ev in pygame.event.get():
            if ev.type==pygame.QUIT: running=False
            elif ev.type==pygame.KEYDOWN:
                if ev.key==pygame.K_ESCAPE: running=False
                elif ev.key==pygame.K_a:
                    map_index=max(0,map_index-1); fixed_objs,nonfixed_objs=load_map(map_index); redraw()
                elif ev.key==pygame.K_d:
                    map_index=min(255,map_index+1); fixed_objs,nonfixed_objs=load_map(map_index); redraw()
                elif ev.key in (pygame.K_EQUALS, pygame.K_PLUS): step_zoom(+1); redraw()
                elif ev.key==pygame.K_MINUS: step_zoom(-1); redraw()
                elif ev.key==pygame.K_f: fit_to_map(); redraw()
                elif ev.key==pygame.K_r: reset_view(); redraw()
                elif ev.key==pygame.K_LEFT: cam_x+=32; redraw()
                elif ev.key==pygame.K_RIGHT: cam_x-=32; redraw()
                elif ev.key==pygame.K_UP: cam_y+=32; redraw()
                elif ev.key==pygame.K_DOWN: cam_y-=32; redraw()
                elif ev.key==pygame.K_LEFTBRACKET: z_ceil=max(0,z_ceil-4); redraw()
                elif ev.key==pygame.K_RIGHTBRACKET: z_ceil=min(255,z_ceil+4); redraw()
                elif ev.key==pygame.K_BACKSLASH:
                    nonlocal_z = locals()  # silence linter
                    z_filter_on = not z_filter_on; redraw()
            elif ev.type==pygame.MOUSEBUTTONDOWN:
                mx,my=ev.pos
                if ev.button==1:
                    # click buttons (panel area)
                    if mx >= view_w:
                        p=(mx-view_w,my)
                        b=next((b for b in buttons if b.hit(p)), None)
                        if b is btn_map_minus:
                            map_index=max(0,map_index-1); fixed_objs,nonfixed_objs=load_map(map_index)
                        elif b is btn_map_plus:
                            map_index=min(255,map_index+1); fixed_objs,nonfixed_objs=load_map(map_index)
                        elif b is btn_zoom_minus: step_zoom(-1)
                        elif b is btn_zoom_plus: step_zoom(+1)
                        elif b is btn_fit: fit_to_map()
                        elif b is btn_reset: reset_view()
                        elif b is btn_fixed:
                            show_fixed=not show_fixed
                        elif b is btn_nonfixed:
                            show_nonfixed=not show_nonfixed
                        elif b is btn_globs:
                            # if no glob file, leave disabled
                            if glob: use_globs = not use_globs
                        elif b is btn_z_minus:
                            z_ceil=max(0,z_ceil-4)
                        elif b is btn_z_plus:
                            z_ceil=min(255,z_ceil+4)
                        elif b is btn_z_toggle:
                            nonlocal_z = locals()
                            z_filter_on = not z_filter_on
                        # reload because expanded set / filter may change
                        fixed_objs,nonfixed_objs = load_map(map_index)
                        redraw()
                elif ev.button==3:
                    dragging=True; drag_start=(mx,my); cam_start=(cam_x,cam_y)
                elif ev.button==4: step_zoom(+1); redraw()
                elif ev.button==5: step_zoom(-1); redraw()
            elif ev.type==pygame.MOUSEBUTTONUP and ev.button==3:
                dragging=False
            elif ev.type==pygame.MOUSEMOTION and dragging:
                mx,my=ev.pos
                cam_x = cam_start[0] + (mx - drag_start[0])
                cam_y = cam_start[1] + (my - drag_start[1])
                redraw()
        clock.tick(60)

    # cleanup
    if fixed: fixed.close()
    if nonfixed: nonfixed.close()
    if glob: glob.close()
    shapes.close()
    pygame.quit()

if __name__=="__main__":
    main()
