You are finalizing YouTube video metadata.

Given this video title and script summary, extract clean metadata for upload.

Title: {title}
Script summary: {summary}

Return a JSON object with:
{
  "title": "final title (max 100 chars)",
  "tags": ["tag1", ...],
  "category_id": "27",
  "language": "en",
  "made_for_kids": false,
  "contains_synthetic_media": true
}

Tags should be 12-15 relevant search terms. Title must be under 100 characters.
Always set contains_synthetic_media to true — this is an AI-generated video.
