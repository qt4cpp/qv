import logging, time, functools
from typing import Callable


logger = logging.getLogger('qv')

def _safe_repr(x, maxlen=120):
    try:
        r = repr(x)
    except Exception:
        r = '<repr error>'
    if len(r) > maxlen:
        r = r[:maxlen] + '...'
    return r


def log_io(level: int = logging.DEBUG, mask: tuple[str, ...] = ()):
    """
    関数の入出力と所要時間を自動ログ。mask に指定した引数名は値をマスクする。
    :param level: debug level.
    :param mask:
    :return: None
    """
    def deco(func: Callable):
        qualname = f"{func.__module__}.{func.__qualname__}"
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if logger.isEnabledFor(level):
                arg_repr = []
                names = func.__code__.co_varnames[:func.__code__.co_argcount]
                for i, a in enumerate(args[:len(names)]):
                    name = names[i]
                    val = "***" if name in mask else _safe_repr(a)
                    if name in ("self", "cls"):
                        continue
                    arg_repr.append(f"{name}={val}")
                for k, v in kwargs.items():
                    val = "***" if k in mask else _safe_repr(v)
                    arg_repr.append(f"{k}={val}")

                logger.log(level, "-> %s(%s)", qualname, ", ".join(arg_repr))

            t0 = time.perf_counter()
            try:
                result = func(*args, **kwargs)
            except Exception:
                logger.exception("Exception in %s", qualname)
                raise
            dt = (time.perf_counter() - t0) * 1000.0
            if logger.isEnabledFor(level):
                r = _safe_repr(result, 120)
                logger.log(level, "<- %s [%0.1f ms] = %s", qualname, dt, r)
            return result
        return wrapper
    return deco
