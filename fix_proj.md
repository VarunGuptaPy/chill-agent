# Claude Code: Fix Image Generation — Style, Multi-Image, NSFW Safety

Read this entire prompt, then make ALL the changes described below. Do not ask questions. Just implement.

---

## PROBLEM 1: Wrong Image Style

The current image generation produces detailed, polished cartoon illustrations (like Pixar or editorial illustration style). The channel needs a VERY SPECIFIC style:

- **Simple stick-figure characters** with large round white heads, black dot eyes, tiny nose (optional), simple mouth
- **Black stick-figure bodies** — literal lines for arms, legs, torso
- **Messy/spiky hair** on the characters (brown/orange), drawn with rough strokes
- **Minimal backgrounds** — flat solid colors, simple furniture/objects drawn with basic shapes
- **Bold black outlines** on everything
- **Very flat shading** — no gradients, no 3D, no shadows, no lighting effects
- **Intentionally crude/simple** — like a webcomic or whiteboard animation, NOT polished
- **Think: "Cyanide and Happiness" meets "xkcd" meets "Diary of a Wimpy Kid"**

This is NOT achievable with Flux Pro because Flux tries too hard to make things look good. The style requires deliberate simplicity.

### SOLUTION: Change the image generation approach

**Option A (Preferred): Switch to Flux Schnell with aggressive style prompting**

Change `services/image/replicate_flux.py` to use `black-forest-labs/flux-schnell` instead of `flux-1.1-pro`. Schnell is faster, cheaper ($0.003/image vs $0.055), and produces less "overcooked" results that are easier to steer toward simple styles.

**Option B: Keep Flux Pro but completely rewrite prompts**

If staying with Flux Pro, the prompts must be extremely specific about the crude style.

### Update `config/style_suffix.txt` to this EXACT text:

```
simple stick figure webcomic style, character has large round white head with black dot eyes and small mouth, black stick body with thin line arms and legs, messy spiky brown hair, minimal flat colored background, bold black outlines, no shading, no gradients, no 3D, no shadows, no lighting effects, extremely simple crude drawing style like Cyanide and Happiness or Diary of a Wimpy Kid, white background or simple solid color background, 16:9 aspect ratio
```

### Update the image prompt generation in `stages/script.py`

The LLM prompt that generates image prompts per segment must be updated. Find the section where image_prompt is generated for each segment and update the instructions to:

```
For each segment, generate an image_prompt that describes the SCENE, not the style.
Focus on: what is the stick figure character doing, what emotion are they showing, what simple objects are around them.
Keep it short and scene-focused. Examples:
- "stick figure character sitting on a couch looking bored, TV remote on coffee table, window behind"
- "stick figure character in bed with thought bubbles above showing weird dreams"
- "stick figure character pointing at a brain diagram on a whiteboard in a lab"
- "stick figure character looking shocked with electricity bolts around their head"
DO NOT describe art style in the image prompt — the style suffix handles that.
DO NOT ask for detailed, realistic, or polished illustrations.
Keep descriptions under 30 words. Simple scenes only.
```

### Update `stages/images.py` — the prompt assembly

When assembling the final prompt (scene prompt + style suffix), make sure the style suffix comes FIRST, then the scene. This ensures the model prioritizes style over content:

```python
# WRONG (current):
final_prompt = f"{scene_prompt}, {style_suffix}"

# CORRECT (new):
final_prompt = f"{style_suffix}. Scene: {scene_prompt}"
```

---

## PROBLEM 2: Only 1 Image Per Segment — Need Multiple

Currently the pipeline generates exactly 1 image per countdown item. But some segments need 2–4 images to visually explain the topic better and keep the video interesting (instead of staring at the same image for 30–60 seconds).

### SOLUTION: Multi-image segments

**A) Update the script generation prompt** to request multiple image prompts per segment:

In `config/prompts/script.md`, update the segment schema:

```json
{
  "number": 7,
  "label": "Button Phobia",
  "narration": "Number seven: Button Phobia...",
  "image_prompts": [
    "stick figure looking disgusted at a pile of buttons on a table",
    "close-up of stick figure's face with wide eyes and sweat drops",
    "stick figure running away from a shirt with buttons"
  ]
}
```

Note: changed from `"image_prompt"` (singular string) to `"image_prompts"` (array of strings).

Add this instruction to the LLM prompt:
```
For each segment, provide 2-4 image_prompts (array of strings), not just one.
Each prompt should show a DIFFERENT moment or angle of the topic being discussed.
Think of it like comic panels — each image captures a different beat of the narration.
Rules for image prompts:
- First image: introduce the concept (character encounters the thing)
- Middle image(s): the funny/weird/creepy detail being explained
- Last image: the punchline or reaction shot
- Keep each prompt under 30 words
- Describe scenes, not art style
```

**B) Update `stages/images.py`** to handle the array:

```python
# Old: one image per segment
for segment in script.segments:
    generate_image(segment.image_prompt, ...)

# New: multiple images per segment
for segment in script.segments:
    segment_images = []
    for i, prompt in enumerate(segment.image_prompts):
        img = generate_image(prompt, output_path=f"seg_{segment.number}_{i}.png")
        segment_images.append(img)
```

**C) Update `stages/assembly.py`** — Ken Burns with multiple images per segment:

Instead of showing 1 image for the entire segment duration, split the segment duration evenly across its images:

```python
# Old: one image for full segment duration
create_ken_burns_clip(image, duration=segment_duration)

# New: split across multiple images
images_for_segment = get_images_for_segment(segment)
time_per_image = segment_duration / len(images_for_segment)

for img in images_for_segment:
    create_ken_burns_clip(img, duration=time_per_image)
```

Each image should get a minimum of 3 seconds and a maximum of 8 seconds. If the math doesn't work out, adjust:

```python
num_images = len(images_for_segment)
time_per_image = segment_duration / num_images

# Clamp to reasonable range
time_per_image = max(3.0, min(8.0, time_per_image))

# If we have too many images for the segment, drop extras from the end
max_images = int(segment_duration / 3.0)
images_for_segment = images_for_segment[:max_images]
```

**D) Update `media/alignment.py`** to provide sub-segment timestamps:

The forced alignment already gives word-level timestamps. Use these to calculate natural "cut points" within a segment — ideally between sentences or at natural pauses, rather than splitting evenly:

```python
def get_image_switch_times(segment_start, segment_end, num_images, word_timestamps):
    """Find natural cut points within a segment for image switches."""
    segment_words = [w for w in word_timestamps
                     if segment_start <= w.start < segment_end]

    # Find sentence boundaries (words ending with . ! ?)
    sentence_ends = [w.end for w in segment_words
                     if w.word.rstrip().endswith(('.', '!', '?'))]

    if len(sentence_ends) >= num_images - 1:
        # Use sentence boundaries as cut points
        step = len(sentence_ends) // num_images
        cut_points = [sentence_ends[i * step] for i in range(1, num_images)]
    else:
        # Fall back to even splits
        duration = segment_end - segment_start
        cut_points = [segment_start + (duration * i / num_images)
                      for i in range(1, num_images)]

    return [segment_start] + cut_points + [segment_end]
```

---

## PROBLEM 3: NSFW Safety — Must NEVER Generate Inappropriate Images

The channel is educational and could be watched by anyone. We need multiple layers of NSFW protection.

### SOLUTION: Three-layer safety system

**Layer 1: Prompt-level blocking (in `stages/images.py`)**

Before sending ANY prompt to the image model, run it through a blocklist check:

```python
NSFW_BLOCKLIST = [
    "nude", "naked", "nsfw", "porn", "sex", "erotic", "lingerie",
    "bikini", "underwear", "topless", "breast", "genitalia", "buttocks",
    "seductive", "provocative", "sensual", "intimate", "fetish",
    "gore", "blood", "dismember", "torture", "mutilat", "decapitat",
    "drug", "cocaine", "heroin", "meth", "syringe",
    "weapon", "gun", "rifle", "pistol", "knife attack",
    "racist", "nazi", "swastika", "hate",
    "child abuse", "minor", "underage",
]

def check_prompt_safety(prompt: str) -> bool:
    """Returns True if prompt is safe, False if blocked."""
    prompt_lower = prompt.lower()
    for term in NSFW_BLOCKLIST:
        if term in prompt_lower:
            logger.warning(f"Blocked NSFW term '{term}' in image prompt: {prompt}")
            return False
    return True
```

**Layer 2: Force safety in every prompt (in `stages/images.py`)**

Append a negative constraint to every image prompt sent to the model:

```python
SAFETY_SUFFIX = ", safe for work, family friendly, no nudity, no violence, no blood, no weapons, cartoon style"

def build_final_prompt(scene_prompt: str, style_suffix: str) -> str:
    return f"{style_suffix}. Scene: {scene_prompt}{SAFETY_SUFFIX}"
```

**Layer 3: Script-level moderation (in `stages/script.py`)**

Before generating images, run the ENTIRE script through a moderation check. Add this to the script generation stage:

```python
def moderate_script(script_text: str) -> bool:
    """Use DeepSeek to check if script content is appropriate."""
    response = llm.complete(
        model="deepseek-chat",
        messages=[{
            "role": "user",
            "content": f"""Review this YouTube script for a family-friendly educational channel.
Does it contain any of: sexual content, graphic violence, hate speech, drug promotion, or content inappropriate for general audiences?

Reply with ONLY "SAFE" or "UNSAFE: [reason]"

Script:
{script_text}"""
        }],
        temperature=0.0,
        max_tokens=50,
    )
    result = response.choices[0].message.content.strip()
    return result.startswith("SAFE")
```

If the moderation check returns UNSAFE, discard the script and regenerate with a different topic.

**Layer 4: Add safety_checker parameter to Replicate call (if available)**

Some Replicate models support a `safety_checker` parameter. Add it:

```python
prediction = replicate_client.predictions.create(
    model="black-forest-labs/flux-schnell",
    input={
        "prompt": final_prompt,
        "disable_safety_checker": False,  # Keep safety ON
        # ... other params
    }
)
```

---

## PROBLEM 4: Thumbnail Style

The thumbnail needs to match the stick-figure style but with:
- Multiple stick-figure characters grouped together (3–5 characters)
- Bold, large text overlay (white text, thick black outline)
- Each character doing something different/funny related to the topic
- Slightly more chaotic/busy composition than segment images

### Update `stages/thumbnail.py`

Change the thumbnail prompt generation. The LLM should generate a thumbnail-specific prompt like:

```
Update the script prompt to also generate a thumbnail_prompt that follows this pattern:
"group of 4-5 stick figure characters with round white heads and black dot eyes, each doing something different related to [topic], characters have exaggerated expressions, chaotic fun composition"
```

The text overlay in `thumbnail.py` should use:
- Font: Impact or Anton (already in assets/fonts/)
- Size: as large as possible while fitting (auto-scale to image width)
- Color: white fill with thick black stroke (3-4px)
- Position: top 30% of image, centered
- Text: the video title in ALL CAPS, max 2 lines
- Add a subtle dark gradient overlay behind the text for readability

```python
from PIL import Image, ImageDraw, ImageFont

def create_thumbnail(image_path: str, title: str, output_path: str):
    img = Image.open(image_path).convert("RGBA")

    # Add semi-transparent dark bar at top for text readability
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)
    draw_overlay.rectangle(
        [(0, 0), (img.width, int(img.height * 0.35))],
        fill=(0, 0, 0, 100)
    )
    img = Image.alpha_composite(img, overlay).convert("RGB")

    draw = ImageDraw.Draw(img)

    # Auto-scale font size
    title_upper = title.upper()
    font_size = 80
    font_path = "assets/fonts/Impact.ttf"  # or Anton-Regular.ttf

    while font_size > 20:
        font = ImageFont.truetype(font_path, font_size)
        bbox = draw.textbbox((0, 0), title_upper, font=font)
        text_width = bbox[2] - bbox[0]
        if text_width < img.width * 0.9:
            break
        font_size -= 2

    # Center text
    x = (img.width - text_width) // 2
    y = int(img.height * 0.05)

    # Black stroke
    for dx in range(-3, 4):
        for dy in range(-3, 4):
            draw.text((x + dx, y + dy), title_upper, font=font, fill="black")

    # White fill
    draw.text((x, y), title_upper, font=font, fill="white")

    img.save(output_path, quality=95)
```

---

## SUMMARY OF ALL CHANGES

1. **`config/style_suffix.txt`** — Rewrite to stick-figure webcomic style
2. **`config/prompts/script.md`** — Update to generate `image_prompts` (array, 2-4 per segment) instead of `image_prompt` (single string). Add instructions for simple scene descriptions.
3. **`services/image/replicate_flux.py`** — Switch model from `flux-1.1-pro` to `flux-schnell`. Update prompt assembly to put style first. Add NSFW blocklist check. Add safety suffix.
4. **`stages/images.py`** — Handle array of prompts per segment. Generate multiple images. Add `check_prompt_safety()` gate before every generation call.
5. **`stages/script.py`** — Add `moderate_script()` moderation check after script generation. Update segment schema to use `image_prompts` array.
6. **`stages/assembly.py`** — Split segment duration across multiple images. Use sentence-boundary cut points from alignment. Clamp image display time to 3-8 seconds.
7. **`media/alignment.py`** — Add `get_image_switch_times()` function for natural cut points.
8. **`stages/thumbnail.py`** — Update thumbnail prompt for group stick-figure composition. Add proper text overlay with auto-scaling, stroke, and dark gradient.
9. **`config.py` / `.env`** — Update `FLUX_MODEL` default to `black-forest-labs/flux-schnell`. Add `NSFW_CHECK_ENABLED=true` config option.
10. **DB schema** — If `Video` or `Segment` models store image paths, update to store a list of paths per segment instead of a single path.

### Files to update:
- `config/style_suffix.txt`
- `config/prompts/script.md`
- `src/chill_agent/services/image/replicate_flux.py`
- `src/chill_agent/stages/images.py`
- `src/chill_agent/stages/script.py`
- `src/chill_agent/stages/assembly.py`
- `src/chill_agent/media/alignment.py`
- `src/chill_agent/stages/thumbnail.py`
- `src/chill_agent/config.py`
- `src/chill_agent/db/models.py`
- `.env.example`

### Do NOT change:
- TTS pipeline (voice generation works fine)
- Upload pipeline (YouTube API works fine)
- Orchestrator flow (just handles new data shapes)
- CLI commands

Begin implementing all changes now.