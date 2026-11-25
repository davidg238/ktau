"""Text → the phones the board speaks (#6): Flite's front end with the kal voice, packed as tools/kal_diphones.py's
wire for the diphone table in the board's flash (c/speech). Needs libflite and numpy.
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import clips, kal_diphones  # noqa: E402

MAX_PHONES = clips.MAX_WIRE // kal_diphones.WIRE_BYTES  # what fits one reply datagram


def load(table_path):
    """The table the board carries, as kal_diphones.unpack gives it. Its phone list numbers the wire's phones."""
    return kal_diphones.unpack(open(table_path, 'rb').read())


def fit(phones, limit):
    """The phones that fit: all of them, else up to the last pause within the limit (a whole clause), else the
    first `limit`."""
    if len(phones) <= limit:
        return phones
    pauses = [i for i, p in enumerate(phones[:limit]) if p[0] == 'pau' and i > 0]
    return phones[:pauses[-1] + 1] if pauses else phones[:limit]


def wire(text, table):
    """Returns (wire bytes, phones spoken, phones Flite made). Raises ValueError for a phone the table lacks."""
    phones, _, _ = kal_diphones.flite_utt(text)
    kept = fit(phones, MAX_PHONES)
    return kal_diphones.pack_wire(table, kept), len(kept), len(phones)
