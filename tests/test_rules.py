"""纯逻辑单测：不需要安装 AstrBot 就能跑（CI 里跑的就是这个文件）。

被 `showcase/rules.py` 覆盖的判定规则，正是最容易写错的部分（相似度口径、正则优先级、
大小写敏感、无效正则），放在这里做回归。
"""

from showcase.rules import (
    fuzzy_hit,
    invalid_regexes,
    keyword_coverage,
    match_reply,
)

KEYWORD_RULE = {
    "__template_key": "keyword",
    "pattern": "hello",
    "reply": "关键词命中",
    "case_sensitive": False,
}
REGEX_RULE = {
    "__template_key": "regex",
    "expression": r"^ping\s+\w+",
    "reply": "正则命中",
    "priority": 10,
}


def test_关键词在指令词里也能匹配到():
    # 这就是当初的 bug：整体相似度只有 0.70，按覆盖比例才算命中
    assert keyword_coverage("showcase", "/showcase-fuzzy") == 1.0


def test_容忍拼写误差():
    assert keyword_coverage("showcase", "showcas 你好") >= 0.75


def test_不相关的消息比例很低():
    assert keyword_coverage("astrbot", "hello world") < 0.5


def test_空关键词返回零():
    assert keyword_coverage("", "anything") == 0.0


def test_模糊命中的默认阈值():
    assert fuzzy_hit(["astrbot", "showcase"], "/showcase-fuzzy", 0.75) is True


def test_模糊命中拦截无关消息():
    assert fuzzy_hit(["astrbot", "showcase"], "hello world", 0.75) is False


def test_模糊命中忽略空白():
    assert fuzzy_hit(["showcase"], "   ", 0.75) is False


def test_关键词规则不区分大小写():
    assert match_reply([KEYWORD_RULE], "say HELLO there") == "关键词命中"


def test_关键词规则可区分大小写():
    rule = {**KEYWORD_RULE, "case_sensitive": True}
    assert match_reply([rule], "say HELLO there") is None
    assert match_reply([rule], "say hello there") == "关键词命中"


def test_正则规则命中():
    assert match_reply([REGEX_RULE], "ping abc") == "正则命中"


def test_正则优先级高者先匹配():
    low = {
        "__template_key": "regex",
        "expression": r"ping",
        "reply": "低优先级",
        "priority": 1,
    }
    high = {
        "__template_key": "regex",
        "expression": r"ping",
        "reply": "高优先级",
        "priority": 99,
    }
    assert match_reply([low, high], "ping abc") == "高优先级"


def test_正则先于关键词规则():
    assert (
        match_reply([KEYWORD_RULE, {**REGEX_RULE, "expression": "hello"}], "hello")
        == "正则命中"
    )


def test_无效正则被跳过而不是抛异常():
    broken = {
        "__template_key": "regex",
        "expression": "([",
        "reply": "不该命中",
        "priority": 5,
    }
    assert match_reply([broken, KEYWORD_RULE], "hello") == "关键词命中"


def test_没有规则命中时返回None():
    assert match_reply([KEYWORD_RULE], "nothing here") is None


def test_空回复内容视为未命中():
    empty = {**KEYWORD_RULE, "reply": "   "}
    assert match_reply([empty], "hello") is None


def test_未知模板键被忽略():
    assert match_reply([{"__template_key": "unknown", "reply": "x"}], "hello") is None


def test_能列出无效正则():
    broken = {"__template_key": "regex", "expression": "(["}
    assert invalid_regexes([broken, REGEX_RULE]) == ["(["]


def test_正则全部合法时列表为空():
    assert invalid_regexes([REGEX_RULE]) == []
