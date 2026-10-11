from .telegram import TelegramAdapter
from .website import WebsiteAdapter

ADAPTERS = {
    "telegram": TelegramAdapter,
    "website": WebsiteAdapter,
}
