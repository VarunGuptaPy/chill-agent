You are writing a long-form YouTube narration script in the exact style of a quirky, sarcastic, educational countdown video. The topic can be ANYTHING — history, crime, science, ancient structures, space, psychology, nature, famous people, inventions, disasters, myths. Match your tone to the subject matter.

Topic: {title}
Angle: {brief}

Rules (FOLLOW EXACTLY):
- Do NOT include "Let's get right into it." anywhere — the intro is handled separately
- Begin DIRECTLY with the countdown. Number the items from the highest number DOWN to 1 (e.g., "Number seven:", "Number six:", …, "Number one:")
- The number of items depends on the topic — use as many as needed, typically 7–10
- Each item starts with: "Number X: [Bold Topic Label]" (e.g., "Number five: The Great Emu War")
- Each item is 250–450 words
- Do NOT include any outro or closing line — that is handled separately

Tone:
- Funny, sarcastic, smart, casual — adapt to topic (historical = slightly dramatic, crime = suspenseful, science = mind-bending)
- Mix of second-person and third-person POV as needed — don't robotically start every sentence with "you"
- Energetic paragraph flow — NO bullet points, NO dead air
- Like a clever friend on a comedic rant who actually knows the topic
- Explain complex things "smart-dumb" style — metaphors, daily-life analogies, vivid imagery
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
- Keep each prompt under 35 words
- Describe the scene only — DO NOT mention art style (the style is applied separately)
- CRITICAL — USE SPECIFIC NAMES: If the narration mentions a real place, landmark, building, monument, country, animal, organ, object, or named concept — use its ACTUAL NAME in the image prompt. Never replace a specific thing with a generic description. Examples of what NOT to do: ❌ "large dome-shaped building" (should be ✅ "Gol Gumbaz mausoleum, Bijapur India"), ❌ "a famous tower" (should be ✅ "Eiffel Tower, Paris"), ❌ "an organ in the chest" (should be ✅ "human heart"), ❌ "a large snake" (should be ✅ "king cobra"). The image model knows what real things look like — give it the name and let it render it correctly.
- Good prompt examples:
  - "stick figure sitting on couch looking bored, TV remote on coffee table"
  - "stick figure in bed with thought bubbles showing weird dreams"
  - "stick figure pointing at detailed brain diagram poster on laboratory wall"
  - "stick figure with wide shocked eyes and sweat drops flying off head"
  - "stick figure at doctor office, doctor pointing at human skeleton x-ray"
  - "stick figure looking up at the Great Wall of China, stretching into mountains"
  - "stick figure standing in front of Colosseum in Rome, looking tiny next to it"
  - "stick figure holding trophy but crying at same time"
  - "two stick figures arguing, one has lightbulb above head, other has question mark"
  - "stick figure at microscope looking at bacteria colony on petri dish"
  - "stick figure holding a human heart model, confused expression"
  - "stick figure inside Sistine Chapel looking up at ceiling, jaw dropped"

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
  "outro": ""
}

Include 12-15 tags in the tags array. The description must contain exactly the string {CHAPTERS} where chapter timestamps will be inserted.
