# J.A.R.V.I.S.

A voice-enabled AI assistant powered by Claude, with a Jarvis-style interface that works on your computer and as an app on your iPhone.

## What it can do
- Chat and answer questions (Claude)
- Search the web for current information
- Tell the time and weather for any city
- Open websites (and, on your computer, launch apps)
- Set spoken reminders
- Voice: tap the reactor and speak, hear spoken replies (hands-free "Jarvis" wake word works on desktop Chrome/Edge)

---

## Put it on your iPhone (about 15 minutes)

Safari only allows the microphone on secure (https) sites, so Jarvis has to be hosted online. These steps use Render's free plan.

**1. Put the project on GitHub**
- Create a free account at github.com, make a new **private** repository, and upload everything in this folder (do not upload a `.env` file).

**2. Deploy on Render**
- Create a free account at render.com, choose **New > Blueprint**, and pick your repository. Render reads `render.yaml` for you.
- When asked, fill in:
  - `ANTHROPIC_API_KEY`: your key from console.claude.com
  - `JARVIS_ACCESS_CODE`: a long password you invent (this stops strangers from spending your credits)
- Wait for the deploy to finish. Render gives you an address like `https://jarvis-xxxx.onrender.com`.

**3. Install it on the iPhone**
- Open that address in **Safari**, enter your access code, tap the Share button, then **Add to Home Screen**.
- Jarvis now opens full screen like a normal app, with its own icon.
- First time: allow the microphone. Voice input also needs Siri and Dictation switched on in Settings > Siri.

**Using it on the phone**
- Tap the reactor, speak, and Jarvis answers aloud. You can also type.
- Say "open YouTube" and a tap-to-open link appears (iPhones block automatic pop-ups).
- Reminders ring only while the app is open on screen.

**Good to know**
- Render's free plan sleeps after inactivity, so the first message after a break can take up to a minute. A paid plan removes this.
- iPhone Safari can't listen continuously, so the "Jarvis" wake word isn't available there. Tap to talk instead.
- Jarvis can't control other iPhone apps. Apple doesn't allow websites to do that.
- Web search and replies use your API credits. There is a built-in limit of 20 requests per minute (`JARVIS_RATE_LIMIT`).

---

## Run it on your computer instead
1. Install Python 3.10+.
2. `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and add your API key.
4. `python server.py`, then open http://127.0.0.1:5000 in Chrome or Edge.

Try: "Open YouTube", "Open the calculator", "Remind me in 10 minutes to call Mum", "What's the weather in Cairo?"

## Customizing
- **Personality / what it calls you:** edit `SYSTEM_PROMPT` in `server.py`, or set `JARVIS_USER_NAME`.
- **Apps it may launch (computer only):** edit `APPS` in `server.py`. It is a whitelist so the AI can never run arbitrary commands.
- **New abilities:** add a tool definition to `TOOLS` and a function to `HANDLERS` (email, calendar, smart home, file search...).
- **Model:** set `JARVIS_MODEL`.
