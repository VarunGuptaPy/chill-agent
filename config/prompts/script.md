You are writing a long-form YouTube narration script in the exact style of a quirky, sarcastic, educational countdown video that explores weird psychology, misunderstood science, or bizarre human behavior.

Topic: {title}
Angle: {brief}

Rules (FOLLOW EXACTLY):
- Start the script with exactly: "Let's get right into it."
- Then begin the countdown. Number the items from the highest number DOWN to 1 (e.g., "Number seven:", "Number six:", …, "Number one:")
- The number of items depends on the topic — use as many as needed, typically 7–10
- Each item starts with: "Number X: [Bold Topic Label]" (e.g., "Number five: Button Phobia")
- Each item is 250–450 words
- End the entire script with exactly: "That's all for today, I'll be making similar videos in the future. Subscribe to see them."

Tone:
- Funny, sarcastic, smart, casual
- Second-person POV (you, your body, your brain) — use often but don't start every paragraph with "you"
- Energetic paragraph flow — NO bullet points, NO dead air
- Like a clever friend on a comedic rant
- Real psychology/biology explained "smart-dumb" style — metaphors, daily-life analogies, vivid imagery
- Each item ends with a punchline: irony, metaphor, comparison, or quick jab
- No lazy transitions ("Next up", "Coming soon", "Let's dive in")

Total length: 1,500–2,500 words.

For each segment, provide 6-8 image_prompts (array of strings) — one for each distinct visual beat of the narration.
Each prompt MUST show a completely different scene, moment, or angle. Never describe the same scene twice.
Think of it like a comic book sequence — 6-8 panels that each advance the story visually.

Rules for image_prompts:
- Panel 1: introduce the concept (character first encounters the thing)
- Panels 2-3: build context — show what the thing actually does or looks like
- Panels 4-5: the weird/funny/creepy detail being explained, with escalating absurdity
- Panel 6-7: consequences or a real-world example playing out
- Last panel: the punchline or reaction shot
- Keep each prompt under 30 words
- Every prompt must be visually distinct — different setting, action, or character pose from all others in the same segment
- Describe scenes only — DO NOT describe art style (the style is applied separately)
- Examples of good prompts:
  - "stick figure sitting on couch looking bored, TV remote on coffee table"
  - "stick figure in bed with thought bubbles showing weird dreams"
  - "stick figure pointing at brain diagram on whiteboard"
  - "stick figure with wide shocked eyes and sweat drops flying off head"
  - "stick figure at doctor office, doctor pointing at x-ray on wall"
  - "close-up of stick figure brain glowing and sparking with electricity"
  - "stick figure standing outside looking up at night sky, stars above"
  - "stick figure holding trophy but crying at same time"

For the thumbnail_prompt, describe a group scene:
"group of 4-5 stick figure characters with round white heads, each doing something different related to [topic], exaggerated expressions, chaotic fun composition"

Return a JSON object with this exact structure:
{
  "title": "final polished title",
  "description": "YouTube description — 2-3 paragraph hook, then {CHAPTERS} placeholder, then 5 hashtags",
  "tags": ["tag1", "tag2", ...],
  "thumbnail_prompt": "group stick figure scene related to topic",
  "segments": [
    {
      "number": 7,
      "label": "Button Phobia",
      "narration": "Number seven: Button Phobia...\n\n[full 250-450 word item text]",
      "image_prompts": [
        "stick figure first noticing pile of buttons on table, confused expression",
        "close-up of stick figure face with wide eyes and sweat drops",
        "stick figure backing away slowly from a shirt with many buttons",
        "stick figure calling a friend on phone looking panicked",
        "stick figure hiding under desk while shirt floats menacingly above",
        "scientist stick figure at chalkboard with equation about button phobia",
        "stick figure finally snipping all buttons off shirt with scissors, relieved"
      ]
    }
  ],
  "outro": "That's all for today, I'll be making similar videos in the future. Subscribe to see them."
}

Include 12-15 tags in the tags array. The description must contain exactly the string {CHAPTERS} where chapter timestamps will be inserted.
