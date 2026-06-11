import yaml

from promptcloak.config import RedactionConfig, Settings, load_settings
from promptcloak.security import encrypt_text, load_key, write_key_file


def test_encrypted_rules_load(tmp_path) -> None:
    key_file = tmp_path / "key"
    write_key_file(key_file)
    rules = [{"type": "exact", "value": "abcd1234", "name": "tail"}]
    encrypted = encrypt_text(yaml.safe_dump(rules), load_key(key_file))
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            Settings(
                redaction=RedactionConfig(encrypted=True, encrypted_rules=encrypted)
            ).model_dump(mode="json")
        ),
        encoding="utf-8",
    )

    settings = load_settings(config, key_file)

    assert settings.redaction.rules[0].value == "abcd1234"
