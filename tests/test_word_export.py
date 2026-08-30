"""exporters.word 纯函数单元测试：图片引用注册表、文件名、响应解码、占位符替换。"""
import gzip
import zlib

import pytest

from exporters.word import (
    ImageRegistry,
    _img_url_to_local_name,
    _decode_response_body,
    download_images_in_text,
)


# ---------------- ImageRegistry ----------------

def test_add_returns_incrementing_placeholder():
    reg = ImageRegistry()
    assert reg.add("图", "http://x/1.png", "1.png", "/tmp/1.png", "images/1.png") == "__IMG_REF__000001__"
    assert reg.add("图", "http://x/2.png", "2.png", "/tmp/2.png", "images/2.png") == "__IMG_REF__000002__"


def test_get_and_items():
    reg = ImageRegistry()
    key = reg.add("alt", "http://x/1.png", "1.png", "/tmp/1.png", "images/1.png")
    info = reg.get(key)
    assert info["url"] == "http://x/1.png"
    assert info["downloaded"] is False
    assert reg.get("__missing__") is None
    assert len(list(reg.items())) == 1


def test_is_placeholder_and_finditer():
    assert ImageRegistry.is_placeholder("__IMG_REF__000001__")
    assert not ImageRegistry.is_placeholder("plain text")
    assert not ImageRegistry.is_placeholder("__IMG_REF__000001__tail")
    matches = list(ImageRegistry.finditer("head __IMG_REF__000003__ tail"))
    assert len(matches) == 1
    assert matches[0].group(0) == "__IMG_REF__000003__"


def test_replace_failed_placeholders():
    reg = ImageRegistry()
    key = reg.add("题目图片", "http://x/1.png", "1.png", "/tmp/1.png", "images/1.png")
    assert reg.replace_failed_placeholders(f"见{key}") == "见[图片加载失败: 题目图片]"
    # 下载成功后占位符保持不变
    reg.get(key)["downloaded"] = True
    assert reg.replace_failed_placeholders(f"见{key}") == f"见{key}"


def test_replace_unknown_key():
    reg = ImageRegistry()
    assert reg.replace_failed_placeholders("__IMG_REF__999999__") == "[图片加载失败: ]"


# ---------------- _img_url_to_local_name ----------------

def test_local_name_basename():
    assert _img_url_to_local_name("https://cdn.x.com/a/b/photo.png") == "photo.png"


def test_local_name_no_ext_uses_md5():
    name = _img_url_to_local_name("https://cdn.x.com/img")
    assert name.endswith(".png")
    assert len(name) == 12 + 4


def test_local_name_lowercases_ext():
    assert _img_url_to_local_name("https://cdn.x.com/PHOTO.JPG") == "PHOTO.jpg"


def test_local_name_keeps_known_svg():
    assert _img_url_to_local_name("https://cdn.x.com/sketch.svg") == "sketch.svg"


def test_local_name_rejects_unknown_ext():
    assert _img_url_to_local_name("https://cdn.x.com/evil.exe") == "evil.png"


def test_local_name_sanitizes_control_chars():
    assert _img_url_to_local_name("https://cdn.x.com/a\u0000b.jpg") == "ab.jpg"


# ---------------- _decode_response_body ----------------

def test_decode_plain():
    assert _decode_response_body(b"hello") == b"hello"


def test_decode_empty():
    assert _decode_response_body(b"") == b""


def test_decode_gzip():
    payload = gzip.compress(b"photo-bytes")
    assert _decode_response_body(payload) == b"photo-bytes"


def test_decode_zlib():
    payload = zlib.compress(b"data-bytes")
    assert _decode_response_body(payload) == b"data-bytes"


def test_decode_invalid_gzip_magic_unchanged():
    data = b"\x1f\x8bgarbage-not-gzip"
    assert _decode_response_body(data) == data


# ---------------- download_images_in_text ----------------

def test_replaces_image_and_registers(tmp_path):
    text = "题干内容 ![](http://x.com/1.png) 后续"
    images_dir = tmp_path / "img"
    new_text, reg = download_images_in_text(text, str(images_dir), "images/作业A")
    assert new_text == "题干内容 __IMG_REF__000001__ 后续"
    items = list(reg.items())
    assert len(items) == 1
    key, info = items[0]
    assert info["relative_url"] == "images/作业A/1.png"
    assert info["local_path"].startswith(str(images_dir))


def test_dedup_same_url(tmp_path):
    text = "![](http://x.com/dup.png) 和 ![](http://x.com/dup.png)"
    images_dir = tmp_path / "img"
    new_text, reg = download_images_in_text(text, str(images_dir), "img")
    # 同一个 URL 出现多次：生成不同占位符，但复用同一本地文件名去重下载
    items = list(reg.items())
    assert len(items) == 2
    assert new_text.count("__IMG_REF__") == 2
    names = {info["local_name"] for _, info in items}
    assert names == {"dup.png"}
    local_paths = {info["local_path"] for _, info in items}
    assert len(local_paths) == 1


def test_no_image_unchanged(tmp_path):
    text = "纯文本没有图片"
    new_text, reg = download_images_in_text(text, str(tmp_path / "img"), "img")
    assert new_text == text
    assert len(list(reg.items())) == 0


def test_empty_text(tmp_path):
    new_text, reg = download_images_in_text("", str(tmp_path / "img"), "img")
    assert new_text == ""
    assert len(list(reg.items())) == 0