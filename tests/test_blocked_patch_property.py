#!/usr/bin/env python3
"""Property test for Property 5 of the nto-live-randomizer-options spec.

Feature: nto-live-randomizer-options
Property 5: A blocked binary patch never aborts the build

Validates: Requirements 6.1, 6.2, 6.3, 8.4

The design's Property 5 says: combining the blocked ``hide_tutorials`` patch with any
subset of transform options must still let the build complete, with ``hide_tutorials``
reporting ``applied: false`` with a reason and writing zero bytes.

The pure, fast core of that guarantee lives in the binary layer: ``apply_patches``
in ``src/binary.py`` refuses any patch whose ``blocked`` reason is set (or whose
``va`` is None) BEFORE writing a single byte, appending a ``BLOCKED`` note instead
of raising. Exercising the whole ``randomize_iso`` pipeline would need the large
retail Summoner (USA) ISO and is far too slow for a 100-iteration property test, so
this test targets the refusal invariant directly.

Approach (a) from the task: build a minimal synthetic PS2 EE ELF-in-ISO fixture that
``find_elf`` / ``_valid_elf`` accept, write it to a temp file, then call
``apply_patches`` with the blocked ``hide_tutorials`` patch (combined with arbitrary
unknown patch names and param dicts) and assert:
  * the ``hide_tutorials`` result entry has ``applied == False`` with a note containing
    "BLOCKED",
  * the ISO bytes are byte-for-byte unchanged (hash equal before/after), and
  * no exception is raised.

NOTE (2026-09-29): the blocked patch used to be ``skip_intro``. That changed when the
movie-start call site was located (va 0x002419C0), so ``skip_intro`` is now armed and
play-verified and ``hide_tutorials`` is the documented wrong lever. This test tracks
"whichever patch is blocked", so it must be updated whenever that role moves - see
docs/TEST-PLAN.md defect D1.
"""
from __future__ import annotations

import hashlib
import struct
import sys
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# Make ``src`` importable regardless of where pytest is invoked from.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import binary  # noqa: E402  (import after sys.path tweak)


# --------------------------------------------------------------------------- #
# synthetic PS2 EE ELF-in-ISO fixture
# --------------------------------------------------------------------------- #
def _build_synthetic_iso() -> bytes:
    """Produce a small byte buffer that ``binary.find_elf`` accepts.

    Layout mirrors what ``_valid_elf`` validates: a 32-bit little-endian MIPS EXEC
    ELF header followed by one PT_LOAD program header. The ELF is placed at a
    non-zero offset inside the "disc" so the offset-correction path in ``find_elf``
    is exercised too.
    """
    ELF_MAGIC = binary.ELF_MAGIC
    PT_LOAD = binary.PT_LOAD

    e_phoff = 0x34            # program headers immediately after a 52-byte header
    e_phnum = 1
    e_entry = binary.VADDR_BASE
    seg_vaddr = binary.VADDR_BASE
    seg_offset = binary.ELF_FILE_OFF_BASE
    # Cover the blocked patch's va so the segment is plausible, though the blocked
    # patch is refused before any address translation happens.
    seg_filesz = 0x00200000

    hdr = bytearray(52)
    hdr[0:4] = ELF_MAGIC
    hdr[4] = 1                # EI_CLASS = ELFCLASS32
    hdr[5] = 1                # EI_DATA  = ELFDATA2LSB
    hdr[6] = 1                # EI_VERSION
    struct.pack_into("<HH", hdr, 16, 2, 8)          # e_type=EXEC, e_machine=MIPS
    struct.pack_into("<II", hdr, 24, e_entry, e_phoff)  # e_entry, e_phoff
    struct.pack_into("<H", hdr, 44, e_phnum)        # e_phnum

    phdr = struct.pack(
        "<IIIIIIII",
        PT_LOAD,     # p_type
        seg_offset,  # p_offset
        seg_vaddr,   # p_vaddr
        seg_vaddr,   # p_paddr
        seg_filesz,  # p_filesz
        seg_filesz,  # p_memsz
        1,           # p_flags
        0x1000,      # p_align
    )

    elf = bytes(hdr) + phdr
    # Pad the ELF body a little so nothing reads off the end during validation.
    elf = elf + b"\x00" * 256

    # Embed the ELF at a non-zero offset within a slightly larger "disc image".
    prefix = b"\x00" * 0x800
    suffix = b"\x00" * 0x800
    return prefix + elf + suffix


def _write_iso(tmp_path: Path) -> Path:
    iso = tmp_path / "synthetic.iso"
    iso.write_bytes(_build_synthetic_iso())
    return iso


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Sanity: confirm the fixture actually validates before we lean on it in a property.
def test_synthetic_fixture_is_a_valid_elf(tmp_path):
    iso = _write_iso(tmp_path)
    loc = binary.find_elf(iso)
    assert loc.seg_vaddr == binary.VADDR_BASE
    # At least one patch must genuinely be blocked, or the property is meaningless.
    # This guard is what fires if the last blocked patch is un-blocked - which is
    # exactly what happened on 2026-09-29 (docs/TEST-PLAN.md defect D1).
    assert _BLOCKED_NAMES, "no blocked patch to exercise the refusal path with"


# --------------------------------------------------------------------------- #
# Property 5
# --------------------------------------------------------------------------- #
# Which patches are blocked is DERIVED from the catalogue, never hardcoded.
#
# This test previously named ``skip_intro`` in both its prose and its data. On
# 2026-09-29 that patch was un-blocked (its call site was located) and the role moved
# to ``hide_tutorials`` - which broke the test twice over, because an armed patch in
# the "others" pool is *allowed* to write. Deriving the set means the next time the
# role moves, this file needs no edit at all. See docs/TEST-PLAN.md defect D1.
_BLOCKED_NAMES = sorted(
    n for n, p in binary.PATCHES.items() if p.blocked and p.va is not None
)
assert _BLOCKED_NAMES, (
    "no blocked patch with a resolved address - this property has nothing to test"
)

# A blocked patch to target, and a pool that may contain only blocked or unknown
# names: none of them may ever write a byte.
_TARGET = st.sampled_from(_BLOCKED_NAMES)
_OTHER_NAMES = st.sampled_from(
    _BLOCKED_NAMES + ["totally_unknown", "not_a_patch", "", "endgame_gate?"]
)

# Arbitrary small param dicts to make sure encode()/params never get a chance to run
# for a blocked patch.
_PARAMS = st.dictionaries(
    keys=st.text(min_size=0, max_size=6),
    values=st.one_of(st.integers(min_value=-5, max_value=999), st.text(max_size=6)),
    max_size=3,
)


@settings(max_examples=100, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    target=_TARGET,
    others=st.lists(st.tuples(_OTHER_NAMES, _PARAMS), max_size=4),
    blocked_params=_PARAMS,
    position=st.integers(min_value=0, max_value=5),
)
def test_blocked_patch_never_aborts_the_build(tmp_path, target, others, blocked_params, position):
    """Feature: nto-live-randomizer-options, Property 5: A blocked binary patch never aborts the build

    Applying ANY blocked patch from the catalogue (combined with any set/order of other
    blocked or unknown patch names and arbitrary params) reports ``applied: false``
    with a reason, writes zero bytes, and does not raise.
    """
    iso = _write_iso(tmp_path)
    before = _sha(iso)

    # Insert the blocked patch somewhere in a varied patch list.
    patch_list = list(others)
    idx = min(position, len(patch_list))
    patch_list.insert(idx, (target, dict(blocked_params)))

    # Must not raise - the build "completes".
    report = binary.apply_patches(iso, patch_list)

    # Zero bytes written: the disc image is byte-for-byte identical.
    assert _sha(iso) == before, "a blocked/unknown patch must never write to the ISO"

    # The blocked patch is reported applied:false with a BLOCKED reason (Req 6.1-6.3, 8.4).
    blocked_entries = [r for r in report["patches"] if r["patch"] == target]
    assert blocked_entries, f"{target} must appear in the patch report"
    for entry in blocked_entries:
        assert entry["applied"] is False
        notes = " ".join(entry.get("notes", []))
        assert "BLOCKED" in notes
        assert notes.strip(), "the refusal must carry a reason"
