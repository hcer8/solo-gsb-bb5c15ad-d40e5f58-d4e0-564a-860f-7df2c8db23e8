"""字幕切分：在逐字时间轴上把修订文本切成满足字数与时长上限的最优字幕段。

切分目标（依次）：
  1. 段数最少；
  2. 断点总分最大：断点左字为句末标点（。！？；）加 2000 分，
     再加上相邻字停顿毫秒值（截到 0～1000）；
  3. 仍同分时，断点下标序列字典序最小。
"""
from __future__ import annotations

from .errors import InvalidTimelineError

# 断点左字为句末标点时的奖励分
_PUNCT_BONUS = 2000
_PUNCT_CHARS = "。！？；"
# 相邻字停顿加分的截断上限（毫秒）
_MAX_PAUSE_BONUS = 1000


def _break_score(text: str, starts: list[int], ends: list[int], pos: int) -> int:
    """在 pos-1 与 pos 之间断开的得分（pos 为右侧新段的首字下标）。"""
    score = _PUNCT_BONUS if text[pos - 1] in _PUNCT_CHARS else 0
    pause = starts[pos] - ends[pos - 1]
    if pause < 0:
        pause = 0
    elif pause > _MAX_PAUSE_BONUS:
        pause = _MAX_PAUSE_BONUS
    return score + pause


def build_caption_segments(
    text: str,
    starts: list[int],
    ends: list[int],
    max_chars: int,
    max_duration_ms: int,
) -> list[dict]:
    """把修订文本的连续字符切成字幕段。

    每段字符数不超过 max_chars，且从首字 start 到末字 end 的跨度不超过
    max_duration_ms。单字跨度超限时报 422（InvalidTimelineError）。
    返回按原文顺序排列的段列表；空文本返回空列表。
    """
    n = len(text)
    if n == 0:
        return []

    for i in range(n):
        span = ends[i] - starts[i]
        if span > max_duration_ms:
            raise InvalidTimelineError(
                f"第 {i} 个字符 {text[i]!r} 的单字跨度 {span} 毫秒超过"
                f"每段时长上限 {max_duration_ms} 毫秒，无法切分字幕")

    # 每个可断位置 e（在 text[e-1] 与 text[e] 之间断开）的得分。
    break_score = [0] * (n + 1)
    for e in range(1, n):
        break_score[e] = _break_score(text, starts, ends, e)

    # 反向 DP：suffix_count[i] / suffix_score[i] 为后缀 text[i:] 的
    # 最少段数，以及该段数下可取到的最大断点总分。
    # 单字必合法（上面已校验），故任意位置都可切分。
    inf = n + 1
    suffix_count = [inf] * (n + 1)
    suffix_score = [0] * (n + 1)
    suffix_count[n] = 0
    for i in range(n - 1, -1, -1):
        best_count = inf
        best_score = 0
        start_i = starts[i]
        hi = min(n, i + max_chars)
        for e in range(i + 1, hi + 1):
            if ends[e - 1] - start_i > max_duration_ms:
                continue
            cand_count = suffix_count[e] + 1
            cand_score = suffix_score[e]
            if e < n:
                cand_score += break_score[e]
            if (cand_count < best_count
                    or (cand_count == best_count and cand_score > best_score)):
                best_count = cand_count
                best_score = cand_score
        suffix_count[i] = best_count
        suffix_score[i] = best_score

    # 从左到右贪心重建：每步取满足（段数最少、总分最大）的最小断点下标，
    # 即得断点下标序列字典序最小的方案。
    segments: list[tuple[int, int]] = []
    pos = 0
    while pos < n:
        remaining = suffix_count[pos]
        if remaining == 1:
            segments.append((pos, n))
            break
        start_pos = starts[pos]
        hi = min(n, pos + max_chars)
        for e in range(pos + 1, hi + 1):
            if ends[e - 1] - start_pos > max_duration_ms:
                continue
            if suffix_count[e] + 1 != remaining:
                continue
            cand_score = suffix_score[e]
            if e < n:
                cand_score += break_score[e]
            if cand_score != suffix_score[pos]:
                continue
            segments.append((pos, e))
            pos = e
            break

    return [
        {
            "start_index": s,
            "end_index": e,
            "text": text[s:e],
            "start": starts[s],
            "end": ends[e - 1],
        }
        for s, e in segments
    ]
