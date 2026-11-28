import struct
import unittest
import uuid

from resolve_symbols import codeview_identity, symbol_url


class SymbolIdentityTests(unittest.TestCase):
    def image(self, pe64=True, age=1):
        image = bytearray(1024)
        image[:2] = b"MZ"
        struct.pack_into("<I", image, 0x3C, 0x80)
        image[0x80:0x84] = b"PE\0\0"
        struct.pack_into("<H", image, 0x86, 1)
        optional_size = 240 if pe64 else 224
        struct.pack_into("<H", image, 0x94, optional_size)
        struct.pack_into("<H", image, 0x98, 0x20B if pe64 else 0x10B)
        directory = 0x98 + (112 if pe64 else 96)
        struct.pack_into("<II", image, directory + 48, 0x1000, 28)
        section = 0x98 + optional_size
        struct.pack_into("<IIII", image, section + 8, 512, 0x1000, 512, 512)
        identity = uuid.UUID("01234567-89ab-cdef-0123-456789abcdef")
        record = b"RSDS" + identity.bytes_le + struct.pack("<I", age) + b"C:\\build\\DWrite.pdb\0"
        struct.pack_into("<IIII", image, 512 + 12, 2, len(record), 0x1040, 576)
        image[576:576 + len(record)] = record
        return bytes(image)

    def test_guid_byte_order_age_and_embedded_build_path(self):
        for pe64 in (False, True):
            with self.subTest(pe64=pe64):
                self.assertEqual(codeview_identity(self.image(pe64, 10)),
                                 ("DWrite.pdb", "0123456789ABCDEF0123456789ABCDEFA"))

    def test_uses_actual_codeview_identity_in_official_source_url(self):
        name, identity = codeview_identity(self.image())
        self.assertEqual(symbol_url(name, identity),
                         "https://msdl.microsoft.com/download/symbols/DWrite.pdb/0123456789ABCDEF0123456789ABCDEF1/DWrite.pdb")

    def test_missing_codeview_is_not_guessed_from_module_name(self):
        image = bytearray(self.image())
        image[576:580] = b"NONE"
        with self.assertRaisesRegex(ValueError, "No RSDS"):
            codeview_identity(image)

    def test_rejects_non_pe(self):
        with self.assertRaisesRegex(ValueError, "Not a PE"):
            codeview_identity(b"not an executable")
