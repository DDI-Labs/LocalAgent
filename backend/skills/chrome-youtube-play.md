---
name: chrome-youtube-play
description: Open Chrome, navigate to YouTube, and play a song
trigger_phrases:
- play a song on youtube
- access youtube and play music
- open chrome and play on youtube
approval_required: false
---

# chrome-youtube-play

Open Chrome, navigate to YouTube, and play a song

## Steps

### Step 1: Google Chrome is already open with Google Meet
**Context:** I can see Google Chrome is already open with Google Meet.
**Action:** click
**Element:** youtube bookmark in the bookmarks bar
**Intent:** Let me click on it to access YouTube

### Step 2: Great! YouTube is now open
**Context:** Great! YouTube is now open.
**Action:** click
**Element:** Search bar with placeholder text "Search"
**Intent:** Let me click on the search bar at the top of the page and search for a popular song

### Step 3: the YouTube page is displayed, but the search bar doesn't appear to...
**Context:** I can see the YouTube page is displayed, but the search bar doesn't appear to be in focus yet.
**Action:** unknown
**Element:** Search input field at the top center of the page
**Intent:** Let me click directly on the search input field to activate it

### Step 4: try clicking on the search bar more precisely in the center area where...
**Context:** Let me try clicking on the search bar more precisely in the center area where the text "Search" appears.
**Action:** click
**Element:** Search text box in the top center with text "Search"
