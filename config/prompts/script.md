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

Return a JSON object with this exact structure:
{
  "title": "final polished title",
  "description": "YouTube description — 2-3 paragraph hook, then {CHAPTERS} placeholder, then 5 hashtags",
  "tags": ["tag1", "tag2", ...],
  "thumbnail_prompt": "detailed image prompt for thumbnail",
  "segments": [
    {
      "number": 7,
      "label": "Button Phobia",
      "narration": "Number seven: Button Phobia...\n\n[full 250-450 word item text]",
      "image_prompt": "detailed image prompt for this segment"
    }
  ],
  "outro": "That's all for today, I'll be making similar videos in the future. Subscribe to see them."
}

Include 12-15 tags in the tags array. The description must contain exactly the string {CHAPTERS} where chapter timestamps will be inserted.
