import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import os
os.environ.setdefault('GROQ_API_KEY','TEST')
from backend.main import _clean_brief_text, _needs_rewrite, _assemble_brief_from_tools

sample = '''"Sunday morning in Vadodara - a warm 38°C day with a hint of smog in the air. Time to get ready for those presentations!"

Startups

* The digitalX Agencies theme is a great way to give your WordPress site a sleek new look.

* The LUV1 modular bike is a game-changer for daily errands, with its 120L storage and swappable batteries.

* The EVSE Charging Dock is a must-have for electric vehicle owners, making it easy to charge on the go.

Politics

* Today's news in a nutshell: [briefly summarize the three articles]

* The dark reality of love and marriage was explored by Leo Tolstoy in his legendary novel.

India

* Fishing for higher yields? Consider investing in G-Secs, SDLs, FRSBs, or corporate bonds.

* Buying what markets ignore can be a smart investment strategy.

* Tech Query: Medi Assist Healthcare Services, Allcargo Logistics, Sanofi India, and Hemisphere Properties India - what's the outlook?

"Thought for the day: 'Don't marry until you've stopped loving the woman you've chosen, until you see her clearly, otherwise...' - Leo Tolstoy. May your presentations be as smooth as a well-prepared love letter!"'''

cleaned = _clean_brief_text(sample)
print('---CLEANED---')
print(cleaned)
print('\n---NEEDS_REWRITE---')
print(_needs_rewrite(cleaned))

# Simulate tool messages
msgs = [
    {'role': 'tool', 'content': '{"topic":"startups","articles":[{"title":"Startup A raises $10M","source":"TechCrunch","published":"2026-05-16"}]}'},
    {'role': 'tool', 'content': '{"topic":"politics","articles":[{"title":"Budget talks heat up","source":"BBC","published":"2026-05-16"}]}'},
    {'role': 'tool', 'content': '{"temp_c":38,"condition":"hazy","city":"Vadodara"}'}
]

class Req:
    pass
req = Req()
req.city = 'Vadodara'
req.interests = ['startups','politics','india']
req.focus_today = 'presentations'

print('\n---ASSEMBLED---')
print(_assemble_brief_from_tools(req, msgs))
