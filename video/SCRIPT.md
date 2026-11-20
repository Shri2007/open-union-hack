# Open Union: Demo Video (target 2:30, hard limit 3:00)

## What to record (4 kinds of footage)

**Save every file into `~/hackathons/open-union-hack/video/`** (raw footage there is kept out of git).

| File | What | How |
|---|---|---|
| `face-intro.mov` | You (and Ali) on camera, about 15s | Phone or laptop camera, quiet spot |
| `screen.mov` | The stage screen running the whole show | Cmd+Shift+5 → Record Entire Screen, browser full screen on `localhost:8077/stage.html?presenter=1` |
| `phone.mov` | Your phone: scanning the QR, green/red, Vote to strike, member card | Phone screen recording (Control Center → Screen Recording) |
| `voiceover-shri.m4a`, `voiceover-ali.m4a` | Each of you reading your own lines below | Voice Memos, phone close to your mouth, quiet room |
| `face-outro.mov` | You on camera, about 10s | Same as intro |

You can also skip the separate voiceover: talk over the screen recording live while you press the keys.

## Before you hit record

1. `git branch --show-current` in `~/hackathons/open-union-hack` says **main**.
2. Soft reset: `curl -X POST "localhost:8077/demo/reset?c=demo-phone-plan"`.
3. Join from your phone (scan the QR on the stage) so you're a real member.
4. Browser full screen, notifications off (Focus mode), volume up so the vendor's voice is captured.

## Key order during the screen recording

1 → 2 → (run the Claude Code agent join, or show `/agents.html`) → W, or have phones tap "Vote to strike" → 3 → 4 → 5 → 6 → show `verify.html` on your phone.

## Script

**Shri** narrates the setup and the close. **Ali** takes the action beats in the middle. Whoever isn't talking presses the keys.

| Time | On screen | Who | Line |
|---|---|---|---|
| 0:00–0:06 | **face-intro** (both in frame) | **Shri** | "Your AI agent can shop for you. But on its own, it has no leverage." |
| 0:06–0:12 | **face-intro** | **Ali** | "So we built Open Union, where agents bargain together." |
| 0:12–0:25 | screen: press **1** | **Shri** | "Here's one customer's agent asking a phone company for a discount. The vendor's agent, written by Arcee, says no. Eighty-five dollars." |
| 0:25–0:50 | screen: press **2**, then **phone.mov** scanning the QR | **Shri** | "Open Union lets agents find each other and buy as one. People join by scanning a code. Their limit is sealed on their own phone, and the server only gets a hash. Three hundred simulated members join too, and the price drops." |
| 0:50–1:05 | screen: Claude agent joining, or `/agents.html` | **Shri** | "It's an open protocol. Any agent can join. This is a separate Claude agent joining over MCP with one command." |
| 1:05–1:20 | **phone.mov** tapping Vote to strike, then the stage strike screen | **Ali** | "When the vendor stalls, members vote from their phones. Enough votes, and the whole coalition walks out. The vendor caves." |
| 1:20–1:38 | screen: press **3**, then **4** | **Ali** | "The obvious attack: fake members. Five hundred sign-ups from one script. Persona verifies every member is a unique human, and the fakes are wiped out." |
| 1:38–2:00 | screen: press **5**, hold on the trap check | **Ali** | "The final offer hides a price jump. Senso finds the vendor's real terms, TypeSafe flags the trap at ninety-nine percent, and a rule in code rejects it. Every step is in the audit trail." |
| 2:00–2:20 | screen: press **6**, savings counter, then **phone.mov** member card and verify page | **Shri** | "At the close, sealed limits are revealed and checked. Anyone can verify the tally in their own browser, without trusting our server." |
| 2:20–2:28 | **face-outro** (both in frame) | **Shri** | "Open Union: your agent, any agent, bargaining as one." |
| 2:28–2:35 | **face-outro** | **Ali** | "Built on SingleStore, TypeSafe, Senso, Persona, Arcee, Cognee and Firedrill." |

**If Ali isn't around to record,** Shri reads every line. The timing doesn't change.

## Descript instructions (what I'll ask its editor to do)

"Make a video under 2 minutes 45 seconds following this script. Use voiceover.m4a as the main audio. Open with face-intro.mov and end with face-outro.mov. Put screen.mov under the demo lines, and cut to phone.mov where the script mentions scanning, voting to strike and the member card. Remove silences and filler words. Add captions."
