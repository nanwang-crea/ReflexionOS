"""LLM HTTP 客户端默认请求头。

部分反代/网关会对明显的"脚本请求"做限流或拦截，这里构造一组类浏览器/
常见 CLI 工具风格的请求头，作为 AsyncOpenAI 客户端的默认 headers，
降低被识别拦截的概率。
"""

from collections.abc import Mapping


_BROWSER_LIKE_HEADERS = {
    "User-Agent": (
        "codex-cli/2.1.177"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    # "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Connection": "keep-alive",
}


def browser_like_default_headers() -> Mapping[str, str]:
    """获取一份类浏览器默认请求头的副本

    输入: 无
    逻辑: 返回 _BROWSER_LIKE_HEADERS 的浅拷贝，避免调用方修改到模块级共享字典
    返回: 请求头字典（User-Agent/Accept 等）
    """
    return dict(_BROWSER_LIKE_HEADERS)
