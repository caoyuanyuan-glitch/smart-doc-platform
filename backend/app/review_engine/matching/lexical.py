from __future__ import annotations


def bigrams(text: str) -> set[str]:
    chars = list(text or "")
    if len(chars) < 2:
        return {"".join(chars)} if chars else set()
    return {"".join(chars[i:i + 2]) for i in range(len(chars) - 1)}


def bigram_score(left: str, right: str) -> float:
    a = bigrams(left)
    b = bigrams(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def lcs_length(left: str, right: str) -> int:
    if not left or not right:
        return 0
    prev = [0] * (len(right) + 1)
    for ch in left:
        current = [0]
        for j, other in enumerate(right, start=1):
            if ch == other:
                current.append(prev[j - 1] + 1)
            else:
                current.append(max(prev[j], current[-1]))
        prev = current
    return prev[-1]
