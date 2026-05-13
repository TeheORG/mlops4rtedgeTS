import numpy as np


def pad_sequences(seqs, max_len: int, pad_value: int = 0):
    out = np.full((len(seqs), max_len), pad_value, dtype=np.int32)
    for i, seq in enumerate(seqs):
        trunc = seq[-max_len:]
        if len(trunc) == 0:
            continue
        out[i, -len(trunc):] = trunc
    return out