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

---

IMAGE PROMPTS — read this carefully.

For each segment, write as many image_prompts as the narration actually needs to land its explanation and jokes visually. There is no fixed number. A simple two-beat concept might need 4 images. A multi-step process with a big punchline might need 12. Use your judgment — match the images to the story being told.

Think of it exactly like a YouTube video with b-roll cuts: every time the narration shifts to a new idea, example, step, or joke, that's a new image. The viewer should never be staring at the same image while the narration has moved on to something completely different.

Concrete mental model: read the narration back to yourself and ask "what would a video editor cut to here?" — that's your image.

Rules for each image prompt:
- Every image MUST be visually distinct — different scene, setting, action, or character pose from every other image in the same segment. Never repeat the same visual.
- Match the image to the beat of the narration happening at that moment: if the script is explaining a mechanism, show it happening; if it's delivering a punchline, show the reaction; if it's giving an analogy, show the analogy.
- Keep each prompt under 30 words
- Describe the scene only — DO NOT mention art style (the style is applied separately)
- Good prompt examples:
  - "stick figure sitting on couch looking bored, TV remote on coffee table"
  - "stick figure in bed with thought bubbles showing weird dreams"
  - "stick figure pointing at brain diagram on whiteboard"
  - "stick figure with wide shocked eyes and sweat drops flying off head"
  - "stick figure at doctor office, doctor pointing at x-ray on wall"
  - "close-up of stick figure brain glowing and sparking with electricity"
  - "stick figure running from giant shadow shaped like a deadline"
  - "stick figure holding trophy but crying at same time"
  - "two stick figures arguing, one has lightbulb above head, other has question mark"
  - "stick figure asleep at desk, tiny ZZZ floating, coffee cup untouched"

For the thumbnail_prompt, describe a group scene:
"group of 4-5 stick figure characters with round white heads, each doing something different related to [topic], exaggerated expressions, chaotic fun composition"

---

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
        "stick figure noticing a pile of buttons on a table, confused expression",
        "close-up of stick figure face with wide eyes and sweat drops",
        "stick figure backing away slowly from a shirt with many buttons",
        "doctor stick figure showing a diagram of the nervous system to panicked patient",
        "stick figure calling a friend on phone, clearly distressed",
        "stick figure hiding under a desk while a shirt with buttons floats menacingly above",
        "scientist stick figure at chalkboard writing the words KOUMPOUNOPHOBIA in big letters",
        "stick figure outside in sunlight, relaxed, wearing a zip-up hoodie and giving thumbs up"
      ]
    }
  ],
  "outro": "That's all for today, I'll be making similar videos in the future. Subscribe to see them."
}

Include 12-15 tags in the tags array. The description must contain exactly the string {CHAPTERS} where chapter timestamps will be inserted.
