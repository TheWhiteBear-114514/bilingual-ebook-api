"""翻译引擎抽象层。

- MockTranslator：内置示例词典，无需任何密钥即可跑通全流程（课程演示默认）
- Baidu / Youdao / DeepL：真实 HTTP 调用（BYOK，用户自己的 key）
- OfficialTranslator：平台自有密钥（存 system_config），按积分计费

TRANSLATOR_MODE=real 时才真正发起网络请求，避免演示时误扣额度。
"""
from __future__ import annotations

import hashlib
import random
import time
from dataclasses import dataclass

import httpx

from config.config_unified import settings


class TranslatorError(Exception):
    def __init__(self, message: str, code: int = 5001):
        super().__init__(message)
        self.message = message
        self.code = code


# 内置示例译文（与种子书一致），让 mock 模式的输出看起来是真的
SAMPLE_DICT: dict[str, str] = {
    "It is a truth universally acknowledged, that a single man in possession of a good fortune, must be in want of a wife.":
        "凡是有钱的单身汉，总想娶位太太，这已经成了一条举世公认的真理。",
    "However little known the feelings or views of such a man may be on his first entering a neighbourhood, this truth is so well fixed in the minds of the surrounding families, that he is considered as the rightful property of some one or other of their daughters.":
        "不管这样一个人的心情或见解在初进一个地区时多么不为人所知，这条真理却总是牢牢记在周围各家各户的心里，他被看作是他们某位女儿的准财产。",
    "Mr. Bennet replied that he had not.": "班纳特先生回答说他还没有听说。",
    "What is his name? asked Mr. Bennet.": "他叫什么名字？班纳特先生问。",
    "Bingley.": "宾利。",
    "Is he married or single, my dear?": "他是已婚还是单身，我亲爱的？",
    "Every one of my girls may have him, for all that I know. First come first served.":
        "据我所知，我的五个女儿谁都可以嫁给他。先来先得。",
    "But I assure you I am by no means so eager as you fancy, to get him for any of them.":
        "可我向你保证，我一点也不像你想象的那样迫切地想让任何一个女儿嫁给他。",
    "To be, or not to be, that is the question:": "生存还是毁灭，这是一个值得考虑的问题。",
}


class BaseTranslator:
    name = "base"

    def translate(self, text: str, src: str, tgt: str, keys: dict | None = None) -> str:  # pragma: no cover
        raise NotImplementedError


class MockTranslator(BaseTranslator):
    name = "mock"

    def translate(self, text: str, src: str, tgt: str, keys: dict | None = None) -> str:
        stripped = text.strip()
        if stripped in SAMPLE_DICT and tgt == "zh":
            return SAMPLE_DICT[stripped]
        # 未收录的句子：给出可辨识的占位译文，避免伪造「真实翻译」
        return f"〔{tgt} 演示译文〕{stripped}"


class OfficialTranslator(MockTranslator):
    """官方引擎：真实模式下走 DeepL，未配置密钥时退回 mock。"""

    name = "official"

    def translate(self, text: str, src: str, tgt: str, keys: dict | None = None) -> str:
        if settings.translator_mode == "real" and settings.official_api_key:
            return DeepLTranslator(settings.official_api_key).translate(text, src, tgt)
        return super().translate(text, src, tgt, keys)


class BaiduTranslator(BaseTranslator):
    name = "baidu"

    def __init__(self, keys: dict | None = None):
        keys = keys or {}
        self.app_id = keys.get("app_id", "")
        self.app_key = keys.get("app_key", "")

    def translate(self, text: str, src: str, tgt: str, keys: dict | None = None) -> str:
        if settings.translator_mode != "real":
            return MockTranslator().translate(text, src, tgt)
        if not self.app_id or not self.app_key:
            raise TranslatorError("百度翻译密钥缺失", 3001)
        salt = str(random.randint(32768, 65536))
        sign = hashlib.md5((self.app_id + text + salt + self.app_key).encode()).hexdigest()
        params = {
            "q": text,
            "from": "auto" if src == "auto" else src,
            "to": tgt,
            "appid": self.app_id,
            "salt": salt,
            "sign": sign,
        }
        try:
            resp = httpx.get("https://fanyi-api.baidu.com/api/trans/vip/translate", params=params, timeout=20)
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise TranslatorError(f"百度翻译调用失败：{exc}") from exc
        if data.get("error_code"):
            raise TranslatorError(f"百度翻译错误 {data.get('error_code')}：{data.get('error_msg')}", 3001)
        return "".join(item.get("dst", "") for item in data.get("trans_result", []))


class YoudaoTranslator(BaseTranslator):
    name = "youdao"

    def __init__(self, keys: dict | None = None):
        keys = keys or {}
        self.app_key = keys.get("app_key", "")
        self.secret_key = keys.get("secret_key", "")

    def translate(self, text: str, src: str, tgt: str, keys: dict | None = None) -> str:
        if settings.translator_mode != "real":
            return MockTranslator().translate(text, src, tgt)
        if not self.app_key or not self.secret_key:
            raise TranslatorError("有道智云密钥缺失", 3001)
        salt = str(int(time.time() * 1000))
        curtime = str(int(time.time()))
        sign = hashlib.sha256(
            (self.app_key + text + salt + curtime + self.secret_key).encode()
        ).hexdigest()
        payload = {
            "q": text,
            "from": "auto" if src == "auto" else src,
            "to": tgt,
            "appKey": self.app_key,
            "salt": salt,
            "sign": sign,
            "signType": "v3",
            "curtime": curtime,
        }
        try:
            resp = httpx.post("https://openapi.youdao.com/api", data=payload, timeout=20)
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise TranslatorError(f"有道智云调用失败：{exc}") from exc
        if data.get("errorCode") not in ("0", 0, None):
            raise TranslatorError(f"有道智云错误 {data.get('errorCode')}", 3001)
        return "".join(data.get("translation", []))


class DeepLTranslator(BaseTranslator):
    name = "deepl"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    def translate(self, text: str, src: str, tgt: str, keys: dict | None = None) -> str:
        if settings.translator_mode != "real":
            return MockTranslator().translate(text, src, tgt)
        if not self.api_key:
            raise TranslatorError("DeepL 密钥缺失", 3001)
        target = {"zh": "ZH", "en": "EN", "ja": "JA", "ko": "KO", "fr": "FR", "de": "DE"}.get(tgt, "ZH")
        try:
            resp = httpx.post(
                "https://api-free.deepl.com/v2/translate",
                headers={"Authorization": f"DeepL-Auth-Key {self.api_key}"},
                data={"text": text, "target_lang": target},
                timeout=20,
            )
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise TranslatorError(f"DeepL 调用失败：{exc}") from exc
        if "translations" not in data:
            raise TranslatorError(f"DeepL 返回异常：{data}", 3001)
        return data["translations"][0]["text"]


@dataclass
class EngineInfo:
    id: str
    name: str
    official: bool
    key_fields: list[dict]


ENGINES: list[EngineInfo] = [
    EngineInfo("official", "官方引擎（积分）", True, []),
    EngineInfo(
        "baidu",
        "百度翻译",
        False,
        [
            {"k": "app_id", "label": "App ID", "type": "text"},
            {"k": "app_key", "label": "App Key", "type": "password"},
        ],
    ),
    EngineInfo(
        "youdao",
        "有道智云",
        False,
        [
            {"k": "app_key", "label": "appKey", "type": "text"},
            {"k": "secret_key", "label": "secretKey", "type": "password"},
        ],
    ),
    EngineInfo("deepl", "DeepL", False, [{"k": "api_key", "label": "API Key", "type": "password"}]),
]

ENGINE_IDS = {e.id for e in ENGINES}


def get_translator(engine: str, keys: dict | None = None) -> BaseTranslator:
    if engine == "official":
        return OfficialTranslator()
    if engine == "baidu":
        return BaiduTranslator(keys)
    if engine == "youdao":
        return YoudaoTranslator(keys)
    if engine == "deepl":
        return DeepLTranslator((keys or {}).get("api_key", ""))
    raise TranslatorError(f"未知引擎：{engine}", 3001)


def validate_keys(engine: str, keys: dict | None) -> None:
    """生成前的最小校验：缺失即 3001。"""
    if engine == "official":
        return
    keys = keys or {}
    info = next((e for e in ENGINES if e.id == engine), None)
    if info is None:
        raise TranslatorError(f"未知引擎：{engine}", 3001)
    missing = [f["label"] for f in info.key_fields if not str(keys.get(f["k"], "")).strip()]
    if missing:
        raise TranslatorError(f"翻译引擎未接入：请填写 {'、'.join(missing)}", 3001)
