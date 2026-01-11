import pygame
import struct
import sys
import tkinter as tk
from tkinter import filedialog
from pathlib import Path
import os
import flx_lib  # Import the flx_lib module

def browse_file(title, filetypes):
    """Opens a file dialog and returns the selected file path."""
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    file_path = filedialog.askopenfilename(title=title, filetypes=filetypes)
    return file_path

def browse_save_file(title, defaultextension):
    """Opens a file dialog and returns the selected file path."""
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    file_path = filedialog.asksaveasfilename(title=title,defaultextension=defaultextension)
    return file_path

def load_bin_data(filename):
  """Loads frame data from .bin file"""
  try:
    with open(filename, 'rb') as f:
        compression = struct.unpack("<H", f.read(2))[0]
        x_len = struct.unpack("<H", f.read(2))[0]
        y_len = struct.unpack("<H", f.read(2))[0]
        x_off = struct.unpack("<h", f.read(2))[0]
        y_off = struct.unpack("<h", f.read(2))[0]
        line_offset_count = struct.unpack("<H", f.read(2))[0]
        line_offsets = []
        for _ in range(line_offset_count):
           line_offsets.append(struct.unpack("<H",f.read(2))[0])
        rle_data_len = struct.unpack("<I", f.read(4))[0]
        rle_data = f.read(rle_data_len)

        return compression, x_len, y_len, x_off, y_off, line_offsets, rle_data
  except FileNotFoundError:
      print(f"Error: .bin file not found: {filename}")
      sys.exit(1)
  except Exception as e:
      print(f"Error reading .bin file: {e}")
      sys.exit(1)

def _rewrite_flx(flx_file_path, objects):
    """Rewrites the FLX file with potentially modified objects."""
    try:
        with open(flx_file_path, 'wb') as f:
            ods = flx_lib.OAutoBufferDataSource()
            # Mimic the header structure from the C++ code
            i = 0
            ods.seek(0)
            for i in range(0x50 // 4):
                ods.write4(0x1A1A1A1A)
            ods.write4(0x00001A1A)
            ods.write4(len(objects))
            ods.write4(0x00000001)  # Assuming this is constant, needs verification
            for i in range(ods.getPos(), 0x80, 4):
                ods.write4(0)

            data_start_offset = 0x80 + (len(objects) * 8)
            current_data_offset = data_start_offset

            ods.seek(0x80)
            for obj_data in objects:
                if not obj_data:
                    ods.write4(0)
                else:
                    ods.write4(current_data_offset)
                ods.write4(len(obj_data))
                current_data_offset += len(obj_data)

            # Complete file size
            ods.seek(0x5c)
            ods.write4(current_data_offset)

            # Write the object data
            ods.seek(data_start_offset)
            for obj_data in objects:
                if obj_data:
                    ods.write(obj_data, len(obj_data))

            f.write(ods.getBuf())

    except FileNotFoundError:
        raise FileNotFoundError(f"Error: Could not write to {flx_file_path}")

def main():
    pygame.init()
    screen = pygame.display.set_mode((600, 400))
    pygame.display.set_caption("Ultima 8 Frame Importer")
    font = pygame.font.Font(None, 24)

    flx_file = ""
    bin_file = ""
    shape_num_str = ""
    frame_num_str = ""

    compression = 0
    x_len = 0
    y_len = 0
    x_off = 0
    y_off = 0
    line_offsets = []
    rle_data = b''

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            if event.type == pygame.MOUSEBUTTONDOWN:
                pos = event.pos

                if 10 < pos[0] < 180 and 20 < pos[1] < 50:
                    flx_file = browse_file("Select U8SHAPES.FLX file", (("FLX Files", "*.flx"),))

                if 10 < pos[0] < 180 and 60 < pos[1] < 90:
                    bin_file = browse_file("Select RLE .bin file", (("Binary Files", "*.bin"),))
                    if bin_file:
                       compression, x_len, y_len, x_off, y_off, line_offsets, rle_data = load_bin_data(bin_file)

                if 10 < pos[0] < 180 and 100 < pos[1] < 130:
                    shape_num_str = input("Shape #:")
                if 10 < pos[0] < 180 and 140 < pos[1] < 170:
                    frame_num_str = input("Frame #:")

                if 10 < pos[0] < 180 and 180 < pos[1] < 210: #Import button
                    if not flx_file or not bin_file or not shape_num_str or not frame_num_str:
                        print("Missing input data")
                    else:
                       try:
                           shape_num = int(shape_num_str)
                           frame_num = int(frame_num_str)
                       except ValueError:
                             print("Invalid Number given, please provide an integer value.")
                             continue

                       try:
                            flx = flx_lib.FlxFile(flx_file)
                       except FileNotFoundError as e:
                           print(e)
                           continue

                       num_typ = flx.get_num_types()
                       if shape_num < 0 or shape_num >= num_typ:
                            print(f"Invalid shape number: {shape_num}, file has {num_typ} shapes")
                            continue

                       print(f"Importing shape {shape_num} and frame {frame_num}")

                       try:
                            frame_offset = flx.calculate_frame_offset(shape_num, frame_num)
                            print(f"Calculated Frame Header offset = {frame_offset}") # Updated print
 
                            f_pos = frame_offset
                            if f_pos + 18 > len(flx.file_data): # Check for enough data for the full header
                                print("Error: Not enough data to read frame header.")
                                continue
                            f_data = flx.file_data[f_pos:f_pos+18] # Read the full header

                            original_compression = struct.unpack('<H',f_data[0:2])[0]
                            original_xoff = struct.unpack('<h',f_data[14:16])[0] # Corrected offsets for full header
                            original_yoff = struct.unpack('<h',f_data[16:18])[0] # Corrected offsets for full header

                            print(f"Original compression: {original_compression}, xoff: {original_xoff}, yoff: {original_yoff}")

                            # Generate new frame data
                            new_frame_data = bytearray()
                            new_frame_data.extend(struct.pack("<H", 0)) # typ_num - assuming 0
                            new_frame_data.extend(struct.pack("<H", 0)) # frm_num - assuming 0
                            new_frame_data.extend(struct.pack("<I", 0)) # unknown
                            new_frame_data.extend(struct.pack("<H", compression))
                            new_frame_data.extend(struct.pack("<H", x_len))
                            new_frame_data.extend(struct.pack("<H", y_len))
                            new_frame_data.extend(struct.pack("<h", original_xoff)) # Use original offsets
                            new_frame_data.extend(struct.pack("<h", original_yoff)) # Use original offsets

                            for offset in line_offsets:
                                new_frame_data.extend(struct.pack("<H", offset))

                            new_frame_data.extend(rle_data)

                            # Replace the record data
                            record_data = flx.get_record_data(shape_num)

                            # Calculate the start and end offset of the frame within the record
                            record_offset = flx.get_record_offset(shape_num)
                            frame_start_in_record = frame_offset - record_offset

                            # Read the existing frame size
                            existing_frame_size_bytes = flx.file_data[frame_offset - 3:frame_offset - 1]
                            existing_frame_size = struct.unpack("<H", existing_frame_size_bytes)[0]
                            print(f"Existing frame size: {existing_frame_size}")

                            # Prepare to rewrite the entire FLX, getting all record data
                            objects_to_write = []
                            for i in range(flx.get_num_types()):
                                if i == shape_num:
                                    # Replace the frame data within the shape's record data
                                    new_record_data = bytearray(record_data)

                                    # Calculate the position to insert the new frame size and data
                                    insert_point = frame_start_in_record - 4 # Account for the size bytes

                                    # Pack the new frame size
                                    new_frame_size_packed = struct.pack("<H", len(new_frame_data))

                                    # Replace the frame size and data
                                    new_record_data[insert_point:insert_point + 2] = new_frame_size_packed
                                    new_record_data[insert_point + 2: insert_point + 2 + existing_frame_size] = new_frame_data

                                    objects_to_write.append(bytes(new_record_data))
                                else:
                                    objects_to_write.append(flx.get_record_data(i))

                            outfile = Path(flx_file)
                            outfile = outfile.with_stem(f"{outfile.stem}_shape{shape_num}_frame{frame_num}")

                            _rewrite_flx(str(outfile), objects_to_write)
                            print(f"File written to {outfile}")

                       except (IndexError, ValueError) as e:
                            print(e)
                            continue

        screen.fill((0, 0, 0))

        # Draw buttons
        flx_text = font.render(f"FLX File: {Path(flx_file).name}", True, (255, 255, 255)) if flx_file else font.render("FLX File", True, (255,255,255))
        bin_text = font.render(f"BIN File: {Path(bin_file).name}", True, (255, 255, 255)) if bin_file else font.render("BIN File", True, (255,255,255))
        pygame.draw.rect(screen, (100, 100, 100), (10, 20, 170, 30))
        screen.blit(flx_text,(15,25))
        pygame.draw.rect(screen, (100, 100, 100), (10, 60, 170, 30))
        screen.blit(bin_text,(15,65))

        pygame.draw.rect(screen, (100, 100, 100), (10, 100, 170, 30))
        screen.blit(font.render(f"Shape: {shape_num_str}", True, (255,255,255)),(15,105))
        pygame.draw.rect(screen, (100, 100, 100), (10, 140, 170, 30))
        screen.blit(font.render(f"Frame: {frame_num_str}", True, (255,255,255)),(15,145))

        pygame.draw.rect(screen, (100, 100, 100), (10, 180, 170, 30))
        screen.blit(font.render("Import", True, (255, 255, 255)), (15, 185))

        pygame.display.flip()
    pygame.quit()

if __name__ == "__main__":
    main()