#!/usr/bin/env python3
"""Restore durable weekly journal. Absence may baseline; errors fail closed."""
from live_store import restore
if __name__ == '__main__':
    raise SystemExit(restore('weekly'))
