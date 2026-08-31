"""core.config 状态与配置辅助函数单元测试。"""
import pytest

import core.config as config
from core.config import (
    set_active_homework,
    reset_active_homework,
    reset_done_count,
    bump_done_count,
    _overall_progress,
    output_dir,
    debug_dir,
    get_appearance,
    set_appearance,
    apply_settings,
    DEFAULT_OUTPUT_DIR,
)


# ---------------- _overall_progress 总进度映射 ----------------
# 说明：并发 worker 模式下，_overall_progress 依赖的是「已完成计数（bump_done_count）
#       + 各线程在途进度（_INFLIGHT_PROGRESS）」，不再使用旧单线程实现的 _ACTIVE_HW_IDX 序号。
#       因此测试应在 set_active_homework(…, total) 设定总量后，
#       用 bump_done_count() 模拟「已完成的作业数」，再断言总进度映射。

def test_overall_progress_none_without_context():
    reset_active_homework()
    assert _overall_progress(0.5) is None


def test_overall_progress_first_homework():
    reset_active_homework()
    reset_done_count()
    set_active_homework(1, 4)
    assert _overall_progress(0) == 0.0
    assert _overall_progress(0.5) == pytest.approx(0.125)


def test_overall_progress_middle_homework():
    reset_active_homework()
    reset_done_count()
    # 模拟前 2 个作业已完成，当前作业正抓到 0.5，(2 + 0.5) / 4
    bump_done_count()
    bump_done_count()
    set_active_homework(3, 4)
    assert _overall_progress(0.5) == pytest.approx(0.625)


def test_overall_progress_clamps():
    reset_active_homework()
    reset_done_count()
    set_active_homework(1, 1)
    assert _overall_progress(1) == 1.0
    assert _overall_progress(99) == 1.0  # 越界进度收敛到 1.0
    assert _overall_progress(-3) == 0.0  # 负进度收敛到 0


def test_overall_progress_none_progress():
    reset_active_homework()
    reset_done_count()
    set_active_homework(2, 4)
    # 并发模型下 progress=None 视为在途进度 0，返回 0/4 = 0.0（而非 None）
    assert _overall_progress(None) == 0.0


# ---------------- output_dir / debug_dir ----------------

def test_output_dir_default(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RUN_ID", None)
    monkeypatch.setattr(config, "BASE_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(config, "BASE_DEBUG_DIR", str(tmp_path / "debug"))
    assert output_dir() == str(tmp_path)
    assert debug_dir() == str(tmp_path / "debug")


def test_output_dir_with_course_and_run(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RUN_ID", "20260101_120000")
    monkeypatch.setattr(config, "COURSE_NAME", "高等数学")
    monkeypatch.setattr(config, "BASE_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(config, "BASE_DEBUG_DIR", str(tmp_path / "debug"))
    suffix = "高等数学_20260101_120000"
    assert output_dir() == str(tmp_path / suffix)
    assert debug_dir() == str(tmp_path / "debug" / suffix)


def test_output_dir_with_run_only(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RUN_ID", "20260101_120000")
    monkeypatch.setattr(config, "COURSE_NAME", "")
    monkeypatch.setattr(config, "BASE_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(config, "BASE_DEBUG_DIR", str(tmp_path / "debug"))
    assert output_dir() == str(tmp_path / "20260101_120000")


def test_set_course_name_sanitizes(monkeypatch):
    monkeypatch.setattr(config, "COURSE_NAME", "")
    from core.config import set_course_name
    set_course_name("  高等数学(进行中)  ")
    assert config.COURSE_NAME == "高等数学"


# ---------------- appearance ----------------

def test_set_and_get_appearance(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "SETTINGS_FILE", "settings.json")
    set_appearance("light")
    assert get_appearance() == "light"


def test_set_appearance_invalid_raises():
    with pytest.raises(ValueError):
        set_appearance("neon")


def test_get_appearance_default_system(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "SETTINGS_FILE", "settings.json")
    apply_settings({})
    assert get_appearance() == "system"


# ---------------- apply_settings ----------------

def test_apply_settings_empty_uses_default(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BASE_OUTPUT_DIR", "unset")
    apply_settings({})
    assert config.BASE_OUTPUT_DIR == DEFAULT_OUTPUT_DIR
    assert config.COURSE_URL == ""  # 课程 URL 不从设置恢复


def test_apply_settings_maps_booleans(monkeypatch):
    monkeypatch.setattr(config, "HEADLESS", None)
    monkeypatch.setattr(config, "AUTO_EXPORT_PDF", None)
    monkeypatch.setattr(config, "FORCE_REGRAB", None)
    monkeypatch.setattr(config, "OPEN_DIR_ON_COMPLETE", None)
    monkeypatch.setattr(config, "SHOW_SOURCE_URL", None)
    apply_settings({
        "headless": False,
        "auto_export_pdf": True,
        "force_regrab": True,
        "open_dir_on_complete": False,
        "show_source_url": False,
        "output_dir": "/tmp/x",
    })
    assert config.HEADLESS is False
    assert config.AUTO_EXPORT_PDF is True
    assert config.FORCE_REGRAB is True
    assert config.OPEN_DIR_ON_COMPLETE is False
    assert config.SHOW_SOURCE_URL is False
    assert config.BASE_OUTPUT_DIR == "/tmp/x"
    assert config.BASE_DEBUG_DIR == "/tmp/x/debug"


# ---------------- 登录态加密存储 ----------------

import time as _time


def test_encrypt_decrypt_roundtrip():
    payload = b'{"cookies":[{"name":"xxt","value":"secret"}]}'
    token = config._encrypt_state_value(payload)
    # 密文不应泄露明文；非空、带版本前缀
    assert token.startswith(config.STATE_CIPHER_MAGIC)
    assert b"secret" not in token.encode("ascii")
    assert config._decrypt_state_value(
        token[len(config.STATE_CIPHER_MAGIC):]) == payload


def test_encrypt_nonce_randomization():
    payload = b"same-payload"
    t1 = config._encrypt_state_value(payload)
    _time.sleep(0.001)
    t2 = config._encrypt_state_value(payload)
    assert t1 != t2
    assert config._decrypt_state_value(
        t1[len(config.STATE_CIPHER_MAGIC):]) == payload
    assert config._decrypt_state_value(
        t2[len(config.STATE_CIPHER_MAGIC):]) == payload


def test_save_state_writes_cipher(tmp_path, monkeypatch):
    # 记录当前时间以覆盖 monkeypatch 的 _time 引用
    class _Ctx:
        def storage_state(self):
            return {"cookies": [{"name": "xxt", "value": "secret"}]}

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "STATE_FILE", str(tmp_path / "state.json"))
    assert config.save_state(_Ctx()) is True
    text = (tmp_path / "state.json").read_text(encoding="ascii")
    assert text.startswith(config.STATE_CIPHER_MAGIC)
    assert "secret" not in text  # 磁盘上不落明文


def test_save_then_load_roundtrip(tmp_path, monkeypatch):
    class _Ctx:
        def storage_state(self):
            return {"cookies": [{"name": "xxt", "value": "secret"}]}

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "STATE_FILE", str(tmp_path / "state.json"))
    config.save_state(_Ctx())
    loaded = config.load_state()
    assert loaded["cookies"][0]["value"] == "secret"


def test_load_state_legacy_plaintext(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "STATE_FILE", str(tmp_path / "state.json"))
    (tmp_path / "state.json").write_text(
        '{"cookies":[{"name":"k","value":"v"}]}', encoding="utf-8")
    assert config.load_state()["cookies"][0]["value"] == "v"


def test_load_state_migrates_legacy_to_cipher(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "STATE_FILE", str(tmp_path / "state.json"))
    (tmp_path / "state.json").write_text(
        '{"cookies":[{"name":"k","value":"v"}]}', encoding="utf-8")
    config.load_state()
    # 读取旧明文后应立即被加密重写，磁盘不再残留明文
    text = (tmp_path / "state.json").read_text(encoding="utf-8")
    assert text.startswith(config.STATE_CIPHER_MAGIC)
    assert "cookies" not in text
    # 转密文后仍能正常解密读取
    assert config.load_state()["cookies"][0]["value"] == "v"


def test_load_state_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "STATE_FILE", str(tmp_path / "state.json"))
    assert config.load_state() is None


def test_load_state_corrupt_cipher_returns_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "STATE_FILE", str(tmp_path / "state.json"))
    (tmp_path / "state.json").write_text(
        config.STATE_CIPHER_MAGIC + "AAAA" * 10, encoding="ascii")
    assert config.load_state() is None