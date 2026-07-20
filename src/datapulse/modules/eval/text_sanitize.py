"""JSONB 安全文本净化：剥掉写入 PostgreSQL JSONB 会报
`invalid input syntax for type json` 的非法字符。

三类非法输入（都能被 Python json.dumps 过、但 JSONB 拒收）：
  1. 孤立代理项 U+D800–U+DFFF（未配对的 UTF-16 surrogate，如被截断的半个 emoji）
     —— 报错 "Unicode low/high surrogate must follow…"，最隐蔽、本次线上真凶。
  2. NUL 字节 \x00 —— JSONB 无法映射到 text。
  3. 其它 C0 控制字符 \x01–\x08 \x0b \x0c \x0e–\x1f \x7f —— 保留 \t \n \r。

来源：日志/Excel 原始文本（客户问题、AI 答案原文）或模型回显里带了这些字符。
统一在这里根治，落库出口(_clean_json)与取数入口(_cell)双防线复用。
"""
from __future__ import annotations

import re

# C0 控制字符（保留制表/换行/回车），与标注模块 processing.py 口径一致
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_jsonb_text(s: str) -> str:
    """把字符串净化成可安全写入 JSONB 的形态。非字符串原样返回。

    先用 encode/decode(ignore) 丢掉孤立代理项（正则匹配不了未配对代理），
    再用正则剥掉 NUL 及其它 C0 控制字符。正常中文/emoji(成对代理)/希腊字母不受损。
    """
    if not isinstance(s, str):
        return s
    # 丢弃孤立代理项：surrogatepass 编码后再 ignore 解码，未配对代理被剔除
    s = s.encode("utf-8", "surrogatepass").decode("utf-8", "ignore")
    return _CTRL_RE.sub("", s)
