import pygame
import struct
from pathlib import Path

class Button:
    def __init__(self, x, y, width, height, text, color=(100, 100, 100), hover_color=(150, 150, 150)):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.color = color
        self.hover_color = hover_color
        self.is_hovered = False
        self.font = pygame.font.Font(None, 24)
        
    def draw(self, surface):
        color = self.hover_color if self.is_hovered else self.color
        pygame.draw.rect(surface, color, self.rect)
        pygame.draw.rect(surface, (200, 200, 200), self.rect, 2)  # Border
        
        text_surface = self.font.render(self.text, True, (255, 255, 255))
        text_rect = text_surface.get_rect(center=self.rect.center)
        surface.blit(text_surface, text_rect)
        
    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.is_hovered = self.rect.collidepoint(event.pos)
            return False
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self.is_hovered:
                return True
        return False

class GUI:
    def __init__(self, viewer):
        self.viewer = viewer
        self.buttons = {
            'prev_shape': Button(10, 520, 100, 30, "Prev Shape"),
            'next_shape': Button(120, 520, 100, 30, "Next Shape"),
            'prev_frame': Button(230, 520, 100, 30, "Prev Frame"),
            'next_frame': Button(340, 520, 100, 30, "Next Frame"),
            'export': Button(450, 520, 100, 30, "Export"),
            'import': Button(560, 520, 100, 30, "Import"), # Added import button
            'export_all': Button(670, 520, 120, 30, "Export All"),
        }
        
        # Shape/frame input boxes
        self.input_font = pygame.font.Font(None, 24)
        self.shape_input_active = False
        self.frame_input_active = False
        self.shape_input = ""
        self.frame_input = ""
        self.shape_input_rect = pygame.Rect(10, 560, 60, 30)
        self.frame_input_rect = pygame.Rect(230, 560, 60, 30)
        
    def draw(self, surface):
        # Draw all buttons
        for button in self.buttons.values():
            button.draw(surface)
        
        # Draw input boxes
        color = (100, 100, 200) if self.shape_input_active else (100, 100, 100)
        pygame.draw.rect(surface, color, self.shape_input_rect, 2)
        
        color = (100, 100, 200) if self.frame_input_active else (100, 100, 100)
        pygame.draw.rect(surface, color, self.frame_input_rect, 2)
        
        # Draw input box content
        txt_surface = self.input_font.render(self.shape_input, True, (255, 255, 255))
        surface.blit(txt_surface, (self.shape_input_rect.x + 5, self.shape_input_rect.y + 5))
        
        txt_surface = self.input_font.render(self.frame_input, True, (255, 255, 255))
        surface.blit(txt_surface, (self.frame_input_rect.x + 5, self.frame_input_rect.y + 5))
        
        # Draw labels
        shape_label = self.input_font.render("Shape:", True, (255, 255, 255))
        frame_label = self.input_font.render("Frame:", True, (255, 255, 255))
        surface.blit(shape_label, (self.shape_input_rect.x - 60, self.shape_input_rect.y + 8))
        surface.blit(frame_label, (self.frame_input_rect.x - 60, self.frame_input_rect.y + 8))
        
    def handle_event(self, event):
        # Handle button events
        for button_name, button in self.buttons.items():
            if button.handle_event(event):
                return button_name
        
        # Handle input box events
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.shape_input_rect.collidepoint(event.pos):
                self.shape_input_active = True
                self.frame_input_active = False
            elif self.frame_input_rect.collidepoint(event.pos):
                self.shape_input_active = False
                self.frame_input_active = True
            else:
                self.shape_input_active = False
                self.frame_input_active = False
        
        elif event.type == pygame.KEYDOWN:
            if self.shape_input_active:
                if event.key == pygame.K_RETURN:
                    try:
                        return ('goto_shape', int(self.shape_input))
                    except ValueError:
                        pass
                elif event.key == pygame.K_BACKSPACE:
                    self.shape_input = self.shape_input[:-1]
                else:
                    if event.unicode.isnumeric():
                        self.shape_input += event.unicode
            
            elif self.frame_input_active:
                if event.key == pygame.K_RETURN:
                    try:
                        return ('goto_frame', int(self.frame_input))
                    except ValueError:
                        pass
                elif event.key == pygame.K_BACKSPACE:
                    self.frame_input = self.frame_input[:-1]
                else:
                    if event.unicode.isnumeric():
                        self.frame_input += event.unicode
        
        return None

class U8ShapeViewer:
    def __init__(self, shape_file: str, pal_file: str):
        # Match BASIC arrays
        self.typ_pos = [0] * 2048  # DIM TypPos(0 TO 2047) AS LONG
        self.typ_siz = [0] * 2048  # DIM TypSiz(0 TO 2047) AS LONG
        self.frm_pos = [0] * 1550  # DIM FrmPos(0 TO 1549) AS LONG
        self.frm_siz = [0] * 1550  # DIM FrmSiz(0 TO 1549) AS LONG
        self.lin_pos = [0] * 200   # DIM LinPos(0 TO 199) AS LONG
        
        # Fixed screen center positions like BASIC
        self.st_x_pos = 160  # Center X = 160 in mode 13
        self.st_y_pos = 150  # Center Y = 150 in mode 13
        
        pygame.init()
        self.screen = pygame.display.set_mode((800, 600))
        pygame.display.set_caption("Ultima 8 Shape Viewer")
        
        # Default shape/frame to show
        self.go_typ = 1  # GoTyp = 1
        self.go_frm = 3  # GoFrm = 3
        
        # Initialize GUI
        self.gui = GUI(self)
        
        self.load_palette(pal_file)
        self.load_and_display_shape(shape_file)
    
    def draw_metadata(self, surface, x_len, y_len, x_off, y_off, typ_num, frm_num, compr, num_frm):
        """Draw metadata overlay with shape and frame information."""
        font = pygame.font.Font(None, 24)
        line_height = 25
        metadata_color = (255, 255, 255)
        
        lines = [
            f"Shape: {self.go_typ} (Type: {typ_num})",
            f"Frame: {self.go_frm}/{num_frm-1} (Frame ID: {frm_num})",
            f"Dimensions: {x_len}x{y_len}",
            f"Hotspot: ({x_off}, {y_off})",
            f"Compression: {compr}",
        ]
        
        # Draw semi-transparent background for text
        bg_surface = pygame.Surface((300, len(lines) * line_height + 10))
        bg_surface.fill((0, 0, 0))
        bg_surface.set_alpha(128)
        surface.blit(bg_surface, (10, 10))
        
        # Draw each line of metadata
        for i, line in enumerate(lines):
            text = font.render(line, True, metadata_color)
            surface.blit(text, (15, 15 + i * line_height))
    
    def load_palette(self, filename: str) -> None:
        """Direct translation of palette loading from BASIC."""
        self.palette = []
        with open(filename, 'rb') as f:
            f.seek(4)  # Start at 5 in BASIC = offset 4 in Python
            for _ in range(768):
                val = f.read(1)[0]
                val = (val << 2)  # Convert 6-bit to 8-bit color
                self.palette.append(val)
    
    def load_and_display_shape(self, filename: str) -> None:
        """Direct translation of BASIC shape loading and display."""
        with open(filename, 'rb') as f:
            f.seek(84)  # 85 in BASIC = offset 84
            num_typ = struct.unpack('<H', f.read(2))[0]
            
            if self.go_typ < 0 or self.go_typ > num_typ - 1:
                return
            
            f.seek(128)  # 129 in BASIC = offset 128
            for ct in range(num_typ):
                self.typ_pos[ct] = struct.unpack('<I', f.read(4))[0] + 1
                self.typ_siz[ct] = struct.unpack('<I', f.read(4))[0]
            
            if self.typ_siz[self.go_typ] < 1:
                return
            
            f.seek(self.typ_pos[self.go_typ] - 1)
            f.read(4)  # Skip unknown bytes
            num_frm = struct.unpack('<H', f.read(2))[0]
            
            if self.go_frm < 0 or self.go_frm > num_frm - 1:
                return
            
            # Read frame info
            for ct in range(num_frm):
                tmp1 = f.read(1)[0]
                tmp2 = f.read(1)[0]
                tmp3 = f.read(1)[0]
                self.frm_pos[ct] = tmp3 * 65536 + tmp2 * 256 + tmp1 + self.typ_pos[self.go_typ]
                f.read(1)  # Skip unknown byte
                tmp1 = f.read(1)[0]
                tmp2 = f.read(1)[0]
                self.frm_siz[ct] = tmp2 * 256 + tmp1
            
            if self.frm_siz[self.go_frm] < 1:
                return
            
            f.seek(self.frm_pos[self.go_frm] - 1)
            typ_num = struct.unpack('<H', f.read(2))[0]
            frm_num = struct.unpack('<H', f.read(2))[0]
            f.read(4)  # Skip unknown
            compr = struct.unpack('<H', f.read(2))[0]
            x_len = struct.unpack('<H', f.read(2))[0]
            y_len = struct.unpack('<H', f.read(2))[0]
            x_off = struct.unpack('<h', f.read(2))[0]
            y_off = struct.unpack('<h', f.read(2))[0]
            
            # Read line positions
            for ct in range(y_len):
                start = f.tell()
                self.lin_pos[ct] = start
                tmp1 = f.read(1)[0]
                tmp2 = f.read(1)[0]
                tmp_pos = tmp2 * 256 + tmp1
                self.lin_pos[ct] = self.lin_pos[ct] + tmp_pos
            
            # Initialize drawing
            surface = pygame.Surface((x_len, y_len))
            surface.fill((0, 0, 0))
            
            # Start exact BASIC drawing loop
            x_pos = x_len
            y_pos = -1
            
            while True:
                while x_pos >= x_len:
                    y_pos += 1
                    if y_pos >= y_len:
                        break
                    f.seek(self.lin_pos[y_pos])
                    x_pos = f.read(1)[0]
                
                if y_pos >= y_len:
                    break
                
                dat_len = f.read(1)[0]
                
                if compr == 1:
                    if (dat_len & 1) == 1:
                        dat_len = dat_len >> 1
                        color = f.read(1)[0]
                        for i in range(dat_len):
                            if x_pos + i < x_len:
                                r = self.palette[color * 3]
                                g = self.palette[color * 3 + 1]
                                b = self.palette[color * 3 + 2]
                                surface.set_at((x_pos + i, y_pos), (r, g, b))
                    else:
                        dat_len = dat_len >> 1
                        for i in range(dat_len):
                            color = f.read(1)[0]
                            if x_pos + i < x_len:
                                r = self.palette[color * 3]
                                g = self.palette[color * 3 + 1]
                                b = self.palette[color * 3 + 2]
                                surface.set_at((x_pos + i, y_pos), (r, g, b))
                else:
                    for i in range(dat_len):
                        color = f.read(1)[0]
                        if x_pos + i < x_len:
                            r = self.palette[color * 3]
                            g = self.palette[color * 3 + 1]
                            b = self.palette[color * 3 + 2]
                            surface.set_at((x_pos + i, y_pos), (r, g, b))
                
                x_pos += dat_len
                if x_pos < x_len:
                    x_pos += f.read(1)[0]
            
            # Clear screen and display frame
            self.screen.fill((0, 0, 0))
            disp_x = 400 - x_off
            disp_y = 300 - y_off
            self.screen.blit(surface, (disp_x, disp_y))
            
            # Draw metadata
            self.draw_metadata(self.screen, x_len, y_len, x_off, y_off, typ_num, frm_num, compr, num_frm)
            
            # Draw GUI elements
            self.gui.draw(self.screen)
            
            pygame.display.flip()

    def export_current_frame(self, filename: str) -> None:
        """Export the current frame as a PNG."""
        with open("U8SHAPES.FLX", 'rb') as f:
            f.seek(84)
            num_typ = struct.unpack('<H', f.read(2))[0]
            
            if self.go_typ < 0 or self.go_typ > num_typ - 1:
                return
            
            f.seek(128)
            for ct in range(num_typ):
                self.typ_pos[ct] = struct.unpack('<I', f.read(4))[0] + 1
                self.typ_siz[ct] = struct.unpack('<I', f.read(4))[0]
            
            if self.typ_siz[self.go_typ] < 1:
                return
            
            f.seek(self.typ_pos[self.go_typ] - 1)
            f.read(4)
            num_frm = struct.unpack('<H', f.read(2))[0]
            
            if self.go_frm < 0 or self.go_frm > num_frm - 1:
                return
            
            # Read frame info
            for ct in range(num_frm):
                tmp1 = f.read(1)[0]
                tmp2 = f.read(1)[0]
                tmp3 = f.read(1)[0]
                self.frm_pos[ct] = tmp3 * 65536 + tmp2 * 256 + tmp1 + self.typ_pos[self.go_typ]
                f.read(1)
                tmp1 = f.read(1)[0]
                tmp2 = f.read(1)[0]
                self.frm_siz[ct] = tmp2 * 256 + tmp1
            
            if self.frm_siz[self.go_frm] < 1:
                return
            
            f.seek(self.frm_pos[self.go_frm] - 1)
            typ_num = struct.unpack('<H', f.read(2))[0]
            frm_num = struct.unpack('<H', f.read(2))[0]
            f.read(4)
            compr = struct.unpack('<H', f.read(2))[0]
            x_len = struct.unpack('<H', f.read(2))[0]
            y_len = struct.unpack('<H', f.read(2))[0]
            x_off = struct.unpack('<h', f.read(2))[0]
            y_off = struct.unpack('<h', f.read(2))[0]
            
            # Read line positions
            for ct in range(y_len):
                start = f.tell()
                self.lin_pos[ct] = start
                tmp1 = f.read(1)[0]
                tmp2 = f.read(1)[0]
                tmp_pos = tmp2 * 256 + tmp1
                self.lin_pos[ct] = self.lin_pos[ct] + tmp_pos
            
            # Create surface for export - just the frame size
            surface = pygame.Surface((x_len, y_len))
            surface.fill((0, 0, 0))
            
            # Start exact BASIC drawing loop
            x_pos = x_len
            y_pos = -1
            
            while True:
                while x_pos >= x_len:
                    y_pos += 1
                    if y_pos >= y_len:
                        break
                    f.seek(self.lin_pos[y_pos])
                    x_pos = f.read(1)[0]
                
                if y_pos >= y_len:
                    break
                
                dat_len = f.read(1)[0]
                
                if compr == 1:
                    if (dat_len & 1) == 1:
                        dat_len = dat_len >> 1
                        color = f.read(1)[0]
                        for i in range(dat_len):
                            if x_pos + i < x_len:
                                r = self.palette[color * 3]
                                g = self.palette[color * 3 + 1]
                                b = self.palette[color * 3 + 2]
                                surface.set_at((x_pos + i, y_pos), (r, g, b))
                    else:
                        dat_len = dat_len >> 1
                        for i in range(dat_len):
                            color = f.read(1)[0]
                            if x_pos + i < x_len:
                                r = self.palette[color * 3]
                                g = self.palette[color * 3 + 1]
                                b = self.palette[color * 3 + 2]
                                surface.set_at((x_pos + i, y_pos), (r, g, b))
                else:
                    for i in range(dat_len):
                        color = f.read(1)[0]
                        if x_pos + i < x_len:
                            r = self.palette[color * 3]
                            g = self.palette[color * 3 + 1]
                            b = self.palette[color * 3 + 2]
                            surface.set_at((x_pos + i, y_pos), (r, g, b))
                
                x_pos += dat_len
                if x_pos < x_len:
                    x_pos += f.read(1)[0]
            
            # Save just the frame without any GUI elements
            pygame.image.save(surface, filename)
            
            # Show export notification
            font = pygame.font.Font(None, 24)
            text = font.render(f"Exported {filename}", True, (0, 255, 0))
            self.screen.blit(text, (10, 460))
            pygame.display.flip()
    
    def run(self) -> None:
        """Handle input and display."""
        running = True
        clock = pygame.time.Clock()
        
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                
                # Handle GUI events
                gui_event = self.gui.handle_event(event)
                if gui_event:
                    if gui_event == 'prev_shape':
                        self.go_typ = max(0, self.go_typ - 1)
                        self.go_frm = 0
                    elif gui_event == 'next_shape':
                        self.go_typ += 1
                        self.go_frm = 0
                    elif gui_event == 'prev_frame':
                        self.go_frm = max(0, self.go_frm - 1)
                    elif gui_event == 'next_frame':
                        self.go_frm += 1
                    elif gui_event == 'export':
                        filename = f"shape_{self.go_typ:04d}_frame_{self.go_frm:04d}.png"
                        self.export_current_frame(filename)
                    elif isinstance(gui_event, tuple):
                        if gui_event[0] == 'goto_shape':
                            self.go_typ = gui_event[1]
                            self.go_frm = 0
                        elif gui_event[0] == 'goto_frame':
                            self.go_frm = gui_event[1]
                
                # Also handle keyboard shortcuts
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_LEFT:
                        self.go_typ = max(0, self.go_typ - 1)
                        self.go_frm = 0
                    elif event.key == pygame.K_RIGHT:
                        self.go_typ += 1
                        self.go_frm = 0
                    elif event.key == pygame.K_UP:
                        self.go_frm = max(0, self.go_frm - 1)
                    elif event.key == pygame.K_DOWN:
                        self.go_frm += 1
            
            # Update display
            self.load_and_display_shape("U8SHAPES.FLX")
            
            # Limit framerate
            clock.tick(30)
        
        pygame.quit()

def main():
    viewer = U8ShapeViewer("U8SHAPES.FLX", "U8PAL.PAL")
    viewer.run()

if __name__ == "__main__":
    main()