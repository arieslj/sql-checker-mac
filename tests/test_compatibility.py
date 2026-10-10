from pathlib import Path
import importlib.util
import plistlib
import struct
import pytest

MODULE = Path(__file__).resolve().parents[1]/'mac/check_compatibility.py'
spec=importlib.util.spec_from_file_location('compatibility',MODULE)
compatibility=importlib.util.module_from_spec(spec)
spec.loader.exec_module(compatibility)

def macho(major, minor=0):
    cmd=struct.pack('<IIIIII',0x32,24,1,(major<<16)|(minor<<8),27<<16,0)
    header=struct.pack('<IiiIIIII',0xfeedfacf,compatibility.ARM64,0,2,1,len(cmd),0,0)
    return header+cmd

def application(tmp_path, native_version, dependency_version):
    app=tmp_path/'Synthetic.app'; (app/'Contents/MacOS').mkdir(parents=True)
    (app/'Contents/Resources').mkdir()
    (app/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable':'App','LSMinimumSystemVersion':'14.0'}))
    (app/'Contents/MacOS/App').write_bytes(macho(native_version))
    (app/'Contents/Resources/dependency.dylib').write_bytes(macho(dependency_version))
    return app

def test_real_arm64_minimum_is_decoded():
    assert compatibility.arm64_targets(macho(27,2))==[(27,2,0)]
    assert compatibility.arm64_targets(macho(14))==[(14,0,0)]

def test_compatible_application_and_dependency(tmp_path):
    checked,minimum=compatibility.audit(application(tmp_path,14,11))
    assert len(checked)==2 and minimum==(14,0,0)

@pytest.mark.parametrize('native,dependency',[(27,14),(14,15)])
def test_declared_minimum_cannot_hide_incompatible_binary(tmp_path,native,dependency):
    with pytest.raises(ValueError,match='exceeds declared macOS'):
        compatibility.audit(application(tmp_path,native,dependency))

def test_universal_binary_checks_the_arm64_slice():
    payload=macho(14)
    fat=struct.pack('>II',0xcafebabe,1)+struct.pack('>iiIII',compatibility.ARM64,0,28,len(payload),0)+payload
    assert compatibility.arm64_targets(fat)==[(14,0,0)]
