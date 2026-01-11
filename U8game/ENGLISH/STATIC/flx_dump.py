import flx_lib
import struct
import sys
from pathlib import Path

def dump_flx_data(filename, output_filename):
    """
    Dumps all relevant data from an FLX file to a text file.

    Args:
        filename (str): Path to the FLX file.
        output_filename (str): Path to the output text file.
    """

    try:
        flx = flx_lib.FlxFile(filename)
    except FileNotFoundError as e:
        print(e)
        sys.exit(1)

    try:
        with open(output_filename, 'w') as outfile:
          outfile.write(f"FLX File Dump: {filename}\n")
          num_typ = flx.get_num_types()
          outfile.write(f"Number of types: {num_typ}\n")

          for shape_num in range(num_typ):
            type_offset = flx.get_record_offset(shape_num)
            type_size = flx.get_record_size(shape_num)
            outfile.write(f"\n----- Shape {shape_num} -----\n")
            outfile.write(f"  Type Offset: {type_offset}, Size: {type_size}\n")

            
            f_pos = type_offset - 1 + 4 # Skip the 4 unknown bytes in the type record
            
            num_frm = struct.unpack('<H', flx.file_data[f_pos:f_pos+2])[0]
            outfile.write(f"  Number of Frames: {num_frm}\n")

            f_pos +=2 # Skip the num_frm value
            
            for frame_num in range(num_frm):
                frame_info_offset = f_pos + 6*frame_num
                f_data = flx.file_data[frame_info_offset:frame_info_offset+6]
                
                frame_offset = struct.unpack('<I', f_data[0:3] + b'\x00')[0]
                frame_size = struct.unpack('<H', f_data[4:6])[0]
                
                outfile.write(f"  --- Frame {frame_num} ---\n")
                outfile.write(f"    Frame Offset (relative to type): {frame_offset}\n")
                outfile.write(f"    Frame Size: {frame_size}\n")
            
                
                
                abs_frame_offset = frame_offset + type_offset -1 #Calculate the absolute frame offset
                
                f_data = flx.file_data[abs_frame_offset:abs_frame_offset + 18]
                
                if len(f_data) < 18:
                    outfile.write(f"      Error: incomplete frame data at offset {abs_frame_offset}\n")
                    continue

                typ_num = struct.unpack('<H', f_data[0:2])[0]
                frm_num = struct.unpack('<H', f_data[2:4])[0]
                compr = struct.unpack('<H', f_data[8:10])[0]
                x_len = struct.unpack('<H', f_data[10:12])[0]
                y_len = struct.unpack('<H', f_data[12:14])[0]
                x_off = struct.unpack('<h', f_data[14:16])[0]
                y_off = struct.unpack('<h', f_data[16:18])[0]
                
                outfile.write(f"    Type Num: {typ_num}\n")
                outfile.write(f"    Frame Num: {frm_num}\n")
                outfile.write(f"    Compression: {compr}\n")
                outfile.write(f"    X Length: {x_len}\n")
                outfile.write(f"    Y Length: {y_len}\n")
                outfile.write(f"    X Offset: {x_off}\n")
                outfile.write(f"    Y Offset: {y_off}\n")
                
                line_offsets_start = abs_frame_offset + 18
                line_offsets = []
                for y in range(y_len):
                    line_offset_data = flx.file_data[line_offsets_start + y*2 :line_offsets_start+ y*2+2]
                    if len(line_offset_data) < 2:
                      outfile.write(f"      Error: incomplete line offset data at offset {line_offsets_start + y*2}\n")
                      continue
                    line_offset = struct.unpack("<H", line_offset_data)[0]
                    line_offsets.append(line_offset)
                    outfile.write(f"      Line {y} Offset: {line_offset}\n")

    except Exception as e:
      print(f"Error during processing: {e}")

def main():
    if len(sys.argv) != 3:
        print("Usage: python flx_dump.py <flx_file> <output_file>")
        sys.exit(1)
    
    flx_file = sys.argv[1]
    output_file = sys.argv[2]
    
    dump_flx_data(flx_file, output_file)
    print(f"Data dumped to {output_file}")

if __name__ == "__main__":
    main()