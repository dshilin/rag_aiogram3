__all__ = ["dp", "bot", "router"]


def __getattr__(name):
    if name in ("dp", "bot"):
        from .dispatcher import dp, bot
        if name == "dp":
            return dp
        return bot
    if name == "router":
        from .handlers import router
        return router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return __all__
