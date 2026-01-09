def format_num(n: int) -> str:
    if n >= 1_000_000_000_000:
        return f"{n/1_000_000_000_000:.1f}t"
    if n >= 1_000_000_000:
        return f"{n/1_000_000_000:.1f}b"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}m"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(n)
