import random

import pytest

import torch
from fastai.data.all import test_close as _test_close
from fastai.data.all import test_eq as _test_eq
from fastai.data.all import test_fail as _test_fail
from fastai.data.all import test_ne as _test_ne

from fastaudio.all import (
    AudioPadType,
    AudioTensor,
    DownmixMono,
    RemoveSilence,
    RemoveType,
    Resample,
    ResizeSignal,
    SignalShifter
)
from fastaudio.augment.signal import _shift
from fastaudio.util import apply_transform, test_audio_tensor


@pytest.fixture(scope="session")
def audio():
    return test_audio_tensor()


def test_path(audio):
    if audio is None:
        raise Exception("Could not find audio")


def test_silence_removed(audio):
    "Add silence to a signal and test that it gets removed"
    silencer = RemoveSilence(threshold=20, pad_ms=20)
    orig, silenced = apply_transform(silencer, audio)
    assert silenced.nsamples <= orig.nsamples


def test_silence_not_removed(audio):
    "Test that nothing is removed from audio that doesnt contain silence"
    test_aud = AudioTensor(torch.ones_like(audio), 16000)
    orig_samples = test_aud.nsamples

    for rm_type in [RemoveType.All, RemoveType.Trim, RemoveType.Split]:
        silence_audio_trim = RemoveSilence(rm_type, threshold=20, pad_ms=20)(test_aud)
        assert orig_samples == silence_audio_trim.nsamples


def test_resample(audio):
    no_resample_needed = Resample(audio.sr)
    inp, out = apply_transform(no_resample_needed, audio)
    assert inp.sr == out.sr
    _test_eq(inp.data, out.data)


def test_resample_rates(audio):
    "Test and hear realistic sample rates"
    for rate in [2000, 4000, 8000, 22050, 44100]:
        resampler = Resample(rate)
        inp, out = apply_transform(resampler, audio)
        assert rate == out.sr
        assert out.nsamples == inp.duration * rate


def test_resample_multi_channel(audio):
    audio = test_audio_tensor(channels=3)
    resampler = Resample(8000)
    _, out = apply_transform(resampler, audio)
    _test_eq(out.nsamples, out.duration * 8000)
    _test_eq(out.nchannels, 3)
    _test_eq(out.sr, 8000)


def test_upsample(audio):
    for _ in range(10):
        random_sr = random.randint(16000, 72000)
        random_upsample = Resample(random_sr)(audio)
        num_samples = random_upsample.nsamples
        _test_close(num_samples, abs(audio.nsamples // (audio.sr / random_sr)), eps=1.1)


def test_cropping():
    "Can use the ResizeSignal Transform"
    audio = test_audio_tensor(seconds=10, sr=1000)

    inp, out1000 = apply_transform(ResizeSignal(1000), audio.clone())
    inp, out2000 = apply_transform(ResizeSignal(2000), audio.clone())
    inp, out5000 = apply_transform(ResizeSignal(5000), audio.clone())

    _test_eq(out1000.duration, 1)
    _test_eq(out2000.duration, 2)
    _test_eq(out5000.duration, 5)

    _test_eq(out1000.nsamples, out1000.duration * inp.sr)
    _test_eq(out2000.nsamples, out2000.duration * inp.sr)
    _test_eq(out5000.nsamples, out5000.duration * inp.sr)

    # Multi Channel Cropping
    inp, mc1000 = apply_transform(ResizeSignal(1000), audio.clone())
    inp, mc2000 = apply_transform(ResizeSignal(2000), audio.clone())
    inp, mc5000 = apply_transform(ResizeSignal(5000), audio.clone())

    _test_eq(mc1000.duration, 1)
    _test_eq(mc2000.duration, 2)
    _test_eq(mc5000.duration, 5)


def test_padding_after(audio):
    "Padding is added to the end  but not the beginning"
    new_duration = (audio.duration + 1) * 1000
    cropsig_pad_after = ResizeSignal(new_duration, pad_mode=AudioPadType.Zeros_After)
    # generate a random input signal that is 3s long
    inp, out = apply_transform(cropsig_pad_after, audio)
    # test end of signal is padded with zeros
    _test_eq(out[:, -10:], torch.zeros_like(out)[:, -10:])
    # test front of signal is not padded with zeros
    _test_ne(out[:, 0:10], out[:, -10:])


def test_padding_both_side(audio):
    "Make sure they are padding on both sides"
    new_duration = (audio.duration + 1) * 1000
    cropsig_pad_after = ResizeSignal(new_duration)
    inp, out = apply_transform(cropsig_pad_after, audio)
    _test_eq(out[:, 0:2], out[:, -2:])


def test_resize_signal_repeat(audio):
    """
    Test pad_mode repeat by making sure that columns are
    equal at the appropriate offsets
    """
    dur = audio.duration * 1000
    repeat = 3
    cropsig_repeat = ResizeSignal(dur * repeat, pad_mode=AudioPadType.Repeat)
    inp, out = apply_transform(cropsig_repeat, audio)
    for i in range(repeat):
        s = int(i * inp.nsamples)
        e = int(s + inp.nsamples)
        print(out[:, s:e].shape, inp.shape)
        _test_eq(out[:, s:e], inp)


def test_fail_invalid_pad_mode():
    _test_fail(ResizeSignal(12000, pad_mode="tenchify"))


def test_shift():
    t1 = torch.tensor([[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]])
    t3 = torch.tensor(
        [
            [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            [11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
            [21, 22, 23, 24, 25, 26, 27, 28, 29, 30],
        ]
    )
    b4 = torch.stack([t3, t3, t3, t3])

    _test_eq(b4.shape, torch.Size([4, 3, 10]))
    _test_eq(_shift(t1, 4), torch.tensor([[0, 0, 0, 0, 1, 2, 3, 4, 5, 6]]))
    _test_eq(
        _shift(t3, -2),
        torch.tensor(
            [
                [3, 4, 5, 6, 7, 8, 9, 10, 0, 0],
                [13, 14, 15, 16, 17, 18, 19, 20, 0, 0],
                [23, 24, 25, 26, 27, 28, 29, 30, 0, 0],
            ]
        ),
    )


def test_rolling(audio):
    shift_and_roll = SignalShifter(p=1, max_pct=0.5, roll=True)
    inp, out = apply_transform(shift_and_roll, audio)
    _test_eq(inp.data.shape, out.data.shape)


def test_down_mix_mono(audio):
    "Test downmixing 1 channel has no effect"
    downmixer = DownmixMono()
    inp, out = apply_transform(downmixer, audio)
    _test_eq(inp.data, out.data)
