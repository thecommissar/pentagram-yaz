import struct
from pathlib import Path
import os

class OAutoBufferDataSource:
	def __init__(self,initial_size = 1024):
		self.buf = bytearray(initial_size)
		self.pos = 0

	def clear(self):
		self.pos = 0

	def write(self, data, size):
		if (self.pos + size) > len(self.buf):
			self.buf.extend(bytearray((self.pos + size) - len(self.buf)))
		self.buf[self.pos:self.pos+size] = data
		self.pos+=size

	def write1(self, data):
		if (self.pos + 1) > len(self.buf):
			self.buf.extend(bytearray(1))
		self.buf[self.pos] = data
		self.pos+=1

	def write2(self, data):
		if (self.pos + 2) > len(self.buf):
			self.buf.extend(bytearray(2))
		self.buf[self.pos:self.pos+2] = struct.pack("<H",data)
		self.pos+=2

	def write4(self, data):
		if (self.pos + 4) > len(self.buf):
			self.buf.extend(bytearray(4))
		self.buf[self.pos:self.pos+4] = struct.pack("<I",data)
		self.pos+=4

	def seek(self, pos):
		self.pos = pos

	def getPos(self):
		return self.pos

	def getBuf(self):
		return self.buf

class FlxFile:
    """
    A class for reading and writing Ultima VIII FLX archive files.
    """
    def __init__(self, filename):
        """
        Initializes a FlxFile object by loading data from the given file.

        Args:
            filename (str): The path to the FLX file.

        Raises:
             FileNotFoundError: If the file is not found.
        """
        self.filename = filename
        try:
            with open(filename, 'rb') as f:
                 self.file_data = bytearray(f.read())
        except FileNotFoundError:
             raise FileNotFoundError(f"Error: FLX file not found: {filename}")

        self.num_types = 0
        self.type_positions = []
        self.type_sizes = []

        if self.is_flex_file():
            self._parse_header()

    def is_flex_file(self) -> bool:
        """
        Validates that the provided file is a valid FLX archive.

        Returns:
             bool: True if the file is a valid FLX archive, otherwise False.
        """
        if len(self.file_data) < 88:
           return False

        if self.file_data[84] == 0x00 and self.file_data[85] == 0x08: # Basic FLX check
          return True
        return False

    def _parse_header(self):
        """Parses the FLX file header."""
        print(f"Parsing header, file length is {len(self.file_data)}")

        num_types_offset = 84
        if num_types_offset + 2 > len(self.file_data):
          print(f"Error: offset 84 + 2 is greater than the file length")
          return

        self.num_types = struct.unpack("<H", self.file_data[num_types_offset:num_types_offset+2])[0]

        print(f"Header value for number of types from offset {num_types_offset}: {self.num_types}")

        self.type_positions = []
        self.type_sizes = []

        for i in range(self.num_types):
            offset = 128 + i * 8
            if offset + 8 > len(self.file_data):
                print(f"Warning: End of file reached before reading all type information.")
                break
            type_pos = struct.unpack("<I", self.file_data[offset:offset+4])[0]
            type_size = struct.unpack("<I", self.file_data[offset+4:offset+8])[0]

            self.type_positions.append(type_pos)
            self.type_sizes.append(type_size)
            print(f"Type {i} - Offset: {type_pos}, Size: {type_size}")

    def get_num_types(self) -> int:
        """
        Returns the number of types (records) stored in this FLX archive file.

        Returns:
             int: The number of types in the FLX archive.
        """
        return self.num_types

    def get_record_offset(self, index: int) -> int:
          """
          Returns the file offset of a record.

          Args:
              index (int): The index of the record.

          Returns:
              int: The byte offset to the start of the record.
          Raises:
              IndexError: if the index is invalid.

          """
          if index < 0 or index >= self.num_types:
             raise IndexError("Invalid record index")
          return self.type_positions[index]

    def get_record_size(self, index: int) -> int:
         """
         Returns the size of a specific record in the file.

         Args:
            index (int): The index of the record.

         Returns:
            int: The size in bytes of the record.
         Raises:
             IndexError: if the index is invalid.
         """
         if index < 0 or index >= self.num_types:
            raise IndexError("Invalid record index")
         return self.type_sizes[index]

    def get_record_data(self, index: int) -> bytes:
       """
       Returns the data for a record in the file

       Args:
           index (int): The index of the record.

       Returns:
            bytes: The record data.
       Raises:
            IndexError: If the index is invalid.
       """
       if index < 0 or index >= self.num_types:
          raise IndexError("Invalid record index")
       offset = self.type_positions[index]
       size = self.type_sizes[index]
       return bytes(self.file_data[offset:offset+size])

    def calculate_frame_offset(self, shape_num: int, frame_num: int) -> int:
        """
        Calculates the file offset of the header of a specific frame within a shape.
        """
        if shape_num < 0 or shape_num >= self.num_types:
            raise ValueError(f"Invalid shape number: {shape_num}, file has {self.num_types} shapes")

        f_pos = self.type_positions[shape_num]
        print(f"Starting position: {f_pos}")

        f_pos += 4 # Skip the 4 unknown bytes in the type record

        if f_pos + 2 > len(self.file_data):
            raise ValueError("Invalid data in flx file")

        num_frm = struct.unpack('<H', self.file_data[f_pos:f_pos+2])[0]
        print(f"Number of frames for shape {shape_num}: {num_frm}")

        if frame_num < 0 or frame_num >= num_frm:
            raise ValueError(f"Invalid frame number: {frame_num}, for this shape, there are {num_frm} frames")

        frame_header_size = 6
        frame_offset = f_pos + 2 + frame_header_size * frame_num

        print(f"Calculated frame header offset for shape {shape_num} and frame {frame_num}: {frame_offset}")

        if frame_offset + 4 > len(self.file_data):
            raise ValueError("Invalid data in flx file")

        frame_data_offset = struct.unpack('<I', self.file_data[frame_offset:frame_offset+4])[0]
        print(f"Final Calculated frame data offset: {frame_data_offset}")

        return frame_offset # Returns the offset to the frame header

    def write_record(self, index: int, data: bytes):
        """
        Writes data to a specific record in the FLX file.

        Args:
             index (int): The index of the record.
             data (bytes): The data to be written.
        Raises:
             IndexError: if the index is invalid.
        """
        if index < 0 or index >= self.num_types:
           raise IndexError("Invalid record index")

        offset = self.type_positions[index]
        size = self.type_sizes[index]

        # Basic check to prevent writing beyond allocated size (can be improved)
        if len(data) > size:
            raise ValueError(f"Data size exceeds record size. Data: {len(data)}, Record: {size}")

        self.file_data[offset:offset+len(data)] = data

    def _write_header(self, ds, objects):
        """Writes the FLX header using the Pentagram method."""
        i = 0
        ds.seek(0)
        for i in range(0x50 // 4):
            ds.write4(0x1A1A1A1A)
        ds.write4(0x00001A1A)
        ds.write4(len(objects))
        # FIXME! This is what many flexes have next, but not all. Find out why.
        ds.write4(0x00000001)
        # FIXME! Figure out what to write until 0x80.
        for i in range(ds.getPos(), 0x80, 4):
            ds.write4(0)

        ds.seek(0x80)
        current_offset = 0x80 + (len(objects) * 8)
        for obj in objects:
            if not obj or len(obj) == 0:
                ds.write4(0)
            else:
                ds.write4(current_offset)
            ds.write4(len(obj))
            current_offset += len(obj)

        # complete file size
        ds.seek(0x5c)
        ds.write4(current_offset)

        ds.seek(current_offset)

    def write_all(self, outputfile:str):
         """
         Writes the modified data to disk

         Args:
            outputfile (str): The location to write the modified data to.
         Raises:
              FileNotFoundError: If the file path is invalid.
         """
         try:
            objects = []

            for i in range(self.num_types):
              try:
                  objects.append(self.get_record_data(i))
              except IndexError:
                   objects.append(b"") # Add an empty array to the data list if we can't get the data

            with open(outputfile,'wb') as f:
                ods = OAutoBufferDataSource()
                self._write_header(ods, objects)
                # Data is written by _write_header now, adjusting seek.
                f.write(ods.getBuf())

         except FileNotFoundError:
             raise FileNotFoundError(f"Error: Could not write to {outputfile}")