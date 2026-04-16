import pytest
from fastapi import HTTPException

import chat.utils.helpers as helpers_mod


def test_validate_and_resolve_files_splits_images_and_other_files(monkeypatch, tmp_path):
    mount_dir = tmp_path / 'mount'
    mount_dir.mkdir()
    text_file = mount_dir / 'doc.txt'
    image_file = mount_dir / 'image.PNG'
    text_file.write_text('doc', encoding='utf-8')
    image_file.write_text('img', encoding='utf-8')

    monkeypatch.setattr(helpers_mod, 'MOUNT_BASE_DIR', str(mount_dir))

    other_files, image_files = helpers_mod.validate_and_resolve_files(
        [str(text_file), 'image.PNG']
    )

    assert other_files == [str(text_file.resolve())]
    assert image_files == [str(image_file.resolve())]


def test_validate_and_resolve_files_rejects_paths_outside_mount(monkeypatch, tmp_path):
    mount_dir = tmp_path / 'mount'
    mount_dir.mkdir()
    outside = tmp_path / 'outside.txt'
    outside.write_text('data', encoding='utf-8')

    monkeypatch.setattr(helpers_mod, 'MOUNT_BASE_DIR', str(mount_dir))

    with pytest.raises(HTTPException, match='Path outside mount directory'):
        helpers_mod.validate_and_resolve_files([str(outside)])


def test_tool_schema_to_string_formats_description_and_parameters():
    rendered = helpers_mod.tool_schema_to_string(
        {
            'search': {
                'description': 'Find documents. Return top results.',
                'parameters': {
                    'query': {'type': 'str', 'des': 'Search text'},
                    'topk': {'type': 'int'},
                },
            }
        }
    )

    assert 'TOOL NAME: search' in rendered
    assert '- Find documents.' in rendered
    assert '- Return top results.' in rendered
    assert '- query: str' in rendered
    assert '- topk: int' in rendered
