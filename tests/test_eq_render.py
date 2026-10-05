"""Tests for PipeWire filter-chain config generation (EQ and 7.1 surround)."""
import pytest

from donglehub.eq import render
from donglehub.eq.model import BANDS, EqSettings


def test_eq_conf_contains_module_and_sink_props():
    conf = render.render_eq_conf(EqSettings())
    assert "libpipewire-module-filter-chain" in conf
    assert 'node.name      = "donglehub.eq"' in conf
    assert "media.class    = Audio/Sink" in conf
    assert "audio.channels = 2" in conf
    assert "[ FL FR ]" in conf


def test_eq_conf_renders_ten_bands_with_correct_filter_kinds():
    conf = render.render_eq_conf(EqSettings())
    assert "name  = band1" in conf and "label = bq_lowshelf" in conf
    assert "name  = band10" in conf and "label = bq_highshelf" in conf
    assert "name  = band5" in conf and "label = bq_peaking" in conf
    assert conf.count("label = bq_peaking") == 8
    assert "name  = preamp" in conf and "label = gain" in conf


def test_eq_conf_embeds_freqs_and_gains():
    s = EqSettings(gains=[1.0, -2.0] + [0.0] * 8, preamp=3.0)
    conf = render.render_eq_conf(s)
    assert '"Freq" = 31.0' in conf
    assert '"Freq" = 16000.0' in conf
    assert '"Gain" = 1.0' in conf
    assert '"Gain" = -2.0' in conf
    assert '"Gain" = 3.0' in conf  # preamp


def test_eq_conf_chains_preamp_through_bands():
    conf = render.render_eq_conf(EqSettings())
    assert '{ output = "preamp:Out" input = "band1:In" }' in conf
    assert '{ output = "band9:Out" input = "band10:In" }' in conf
    assert 'outputs = [ "band10:Out" ]' in conf
    assert 'inputs  = [ "band1:In" ]' in conf


def test_surround_conf_builds_hesuvi_convolver_stage():
    s = EqSettings(mode="surround", hrir="/home/u/hrirs/hesuvi.wav")
    conf = render.render_surround_conf(s)
    assert 'label = convolver2' in conf
    assert conf.count("label = convolver2") == 8
    assert conf.count('filename = "/home/u/hrirs/hesuvi.wav"') == 16  # 8 nodes x L/R
    assert 'label = mixer' in conf
    assert "audio.channels = 8" in conf
    assert "[ FL FR FC LFE RL RR SL SR ]" in conf


def test_surround_conf_maps_channels_like_hesuvi_reference():
    s = EqSettings(mode="surround", hrir="/x/hesuvi.wav")
    conf = render.render_surround_conf(s)
    # Reference mapping from pipewire's sink-virtual-surround-7.1-hesuvi.conf
    assert "channel =  0" in conf  # FL
    assert "channel =  8" in conf  # FR
    assert "channel =  6" in conf  # FC
    assert 'output = "convFL:Out 1"  input="mixL:In 1"' in conf
    assert 'input="mixR:In 8"' in conf
    assert 'inputs  = [ "convFL:In" "convFR:In"' in conf


def test_surround_conf_appends_eq_on_both_channels():
    s = EqSettings(mode="surround", hrir="/x/hesuvi.wav", gains=[5.0] + [0.0] * 9)
    conf = render.render_surround_conf(s)
    assert "name  = band1L" in conf and "name  = band1R" in conf
    assert '"Gain" = 5.0' in conf
    assert '{ output = "mixL:Out" input = "preampL:In" }' in conf
    assert '{ output = "mixR:Out" input = "preampR:In" }' in conf
    assert 'outputs = [ "band10L:Out" "band10R:Out" ]' in conf


def test_control_keys_per_mode():
    s = EqSettings()
    assert render.control_keys(s, 0) == ["band1:Gain"]
    s2 = EqSettings(mode="surround", hrir="/x/h.wav")
    assert render.control_keys(s2, 0) == ["band1L:Gain", "band1R:Gain"]
    assert render.preamp_keys(s2) == ["preampL:Gain", "preampR:Gain"]
    assert render.preamp_keys(s) == ["preamp:Gain"]


def test_settings_validate_gain_ranges():
    with pytest.raises(ValueError):
        EqSettings(gains=[13.0] + [0.0] * 9)
    with pytest.raises(ValueError):
        EqSettings(preamp=-30.0)
    with pytest.raises(ValueError):
        EqSettings(mode="surround", hrir=None)


def test_default_bands_match_classic_10_band_layout():
    assert len(BANDS) == 10
    assert [b.freq for b in BANDS][:4] == [31.0, 62.0, 125.0, 250.0]
    assert BANDS[-1].freq == 16000.0
