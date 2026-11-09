"""Compatibility entry point; uses the same encrypted state and deduplication."""
from datetime import datetime
from bot import Telegram, Store, TZ, run

if __name__ == '__main__':
    store = Store()
    run(Telegram(), store, store.load(), datetime.now(TZ), 'poll')
