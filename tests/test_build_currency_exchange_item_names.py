import gzip
import json

from scripts.build_currency_exchange_item_names import load_source


def test_load_source_accepts_plain_json_and_gzip(tmp_path):
    payload = {"Metadata/Items/Example": "Example Item"}
    plain = tmp_path / "items.json"
    compressed = tmp_path / "items.json.gz"
    plain.write_text(json.dumps(payload), encoding="utf-8")
    with gzip.open(compressed, "wt", encoding="utf-8") as target:
        json.dump(payload, target)

    assert load_source(plain) == payload
    assert load_source(compressed) == payload
