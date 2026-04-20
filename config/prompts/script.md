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

For each segment, provide 2-4 image_prompts (array of strings), not just one.
Each prompt should show a DIFFERENT moment or angle of the topic being discussed.
Think of it like comic panels — each image captures a different beat of the narration.

Rules for image_prompts:
- First image: introduce the concept (character encounters the thing)
- Middle image(s): the funny/weird/creepy detail being explained
- Last image: the punchline or reaction shot
- Keep each prompt under 30 words
- Describe scenes only — DO NOT describe art style (the style is applied separately)
- Examples of good prompts:
  - "stick figure sitting on couch looking bored, TV remote on coffee table"
  - "stick figure in bed with thought bubbles showing weird dreams"
  - "stick figure pointing at brain diagram on whiteboard"
  - "stick figure with wide shocked eyes and sweat drops flying off head"

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
        "stick figure looking disgusted at pile of buttons on table",
        "close-up of stick figure face with wide eyes and sweat drops",
        "stick figure running away from a shirt with buttons"
      ]
    }
  ],
  "outro": "That's all for today, I'll be making similar videos in the future. Subscribe to see them."
}

Include 12-15 tags in the tags array. The description must contain exactly the string {CHAPTERS} where chapter timestamps will be inserted.
