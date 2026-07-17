"""Dorm Wire multi-sport adapters.

Backend adapters that turn free sports feeds (ESPN scoreboard JSON, etc.)
into the single game contract the arcade frontend renders. The MLB board
keeps using the original statsapi code in app.py; these modules add the
other leagues without touching it.
"""
