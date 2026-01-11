import pygame
import struct
import sys
import tkinter as tk
from tkinter import filedialog
from pathlib import Path

def browse_file(title, filetypes):
    """Opens a file dialog and returns the selected file path."""
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    file_path = filedialog.askopenfilename(title=title, filetypes=filetypes)
    return file_path

def read_pixel_data(surface):
    """Extracts the raw pixel data as a list of color indices."""
    width, height = surface.get_size()
    pixels = []
    for y in range(height):
        for x in range(width):
           pixels.append(surface.get_at((x, y)))
    return pixels, width, height


def rle_encode(pixels, width, height):
    """Compresses pixel data using RLE."""
    rle_data = bytearray()
    line_offsets = []
    current_pos = 0
    compression_type = 1 # Hard code compression type, always 1

    try:
        for y in range(height):
            print(f"Starting line {y}")
            line_offsets.append(len(rle_data))
            x = 0
            while x < width:
                print(f"  x={x}  current rle_data={len(rle_data)}")
                start_x = x
                skip_pixels = 0
                while x < width and pixels[y * width + x] == (0,0,0,0):
                    skip_pixels+=1
                    x+=1
                
                print(f"    skip_pixels={skip_pixels}")

                rle_data.append(skip_pixels)

                if x >= width:
                    print(f"    end of line")
                    continue


                if compression_type == 0: # this should never run, but is here in case we change compression type
                  
                    print(f"    comp 0 rle start")
                    run_data = bytearray()
                    while x < width and pixels[y * width + x] != (0,0,0,0):
                       run_data.append(pixels[y * width + x][0])
                       x+=1

                    print(f"    comp 0 rle end.  len(run_data)={len(run_data)}")
                    rle_data.append(len(run_data))
                    rle_data.extend(run_data)
                
                elif compression_type == 1:
                  
                  print(f"    comp 1 rle start")
                  if  x < width and pixels[y * width + x] != (0,0,0,0):
                    
                    r = pixels[y*width+x][0]
                    if x+1 < width and pixels[y*width+x] == pixels[y*width+x+1]:
                      repeat_count = 0
                      while x < width and pixels[y*width+x] == pixels[y*width+start_x] and pixels[y*width+x] != (0,0,0,0):
                           repeat_count += 1
                           x+=1

                      print(f"    comp 1 repeat: repeat_count={repeat_count}, r={r}")
                      rle_data.append((repeat_count << 1)|1)
                      rle_data.append(r)

                    else:
                        run_data = bytearray()
                        while x < width and pixels[y * width + x] != (0,0,0,0):
                          run_data.append(pixels[y * width + x][0])
                          x+=1

                        print(f"    comp 1 rle end.  len(run_data)={len(run_data)}")
                        rle_data.append(len(run_data)<<1)
                        rle_data.extend(run_data)

        return bytes(rle_data), line_offsets
    except Exception as e:
      print(f"Error in rle_encode: {e}")
      sys.exit(1)

def generate_output(filename, x_len, y_len, line_offsets, rle_data):
    """Generates the binary output file."""
    try:
        with open(filename, 'wb') as f:
            f.write(struct.pack("<H", 1)) # Compression type 1
            f.write(struct.pack("<H", x_len))
            f.write(struct.pack("<H", y_len))
            f.write(struct.pack("<h", 0)) # Hotspot X
            f.write(struct.pack("<h", 0)) # Hotspot Y
            f.write(struct.pack("<H", len(line_offsets)))

            for offset in line_offsets:
                f.write(struct.pack("<H", offset))
            f.write(struct.pack("<I", len(rle_data)))
            f.write(rle_data)
            print(f"RLE data written to {filename}")
    except Exception as e:
        print(f"Error writing binary data: {e}")
        sys.exit(1)


def main():
    pygame.init()
    screen = pygame.display.set_mode((400, 300))
    pygame.display.set_caption("Ultima 8 RLE Encoder")
    font = pygame.font.Font(None, 24)

    input_png = ""
    output_file = ""
    
    encoding_active = False
    
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            
            if event.type == pygame.MOUSEBUTTONDOWN:
                pos = event.pos
                if 10 < pos[0] < 150 and 20 < pos[1] < 50: # Input PNG button
                    input_png = browse_file("Select Input PNG", (("PNG Files", "*.png"),))
                if 10 < pos[0] < 150 and 60 < pos[1] < 90: # Output file button
                    output_file = filedialog.asksaveasfilename(title="Select Output File",defaultextension=".bin")
                if 10 < pos[0] < 150 and 100 < pos[1] < 130 and not encoding_active: # Start encode button
                    if not input_png or not output_file:
                        print("Missing input data")
                    else:
                      encoding_active = True
                      try:
                            surface = pygame.image.load(input_png)
                      except pygame.error as e:
                            print(f"Error loading image: {e}")
                            pygame.quit()
                            sys.exit(1)
                      
                      try:
                          pixels, width, height = read_pixel_data(surface)
                          rle_data, line_offsets = rle_encode(pixels, width, height)
                          generate_output(output_file, width, height, line_offsets, rle_data)
                          pygame.quit()
                          sys.exit()
                      except Exception as e:
                           print(f"Unexpected exception {e}")
                           pygame.quit()
                           sys.exit(1)

                    encoding_active = False # This is here so that the encoding only happens once.
                      
        screen.fill((0, 0, 0))
        
        # Draw buttons
        input_text = font.render(f"Input PNG: {Path(input_png).name}", True, (255, 255, 255)) if input_png else font.render("Input PNG", True, (255,255,255))
        output_text = font.render(f"Output File: {Path(output_file).name}", True, (255, 255, 255)) if output_file else font.render("Output File", True, (255,255,255))
        
        pygame.draw.rect(screen, (100, 100, 100), (10, 20, 140, 30))
        screen.blit(input_text,(15,25))
        pygame.draw.rect(screen, (100, 100, 100), (10, 60, 140, 30))
        screen.blit(output_text,(15,65))
        
        pygame.draw.rect(screen, (100, 100, 100), (10, 100, 140, 30))
        screen.blit(font.render("Encode", True, (255,255,255)), (15, 105))

        pygame.display.flip()
    pygame.quit()


if __name__ == "__main__":
    main()