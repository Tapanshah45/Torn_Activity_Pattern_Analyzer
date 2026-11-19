import ijson
from typing import Generator, Dict, Any


def stream_campaign_members(file_path: str) -> Generator[Dict[str, Any], None, None]:
    """
    Lazily yield each member object from the campaign JSON file.
    Uses ijson to avoid loading the entire file into memory.
    """
    with open(file_path, "rb") as f:
        yield from ijson.items(f, "members.item")


def get_campaign_metadata(file_path: str) -> Dict[str, Any]:
    """
    Extract only the top-level campaign metadata block without reading member data.
    Stops parsing as soon as the 'members' key is encountered.
    """
    with open(file_path, "rb") as f:
        parser = ijson.parse(f)
        campaign_data: Dict[str, Any] = {}
        for prefix, event, value in parser:
            if prefix.startswith("campaign."):
                key = prefix.split(".", 1)[1]
                campaign_data[key] = value
            elif prefix == "members":
                break
        return campaign_data
