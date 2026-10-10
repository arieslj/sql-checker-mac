"""Audit real arm64 Mach-O deployment versions against the app's declaration."""
from pathlib import Path
import plistlib
import struct
import sys

ARM64 = 0x0100000C

def slices(data):
    magic = data[:4]
    if magic in (b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf'):
        count = struct.unpack_from('>I', data, 4)[0]
        is64 = magic == b'\xca\xfe\xba\xbf'
        fmt = '>iiQQII' if is64 else '>iiIII'
        size = struct.calcsize(fmt)
        for index in range(count):
            fields = struct.unpack_from(fmt, data, 8 + index * size)
            cpu, _, offset, length = fields[:4]
            if cpu == ARM64:
                yield data[offset:offset + length]
    elif magic in (b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf'):
        yield data

def arm64_targets(data):
    result = []
    for chunk in slices(data):
        endian = '<' if chunk[:4] == b'\xcf\xfa\xed\xfe' else '>'
        cpu = struct.unpack_from(endian+'I', chunk, 4)[0]
        if cpu != ARM64: continue
        count = struct.unpack_from(endian+'I', chunk, 16)[0]
        offset = 32
        for _ in range(count):
            cmd, size = struct.unpack_from(endian+'II', chunk, offset)
            if size < 8 or offset + size > len(chunk): raise ValueError('Invalid Mach-O command')
            version = None
            if cmd == 0x32 and struct.unpack_from(endian+'I', chunk, offset+8)[0] == 1:
                version = struct.unpack_from(endian+'I', chunk, offset+12)[0]
            elif cmd == 0x24:
                version = struct.unpack_from(endian+'I', chunk, offset+8)[0]
            if version is not None:
                result.append((version >> 16, (version >> 8) & 255, version & 255))
            offset += size
    return result

def audit(app):
    app = Path(app)
    info = plistlib.loads((app/'Contents/Info.plist').read_bytes())
    parts = [int(p) for p in info['LSMinimumSystemVersion'].split('.')]
    minimum = tuple((parts + [0,0,0])[:3])
    main = app/'Contents/MacOS'/info['CFBundleExecutable']
    if not arm64_targets(main.read_bytes()): raise ValueError('Main executable lacks an arm64 macOS deployment target')
    checked, violations, seen = [], [], set()
    for path in (app/'Contents').rglob('*'):
        if not path.is_file(): continue
        resolved = path.resolve()
        if resolved in seen: continue
        seen.add(resolved)
        with path.open('rb') as file:
            if file.read(4) not in (b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf'): continue
        for target in arm64_targets(path.read_bytes()):
            item = (str(path.relative_to(app)), target)
            checked.append(item)
            if target > minimum: violations.append(item)
    if violations:
        details = '; '.join(f'{name}: {".".join(map(str, version))}' for name,version in violations)
        raise ValueError(f'Binary minimum exceeds declared macOS {info["LSMinimumSystemVersion"]}: {details}')
    return checked, minimum

if __name__ == '__main__':
    checked, minimum = audit(sys.argv[1])
    print(f'Compatibility audit passed: {len(checked)} arm64 binaries, minimum no higher than macOS {".".join(map(str, minimum))}.')
