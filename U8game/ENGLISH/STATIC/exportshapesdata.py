import struct
import json

def read_u8shapes_metadata(file_path, output_json, log_details=False):
    metadata = []
    skipped_types = 0

    with open(file_path, 'rb') as f:
        # Step 1: Read the number of types
        f.seek(84)  # Offset is 85 in 1-index, so seek to 84
        num_types = struct.unpack('<H', f.read(2))[0]
        
        print(f"Number of types: {num_types}")

        # Step 2: Read type information chunks
        type_info_offset = 128  # 129 in 1-indexing
        type_entries = []
        f.seek(type_info_offset)
        for i in range(num_types):
            type_position, type_size = struct.unpack('<II', f.read(8))
            if type_size == 0:  # Skip invalid or null types
                skipped_types += 1
                continue
            type_entries.append((type_position + 1, type_size))  # +1 for 1-index adjustment

        # Step 3: Read details for each type
        for idx, (type_position, type_size) in enumerate(type_entries):
            f.seek(type_position)

            if type_size < 6:  # Type too small to contain valid headers
                print(f"Warning: Type {idx} too small, skipping.")
                skipped_types += 1
                continue

            # Read number of frames
            num_frames = struct.unpack('<H', f.read(2))[0]
            remaining_size = type_size - 4  # Adjust after reading frame count

            if log_details:
                print(f"Type {idx}: Position={type_position}, Size={type_size}, Frames={num_frames}")

            # Validate if enough space exists for frame headers
            expected_header_size = 6 * num_frames
            if expected_header_size > remaining_size:
                print(f"Warning: Type {idx} has invalid frame count or size mismatch.")
                skipped_types += 1
                continue

            # Parse frame headers
            frame_info = []
            for frame_idx in range(num_frames):
                frame_offset, unknown_byte, frame_size = struct.unpack('<3sB H', f.read(6))
                frame_position = type_position + int.from_bytes(frame_offset, 'little')
                frame_info.append({
                    'frame_index': frame_idx,
                    'frame_position': frame_position,
                    'unknown_byte': unknown_byte,
                    'frame_size': frame_size
                })

            metadata.append({
                'type_index': idx,
                'type_position': type_position,
                'type_size': type_size,
                'num_frames': num_frames,
                'frames': frame_info
            })

            if log_details:
                print(f"Type {idx}: Read {len(frame_info)} frames")

    # Step 4: Export metadata to JSON
    with open(output_json, 'w') as out_file:
        json.dump(metadata, out_file, indent=4)

    print(f"Metadata exported to {output_json}")
    print(f"Skipped {skipped_types} invalid or incomplete types out of {num_types}.")

if __name__ == "__main__":
    input_file = "U8SHAPES.FLX"  # Replace with your U8SHAPES.FLX file path
    output_file = "u8shapes_metadata.json"
    read_u8shapes_metadata(input_file, output_file, log_details=True)