import allTags from "@data/all_tags.json";

export const ALL_TAGS = new Set(
  allTags.map((tag) => tag.trim().toLowerCase()).filter(Boolean),
);

export function normalizeCandidateTag(tag: string) {
  return tag.trim().toLowerCase();
}

export function filterKnownTags(tags: string[]) {
  return tags
    .map(normalizeCandidateTag)
    .filter((tag, index, array) => ALL_TAGS.has(tag) && array.indexOf(tag) === index);
}
