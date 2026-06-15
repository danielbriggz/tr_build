from dataclasses import dataclass


@dataclass(frozen=True)
class Platform:
    """A social media platform with its image dimensions and layout type."""
    name: str
    slug: str           # used for filenames and CLI display
    width: int
    height: int
    layout: str         # "story" | "portrait" | "landscape" | "editorial"


PLATFORMS: dict[str, Platform] = {
    "ig_story": Platform(
        name="IG Story",
        slug="ig_story",
        width=1080,
        height=1920,
        layout="story",
    ),
    "ig_portrait": Platform(
        name="IG Post (Portrait)",
        slug="ig_portrait",
        width=1080,
        height=1350,
        layout="portrait",
    ),
    "twitter": Platform(
        name="Twitter / X",
        slug="twitter",
        width=1600,
        height=900,
        layout="landscape",
    ),
    "linkedin": Platform(
        name="LinkedIn",
        slug="linkedin",
        width=1200,
        height=627,
        layout="editorial",
    ),
}
