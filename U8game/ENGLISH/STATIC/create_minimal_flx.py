import pygame
import struct
import sys
import tkinter as tk
from tkinter import filedialog
from pathlib import Path
import flx_lib


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


def create_minimal_flx(output_filename, input_png):
    """
    Creates a minimal FLX file with one shape and one frame.

    Args:
        output_filename (str): The path to the output FLX file.
    """
    try:
        flx = flx_lib.FlxFile("") # Create a new FlxFile with no data
        flx.file_data = bytearray() # Remove old data

        
        surface = pygame.image.load(input_png)
        pixels, width, height = read_pixel_data(surface)
        rle_data, line_offsets = rle_encode(pixels, width, height)

        # Create a single shape
        shape_data = bytearray()
        
        # Add frame information
        frame_data = bytearray()
        frame_data.extend(struct.pack("<H", 0)) # typ_num
        frame_data.extend(struct.pack("<H", 0)) # frm_num
        frame_data.extend(struct.pack("<I", 0)) # unknown
        frame_data.extend(struct.pack("<H", 1)) # compression
        frame_data.extend(struct.pack("<H", width)) # x_len
        frame_data.extend(struct.pack("<H", height)) # y_len
        frame_data.extend(struct.pack("<h", 0)) # xoff
        frame_data.extend(struct.pack("<h", 0)) # yoff
        
        for offset in line_offsets:
           frame_data.extend(struct.pack("<H",offset))
        
        frame_data.append(10) # First line skip data
        frame_data.append(0)  #First line data length
        
        frame_offset = len(shape_data)
        
        shape_data.extend(struct.pack("<I",0)) #Unknown
        shape_data.extend(struct.pack("<H",1)) # num_frm
        shape_data.extend(struct.pack("<I", frame_offset)) # Frame offset
        shape_data.extend(struct.pack("<H", len(frame_data)))
        
        
        flx.num_types = 1
        flx.type_positions = [128]
        flx.type_sizes = [len(shape_data)]
        
        
        with open(output_filename,'wb') as f:
            ods = flx_lib.OAutoBufferDataSource()
            flx._write_header(ods, [shape_data,frame_data,rle_data])
            ods.write(shape_data, len(shape_data))
            ods.write(frame_data, len(frame_data))
            ods.write(rle_data, len(rle_data))
            f.write(ods.getBuf())
            print(f"Generated minimal file {output_filename}")
            
    except Exception as e:
            print(f"An error occurred {e}")
            sys.exit(1)


def main():
    pygame.init()
    screen = pygame.display.set_mode((400, 300))
    pygame.display.set_caption("Ultima 8 RLE Encoder")
    font = pygame.font.Font(None, 24)

    input_png = ""
    output_file = ""
    
    
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
                    output_file = filedialog.asksaveasfilename(title="Select Output File",defaultextension=".flx")
                if 10 < pos[0] < 150 and 100 < pos[1] < 130: # Start encode button
                    if not input_png or not output_file:
                        print("Missing input data")
                    else:
                      try:
                           create_minimal_flx(output_file, input_png)
                           pygame.quit()
                           sys.exit()
                      except Exception as e:
                           print(f"Unexpected exception {e}")
                           pygame.quit()
                           sys.exit(1)
        screen.fill((0,0,0))
        input_text = font.render(f"Input PNG: {Path(input_png).name}", True, (255, 255, 255)) if input_png else font.render("Input PNG", True, (255,255,255))
        output_text = font.render(f"Output File: {Path(output_file).name}", True, (255, 255, 255)) if output_file else font.render("Output File", True, (255,255,255))
        
        pygame.draw.rect(screen, (100, 100, 100), (10, 20, 140, 30))
        screen.blit(input_text,(15,25))
        pygame.draw.rect(screen, (100, 100, 100), (10, 60, 140, 30))
        screen.blit(output_text,(15,65))
        
        pygame.draw.rect(screen, (100, 100, 100), (10, 100, 140, 30))
        screen.blit(font.render("Generate", True, (255,255,255)), (15, 105))

        pygame.display.flip()
    pygame.quit()

if __name__ == "__main__":
    main()